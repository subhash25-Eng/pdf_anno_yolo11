import logging
import math
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
import fitz  # PyMuPDF
from PIL import Image
from PyQt5.QtCore import QRunnable

from surya.layout import LayoutPredictor

from configParser import config_parser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# -------------------------- configuration --------------------------
@dataclass
class ExtractorConfig:
    dpi: int = 120  # 96–120 is usually plenty for page-level layout
    batch_size: int = 8  # Surya micro-batch for multi-page PDFs
    overlap_iou_threshold: float = 0.05  # when matching spans to zone rects
    max_pages_in_memory: int = 64  # safety guard for extreme PDFs


# -------------------------- utilities --------------------------
def _pdf_page_to_pil(page: fitz.Page, dpi: int) -> Image.Image:
    """Render a single PDF page to a PIL RGB image fully in-memory."""
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=matrix)
    img_bytes = pix.tobytes("png")
    return Image.open(BytesIO(img_bytes)).convert("RGB")


def _rect_from_xywh(x: float, y: float, w: float, h: float) -> fitz.Rect:
    return fitz.Rect(x, y, x + w, y + h)


def _bbox_to_xywh(bbox_xyxy: Sequence[float]) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = map(float, bbox_xyxy)
    return x1, y1, (x2 - x1), (y2 - y1)


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a.intersect(b)
    if inter.is_empty:
        return 0.0
    return inter.get_area() / (a.get_area() + b.get_area() - inter.get_area())


# -------------------------- core classes --------------------------
class ZoneExtractor:
    """
    Extracts page 'zones' from a PDF by:
      1) rasterizing each page to an image (in memory),
      2) running Surya's LayoutPredictor in **batches** to detect layout blocks,
      3) mapping each block back to PDF coordinates,
      4) extracting text + font info using a **per-page span cache**,
      5) streaming results via an optional page_callback.
    """

    def __init__(
        self,
        page_callback: Optional[Callable[[int, List[Dict]], None]] = None,
        page_offset: int = 0,
        config: Optional[ExtractorConfig] = None,
    ):
        self.page_callback = page_callback
        self.all_zones: List[Dict] = []
        self.file_path: Optional[str] = None
        self.page_offset = page_offset
        self.cfg = config or ExtractorConfig()

        # Pre-parse zones configuration for better performance
        self.zone_colors = self._parse_zone_colors()

        # Instantiate Surya predictor once
        self.layout_predictor = LayoutPredictor()

    # -------------------------- helpers --------------------------
    def _parse_zone_colors(self) -> Dict[str, str]:
        """Pre-parse zone colors to avoid repeated JSON parsing."""
        try:
            import json

            zone_list = json.loads(config_parser.zones_type)
            return {str(item.get("type", "")).lower(): item.get("color") for item in zone_list}
        except Exception as e:
            logger.warning(f"Failed to parse zone colors: {e}")
            return {}

    # ---------- text & font from cached spans ----------
    @staticmethod
    def _collect_page_spans(page: fitz.Page) -> List[Dict]:
        """Return a flat list of span dicts for the whole page once."""
        spans: List[Dict] = []
        try:
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []) or []:
                for line in block.get("lines", []) or []:
                    for span in line.get("spans", []) or []:
                        # Normalize coordinates as a Rect for fast checks
                        x0 = float(span.get("bbox", [0, 0, 0, 0])[0])
                        y0 = float(span.get("bbox", [0, 0, 0, 0])[1])
                        x1 = float(span.get("bbox", [0, 0, 0, 0])[2])
                        y1 = float(span.get("bbox", [0, 0, 0, 0])[3])
                        span["_rect"] = fitz.Rect(x0, y0, x1, y1)
                        spans.append(span)
        except Exception as e:
            logger.warning(f"Failed to collect spans: {e}")
        return spans

    def _extract_text_and_fonts_from_bbox_cached(
        self,
        spans: List[Dict],
        bbox_xywh: Tuple[float, float, float, float],
        iou_thresh: float,
    ) -> Tuple[str, str, str]:
        """Aggregate text, avg font size, and most common font from cached spans inside bbox."""
        rect = _rect_from_xywh(*bbox_xywh)
        keep: List[Dict] = []
        for sp in spans:
            r = sp.get("_rect")
            if r is None:
                continue
            # quick reject by bbox
            if not r.intersects(rect):
                continue
            if _iou(r, rect) >= iou_thresh:
                keep.append(sp)

        if not keep:
            return "", "", ""

        # Sort spans top-to-bottom, then left-to-right for readable text order
        keep.sort(key=lambda s: (float(s.get("bbox", [0, 0, 0, 0])[1]), float(s.get("bbox", [0, 0, 0, 0])[0])))

        # Concatenate text
        texts = [str(s.get("text", "")) for s in keep]
        joined = " ".join(t.strip() for t in texts if t)
        joined = " ".join(joined.split())  # normalize whitespace

        # Average font size & most common font name
        sizes = [float(s.get("size", 0.0)) for s in keep if "size" in s]
        avg_size = str(round(sum(sizes) / len(sizes), 1)) if sizes else ""

        fonts = [str(s.get("font", "")) for s in keep if s.get("font")]
        most_common_font = max(set(fonts), key=fonts.count) if fonts else ""

        # Heuristic line count: count distinct y-baselines buckets
        line_count = "0"
        if keep:
            y_vals = [float(s.get("bbox", [0, 0, 0, 0])[1]) for s in keep]
            y_vals.sort()
            # bucket by small deltas (2.0 px)
            lines = 0
            last_y = None
            for y in y_vals:
                if last_y is None or abs(y - last_y) > 2.0:
                    lines += 1
                    last_y = y
            line_count = str(lines)

        return joined, avg_size, most_common_font if most_common_font else ""

    @staticmethod
    def _determine_size_class(font_size: str) -> str:
        try:
            size = float(font_size) if font_size else 0.0
            if size >= 18:
                return "large"
            elif size >= 12:
                return "medium"
            elif size >= 8:
                return "small"
            else:
                return "tiny"
        except Exception:
            return "unknown"

    # -------------------------- core flow --------------------------
    def build_dom_once(self, file_path: str, page_offset: int):
        self.file_path = file_path
        self.page_offset = page_offset
        logger.debug(f"Starting DOM build for: {file_path}")

        pdf_document: Optional[fitz.Document] = None
        try:
            # Load PDF once
            pdf_document = fitz.open(self.file_path)

            # Process in micro-batches to control memory while still being fast
            total_pages = pdf_document.page_count
            bs = max(1, self.cfg.batch_size)
            for start in range(0, total_pages, bs):
                end = min(total_pages, start + bs)
                images: List[Image.Image] = []
                pages: List[fitz.Page] = []
                for pno in range(start, end):
                    page = pdf_document[pno]
                    pages.append(page)
                    images.append(_pdf_page_to_pil(page, self.cfg.dpi))

                # Run Surya once per micro-batch
                layout_results = self.layout_predictor(images)

                # Convert results page-by-page
                for local_idx, layout_result in enumerate(layout_results):
                    page_idx = start + local_idx
                    page = pages[local_idx]
                    img_w, img_h = images[local_idx].size
                    pdf_w, pdf_h = page.rect.width, page.rect.height

                    # Pre-extract spans once for this page
                    spans = self._collect_page_spans(page)

                    zones = self._convert_layout_to_zones(
                        layout_result=layout_result,
                        image_size=(img_w, img_h),
                        page_size=(pdf_w, pdf_h),
                        page_idx=page_idx,
                        page_offset=page_offset,
                        spans=spans,
                    )

                    page_num = page_idx + page_offset
                    if zones:
                        self._flush_page_zones(page_num, zones)
                        self.all_zones.extend(zones)

        finally:
            if pdf_document:
                pdf_document.close()

    def _convert_layout_to_zones(
        self,
        layout_result,
        image_size: Tuple[float, float],
        page_size: Tuple[float, float],
        page_idx: int,
        page_offset: int,
        spans: List[Dict],
    ) -> List[Dict]:
        """Convert Surya LayoutResult to our zone dicts with reading-order aware sorting."""
        img_w, img_h = image_size
        pdf_w, pdf_h = page_size
        scale_x = (pdf_w / img_w) if img_w else 1.0
        scale_y = (pdf_h / img_h) if img_h else 1.0

        # LayoutResult has .bboxes: list[LayoutBox]
        boxes = getattr(layout_result, "bboxes", []) or []

        def sort_key(box):
            pos = getattr(box, "position", None)
            bbox = getattr(box, "bbox", None)
            y1 = float(bbox[1]) if bbox and len(bbox) >= 2 else 1e9
            return (pos if (pos is not None) else 1_000_000_000, y1)

        boxes_sorted = sorted(boxes, key=sort_key)

        zones: List[Dict] = []
        page_num = page_idx + page_offset

        for block_count, box in enumerate(boxes_sorted, start=1):
            bbox = getattr(box, "bbox", None)  # [x1, y1, x2, y2] in image coords
            label = getattr(box, "label", None)
            confidence = getattr(box, "confidence", None)
            position = getattr(box, "position", None)

            if not bbox or len(bbox) < 4:
                continue

            x1_img, y1_img, x2_img, y2_img = map(float, bbox)
            # Scale to PDF coordinate space
            x1_pdf = x1_img * scale_x
            y1_pdf = y1_img * scale_y
            x2_pdf = x2_img * scale_x
            y2_pdf = y2_img * scale_y
            width_pdf = x2_pdf - x1_pdf
            height_pdf = y2_pdf - y1_pdf

            block_id = f"pz{page_num + 1}-{block_count}"
            span_id = f"z{page_num + 1}-{block_count}"

            # Use configured color if available (case-insensitive)
            label_norm = str(label).lower() if label else ""
            color = self.zone_colors.get(label_norm)

            bbox_xywh = (x1_pdf, y1_pdf, width_pdf, height_pdf)

            # Use cached spans to build text + fonts quickly
            extracted_text, font_size, font_name = self._extract_text_and_fonts_from_bbox_cached(
                spans=spans,
                bbox_xywh=bbox_xywh,
                iou_thresh=self.cfg.overlap_iou_threshold,
            )

            size_class = self._determine_size_class(font_size)

            zone = {
                "block_id": block_id,
                "x": x1_pdf,
                "y": y1_pdf,
                "width": width_pdf,
                "height": height_pdf,
                "page": page_num,
                "text": extracted_text,
                "font_size": font_size,
                "size_class": size_class,
                "line_count": str(extracted_text.count("\n") + 1) if extracted_text else "0",
                "bbox": [x1_pdf, y1_pdf, width_pdf, height_pdf],
                "pg": page_num,
                "span_id": span_id,
                "label": label,
                "feats": font_name,  # store font name
                "type": label,
                "zone_color": color,
                "action_type": "self",
                "zone_object": {
                    "confidence": float(confidence) if confidence is not None else None,
                    "position": position,
                },
            }
            zones.append(zone)

        return zones

    # -------------------------- plumbing --------------------------
    def _flush_page_zones(self, page_num: int, zones: List[Dict]):
        if self.page_callback and zones:
            logger.debug(f"Sending {len(zones)} zones for page {page_num}")
            self.page_callback(page_num, zones)

    # API kept for backward compat
    def extract_id_with_split(self, html_string: str):
        """Kept for backward-compat with any HTML-derived IDs the caller may use."""
        try:
            parts = html_string.split("'id': '")
            if len(parts) <= 1:
                return None, None
            zone_type = None
            if "." in parts[0]:
                type_parts = parts[0].replace("{", "").split(".")
                if len(type_parts) > 1:
                    zone_type = type_parts[1].strip()
            id_value = parts[1].split("'")[0].strip()
            return id_value, zone_type
        except Exception as e:
            logger.error(f"Error extracting ID: {e}")
            return None, None


# -------------------------- background task --------------------------
class BackgroundZoneExtractionTask(QRunnable):
    """Background task wrapper to run ZoneExtractor without blocking the UI thread."""

    def __init__(self, file_path: str, on_finish=None, on_page=None, page_offset: int = 0, config: Optional[ExtractorConfig] = None):
        super().__init__()
        self.file_path = file_path
        self.on_finish = on_finish
        self.on_page = on_page
        self.page_offset = page_offset
        self.config = config or ExtractorConfig()

    def run(self):
        extractor: Optional[ZoneExtractor] = None
        try:
            logger.info(f"Zone extraction started for: {self.file_path}")
            extractor = ZoneExtractor(page_callback=self.on_page, page_offset=self.page_offset, config=self.config)
            extractor.build_dom_once(self.file_path, self.page_offset)
            logger.info(
                f"Zone extraction completed successfully. Extracted {len(extractor.all_zones)} zones"
            )
            if self.on_finish:
                self.on_finish(extractor)
        except FileNotFoundError as e:
            logger.error(f"File not found: {self.file_path} - {e}")
            if self.on_finish:
                self.on_finish(None)
        except PermissionError as e:
            logger.error(f"Permission denied: {self.file_path} - {e}")
            if self.on_finish:
                self.on_finish(None)
        except Exception as e:
            logger.exception(f"Unexpected error during zone extraction: {e}")
            if self.on_finish:
                self.on_finish(None)
