
# zone_extractor.py (Surya LayoutPredictor version — replaces YOLO pipeline)
import os
import json
import logging
from pathlib import Path
from typing import Callable, List, Dict, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image
from PyQt5.QtCore import QRunnable

from surya.layout import LayoutPredictor

from configParser import config_parser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ZoneExtractor:
    """
    Extracts page 'zones' from a PDF by:
      1) rasterizing each page to an image,
      2) running Surya's LayoutPredictor to detect layout blocks with reading order,
      3) mapping each block back to PDF coordinates,
      4) extracting text + font info for each zone from the PDF,
      5) streaming results via an optional page_callback.
    """
    def __init__(self, page_callback: Optional[Callable[[int, List[Dict]], None]] = None, page_offset: int = 0):
        self.page_callback = page_callback
        self.all_zones: List[Dict] = []
        self.file_path: Optional[str] = None
        self.page_offset = page_offset

        # Pre-parse zones configuration for better performance
        self.zone_colors = self._parse_zone_colors()

        # Instantiate once; Surya supports callable predictor
        self.layout_predictor = LayoutPredictor()

    # -------------------------- helpers --------------------------
    def _parse_zone_colors(self) -> Dict[str, str]:
        """Pre-parse zone colors to avoid repeated JSON parsing"""
        try:
            zone_list = json.loads(config_parser.zones_type)
            return {str(item.get("type", "")).lower(): item.get("color") for item in zone_list}
        except Exception as e:
            logger.warning(f"Failed to parse zone colors: {e}")
            return {}

    def extract_text_from_bbox(self, pdf_document, page_num: int, bbox_xywh: Tuple[float, float, float, float]) -> str:
        """Extract text from a specific bbox (x, y, w, h) in PDF page"""
        try:
            page = pdf_document[page_num]
            x1, y1, width, height = bbox_xywh
            x2, y2 = x1 + width, y1 + height
            rect = fitz.Rect(x1, y1, x2, y2)
            text = page.get_textbox(rect) or ""
            # Normalize whitespace
            text = " ".join(text.split())
            return text
        except Exception as e:
            logger.warning(f"Error extracting text from bbox {bbox_xywh} on page {page_num}: {e}")
            return ""

    def get_font_info_from_bbox(self, pdf_document, page_num: int, bbox_xywh: Tuple[float, float, float, float]) -> Tuple[str, str]:
        """Extract average font size and most common font name from a bbox"""
        try:
            page = pdf_document[page_num]
            x1, y1, width, height = bbox_xywh
            x2, y2 = x1 + width, y1 + height
            rect = fitz.Rect(x1, y1, x2, y2)

            blocks = page.get_text("dict", clip=rect)
            font_sizes = []
            font_names  = []
            for block in blocks.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if "size" in span:
                            font_sizes.append(span["size"])  # float
                        if "font" in span:
                            font_names.append(span["font"])  # str

            avg_font_size = str(round(sum(font_sizes) / len(font_sizes), 1)) if font_sizes else ""
            most_common_font = max(set(font_names), key=font_names.count) if font_names else ""
            return avg_font_size, most_common_font
        except Exception as e:
            logger.warning(f"Error extracting font info from bbox {bbox_xywh} on page {page_num}: {e}")
            return "", ""

    def _determine_size_class(self, font_size: str) -> str:
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

        pdf_name = Path(self.file_path).stem
        output_dir = Path(f"temp/{pdf_name}_detections")
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_document = None
        image_paths: List[str] = []
        try:
            # Load PDF once
            pdf_document = fitz.open(self.file_path)

            # Convert PDF → images on disk (RGB PNG @ 150 DPI)
            image_paths = PDFProcessor.pdf_to_images(self.file_path, str(output_dir))

            if not image_paths:
                logger.debug(f"Failed to convert to images: {file_path}")
                return

            # Process pages sequentially to immediately stream page results
            self._process_pages(image_paths, pdf_document, page_offset)

        finally:
            if pdf_document:
                pdf_document.close()
            self._cleanup_temp_images(image_paths)

    def _process_pages(self, image_paths: List[str], pdf_document, page_offset: int):
        current_page_num = None
        current_page_zones: List[Dict] = []

        for page_idx, image_path in enumerate(image_paths):
            try:
                # Load image for the page
                image = Image.open(image_path).convert("RGB")
                img_w, img_h = image.size

                # Run Surya LayoutPredictor on this page image
                # Returns a list; we pass [image] to keep API consistent
                layout_results = self.layout_predictor([image])
                if not layout_results:
                    continue
                layout_result = layout_results[0]

                # Gather zones
                page = pdf_document[page_idx]
                page_size = (page.rect.width, page.rect.height)

                zones = self._convert_layout_to_zones(
                    layout_result=layout_result,
                    image_size=(img_w, img_h),
                    page_size=page_size,
                    page_idx=page_idx,
                    page_offset=page_offset,
                    pdf_document=pdf_document
                )

                page_num = page_idx + page_offset
                if current_page_num is not None and page_num != current_page_num:
                    self._flush_page_zones(current_page_num, current_page_zones)
                    current_page_zones = []

                current_page_num = page_num
                current_page_zones.extend(zones)
                self.all_zones.extend(zones)

            except Exception as e:
                logger.exception(f"Error processing page {page_idx}: {e}")
                continue

        # Flush last page
        if current_page_zones:
            self._flush_page_zones(current_page_num, current_page_zones)

    def _convert_layout_to_zones(self, layout_result, image_size, page_size, page_idx, page_offset, pdf_document) -> List[Dict]:
        """Convert Surya LayoutResult to our zone dicts with reading-order aware sorting."""
        img_w, img_h = image_size
        pdf_w, pdf_h = page_size
        scale_x = pdf_w / img_w if img_w else 1.0
        scale_y = pdf_h / img_h if img_h else 1.0

        # LayoutResult has .bboxes: list[LayoutBox]
        boxes = getattr(layout_result, "bboxes", []) or []

        def sort_key(box):
            # Prefer explicit reading-order (position); fallback to top y
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
            width_pdf  = x2_pdf - x1_pdf
            height_pdf = y2_pdf - y1_pdf

            block_id = f"pz{page_num + 1}-{block_count}"
            span_id  = f"z{page_num + 1}-{block_count}"

            # Use configured color if available (case-insensitive)
            label_norm = str(label).lower() if label else ""
            color = self.zone_colors.get(label_norm)

            # Extract text + font info from the PDF page
            bbox_xywh = (x1_pdf, y1_pdf, width_pdf, height_pdf)
            extracted_text = self.extract_text_from_bbox(pdf_document, page_idx, bbox_xywh)
            font_size, font_name = self.get_font_info_from_bbox(pdf_document, page_idx, bbox_xywh)

            # Line count from PDF spans is expensive; approximate by splitting on newlines if any
            line_count = str(extracted_text.count("\n") + 1) if extracted_text else "0"

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
                "line_count": line_count,
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
                    "position": position
                }
            }
            zones.append(zone)

        return zones

    # -------------------------- plumbing --------------------------
    def _flush_page_zones(self, page_num: int, zones: List[Dict]):
        if self.page_callback and zones:
            logger.debug(f"Sending {len(zones)} zones for page {page_num}")
            self.page_callback(page_num, zones)

    def _cleanup_temp_images(self, image_paths: List[str]):
        for image_path in image_paths or []:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except OSError as e:
                logger.warning(f"Failed to remove temp image {image_path}: {e}")

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


class PDFProcessor:
    """PDF → image conversion with resource management."""
    @staticmethod
    def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 150) -> List[str]:
        doc = None
        image_paths: List[str] = []
        try:
            doc = fitz.open(pdf_path)
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            for page_num in range(doc.page_count):
                try:
                    page = doc[page_num]
                    pix = page.get_pixmap(matrix=matrix)
                    image_filename = f"page_{page_num + 1:03d}.png"
                    image_path = os.path.join(output_dir, image_filename)
                    pix.save(image_path)
                    image_paths.append(image_path)
                except Exception as e:
                    logger.error(f"Error converting page {page_num}: {e}")
                    continue
            return image_paths
        except Exception as e:
            logger.error(f"Error converting PDF {pdf_path}: {e}")
            return []
        finally:
            if doc:
                doc.close()


class BackgroundZoneExtractionTask(QRunnable):
    """Background task wrapper to run ZoneExtractor without blocking the UI thread."""
    def __init__(self, file_path: str, on_finish=None, on_page=None, page_offset: int = 0):
        super().__init__()
        self.file_path = file_path
        self.on_finish = on_finish
        self.on_page = on_page
        self.page_offset = page_offset

    def run(self):
        extractor: Optional[ZoneExtractor] = None
        try:
            logger.info(f"Zone extraction started for: {self.file_path}")
            extractor = ZoneExtractor(page_callback=self.on_page, page_offset=self.page_offset)
            extractor.build_dom_once(self.file_path, self.page_offset)
            logger.info(f"Zone extraction completed successfully. Extracted {len(extractor.all_zones)} zones")
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
