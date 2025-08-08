# zone_extractor.py (optimized version)
import ast
import os
import traceback
import json
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF
from ultralytics import YOLO
import supervision as sv
from typing import Callable, List, Dict, Optional, Tuple
import logging
from PyQt5.QtCore import QRunnable

from configParser import config_parser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



class ZoneExtractor:
    def __init__(self, page_callback: Optional[Callable[[int, List[Dict]], None]] = None, page_offset: int = 0):
        self.page_callback = page_callback
        self.all_zones = []
        self.file_path = None
        self.model_path = "D://yolo_detection//yolov11x_best.pt"
        self.conf_threshold = 0.2
        self.iou_threshold = 0.8

        # Pre-parse zones configuration for better performance
        self.zone_colors = self._parse_zone_colors()

    def _parse_zone_colors(self):
        """Pre-parse zone colors to avoid repeated JSON parsing"""
        try:
            zone_list = json.loads(config_parser.zones_type)
            return {item["type"]: item["color"] for item in zone_list}
        except Exception as e:
            logger.warning(f"Failed to parse zone colors: {e}")
            return {}

    def extract_text_from_bbox(self, pdf_document, page_num: int, bbox: Tuple[float, float, float, float]) -> str:
        """Extract text from a specific bbox in PDF page"""
        try:
            page = pdf_document[page_num]
            x1, y1, width, height = bbox
            x2, y2 = x1 + width, y1 + height

            # Create rectangle for text extraction
            rect = fitz.Rect(x1, y1, x2, y2)

            # Extract text inside the rectangle
            text = page.get_textbox(rect).strip()

            # Clean up text (remove extra whitespaces, newlines)
            text = ' '.join(text.split()) if text else ""

            return text
        except Exception as e:
            logger.warning(f"Error extracting text from bbox {bbox} on page {page_num}: {e}")
            return ""

    def get_font_info_from_bbox(self, pdf_document, page_num: int, bbox: Tuple[float, float, float, float]) -> Tuple[
        str, str]:
        """Extract font size and other text properties from bbox"""
        try:
            page = pdf_document[page_num]
            x1, y1, width, height = bbox
            x2, y2 = x1 + width, y1 + height

            rect = fitz.Rect(x1, y1, x2, y2)

            # Get text blocks with formatting information
            blocks = page.get_text("dict", clip=rect)

            font_sizes = []
            font_names = []

            for block in blocks.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if span.get("size"):
                                font_sizes.append(span["size"])
                            if span.get("font"):
                                font_names.append(span["font"])

            # Get most common font size
            avg_font_size = str(round(sum(font_sizes) / len(font_sizes), 1)) if font_sizes else ""
            most_common_font = max(set(font_names), key=font_names.count) if font_names else ""

            return avg_font_size, most_common_font

        except Exception as e:
            logger.warning(f"Error extracting font info from bbox {bbox} on page {page_num}: {e}")
            return "", ""

    def build_dom_once(self, file_path, page_offset):
        self.file_path = file_path
        logger.debug(f"Starting DOM build for: {file_path}")

        pdf_name = Path(self.file_path).stem
        output_dir = Path(f"temp/{pdf_name}_detections")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize processors with shared model instance
        pdf_processor = PDFProcessor()
        yolo_processor = YOLODetectionProcessor(self.model_path)

        pdf_document = None
        try:
            # Load PDF document once
            pdf_document = fitz.open(self.file_path)

            # Convert PDF to images
            image_paths = pdf_processor.pdf_to_images(self.file_path, str(output_dir))

            if not image_paths:
                logger.debug(f"Failed to convert to images: {file_path}")
                return

            # Process all pages with text extraction
            self._process_pages(image_paths, pdf_document, yolo_processor, page_offset)

        finally:
            # Ensure PDF document is properly closed
            if pdf_document:
                pdf_document.close()

            # Cleanup temporary images
            self._cleanup_temp_images(image_paths)

    def _process_pages(self, image_paths, pdf_document, yolo_processor, page_offset):
        """Process all pages efficiently with batch operations"""
        current_page = None
        current_page_zones = []

        for page_idx, image_path in enumerate(image_paths):
            try:
                # Get detection results
                results, image, detections = yolo_processor.process_image(
                    image_path, self.conf_threshold, self.iou_threshold
                )

                if detections is None or len(detections) == 0:
                    continue

                # Get PDF page dimensions
                page = pdf_document[page_idx]
                page_size = (page.rect.width, page.rect.height)

                # Convert detections to zones with text extraction
                zones = self._convert_detections_to_zones(
                    detections, results, image.shape, page_size, page_idx, page_offset, pdf_document
                )

                # Handle page transitions
                page_num = page_idx + page_offset
                if current_page is not None and page_num != current_page:
                    self._flush_page_zones(current_page, current_page_zones)
                    current_page_zones = []

                current_page = page_num
                current_page_zones.extend(zones)
                self.all_zones.extend(zones)

            except Exception as e:
                logger.error(f"Error processing page {page_idx}: {e}")
                continue

        # Flush final page
        if current_page_zones and self.page_callback:
            self._flush_page_zones(current_page, current_page_zones)

    def _convert_detections_to_zones(self, detections, results, image_shape, page_size, page_idx, page_offset,
                                     pdf_document):
        """Convert YOLO detections to zone format with text extraction"""
        if len(detections) == 0:
            return []

        page_num = page_idx + page_offset
        img_h, img_w = image_shape[:2]
        pdf_w, pdf_h = page_size

        # Calculate scaling factors once
        scale_x = pdf_w / img_w
        scale_y = pdf_h / img_h

        # Get class names once
        class_names = results.names if hasattr(results, 'names') else {}

        zones = []

        # Create zones list with scaled coordinates
        zone_data_list = []
        for i, (bbox, conf, class_id) in enumerate(zip(detections.xyxy, detections.confidence, detections.class_id)):
            x1, y1, x2, y2 = bbox

            # Scale coordinates
            x1_scaled = float(x1) * scale_x
            y1_scaled = float(y1) * scale_y
            x2_scaled = float(x2) * scale_x
            y2_scaled = float(y2) * scale_y

            width = x2_scaled - x1_scaled
            height = y2_scaled - y1_scaled

            label = class_names.get(int(class_id), f"class_{int(class_id)}")

            zone_data_list.append({
                'bbox': {'x1': x1_scaled, 'y1': y1_scaled, 'x2': x2_scaled, 'y2': y2_scaled},
                'width': width,
                'height': height,
                'label': label,
                'confidence': float(conf)
            })

        # Sort by Y-coordinate (batch operation)
        zone_data_list.sort(key=lambda z: z["bbox"]["y1"])

        # Create final zone objects with text extraction
        for block_count, zone_data in enumerate(zone_data_list, 1):
            bbox_data = zone_data['bbox']

            block_id = f"pz{page_num + 1}-{block_count}"
            span_id = f"z{page_num + 1}-{block_count}"

            # Get color from pre-parsed dictionary
            color = self.zone_colors.get(zone_data["label"].lower())

            # Extract text from the bbox
            bbox_for_text = (bbox_data["x1"], bbox_data["y1"], zone_data["width"], zone_data["height"])
            extracted_text = self.extract_text_from_bbox(pdf_document, page_idx, bbox_for_text)

            # Get font information
            font_size, font_name = self.get_font_info_from_bbox(pdf_document, page_idx, bbox_for_text)

            # Count lines in extracted text
            line_count = str(len(extracted_text.split('\n'))) if extracted_text else "0"

            # Determine size class based on font size
            size_class = self._determine_size_class(font_size)

            zone = {
                "block_id": block_id,
                "x": bbox_data["x1"],
                "y": bbox_data["y1"],
                "width": zone_data["width"],
                "height": zone_data["height"],
                "page": page_num,
                "text": extracted_text,  # ← TEXT EXTRACTED HERE
                "font_size": font_size,
                "size_class": size_class,
                "line_count": line_count,
                "bbox": [bbox_data["x1"], bbox_data["y1"], zone_data["width"], zone_data["height"]],
                "pg": page_num,
                "span_id": span_id,
                "label": zone_data["label"],
                "feats": font_name,  # Store font name in feats
                "type": zone_data["label"],
                "zone_color": color,
                "action_type": "self",
                "zone_object": {
                    "confidence": zone_data["confidence"],
                    "font_name": font_name
                }
            }
            zones.append(zone)

        return zones

    def _determine_size_class(self, font_size: str) -> str:
        """Determine size class based on font size"""
        try:
            size = float(font_size) if font_size else 0
            if size >= 18:
                return "large"
            elif size >= 12:
                return "medium"
            elif size >= 8:
                return "small"
            else:
                return "tiny"
        except:
            return "unknown"

    def _flush_page_zones(self, page_num, zones):
        """Send zones for a page via callback"""
        if self.page_callback and zones:
            logger.debug(f"Sending {len(zones)} zones for page {page_num}")
            self.page_callback(page_num, zones)

    def _cleanup_temp_images(self, image_paths):
        """Clean up temporary image files"""
        for image_path in image_paths or []:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except OSError as e:
                logger.warning(f"Failed to remove temp image {image_path}: {e}")

    def extract_id_with_split(self, html_string):
        """Extract ID and zone type from HTML string"""
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

        except (IndexError, AttributeError) as e:
            logger.error(f"Error extracting ID: {e}")
            return None, None


class YOLODetectionProcessor:
    """Optimized YOLO detection processor with model caching"""

    def __init__(self, model_path="yolov11x_best.pt"):
        self.model_path = model_path
        self.model = None
        self.class_names = {}
        self._load_model()

    def _load_model(self):
        """Load YOLO model once and cache class names"""
        try:
            self.model = YOLO(self.model_path)
            self.class_names = self.model.names
            logger.info(f"Model loaded: {self.model_path}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            self.model = None

    def process_image(self, image_path, conf_threshold=0.2, iou_threshold=0.8):
        """Process image with YOLO detection"""
        if self.model is None:
            return None, None, None

        try:
            # Run detection
            results = self.model(image_path, conf=conf_threshold, iou=iou_threshold, verbose=False)[0]
            image = cv2.imread(image_path)

            if image is None:
                logger.warning(f"Failed to load image: {image_path}")
                return None, None, None

            detections = sv.Detections.from_ultralytics(results)
            return results, image, detections

        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return None, None, None


class PDFProcessor:
    """Optimized PDF processor with better resource management"""

    @staticmethod
    def pdf_to_images(pdf_path, output_dir, dpi=150):
        """Convert PDF pages to images with optimized memory usage"""
        doc = None
        try:
            doc = fitz.open(pdf_path)
            image_paths = []

            # Pre-calculate matrix once
            matrix = fitz.Matrix(dpi / 72, dpi / 72)

            for page_num in range(doc.page_count):
                try:
                    page = doc[page_num]
                    pix = page.get_pixmap(matrix=matrix)

                    image_filename = f"page_{page_num + 1:03d}.png"
                    image_path = os.path.join(output_dir, image_filename)

                    pix.save(image_path)
                    image_paths.append(image_path)

                    # Free pixmap memory immediately
                    pix = None

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
    """Optimized background task with better error handling"""

    def __init__(self, file_path, on_finish=None, on_page=None, page_offset: int = 0):
        super().__init__()
        self.file_path = file_path
        self.on_finish = on_finish
        self.on_page = on_page
        self.page_offset = page_offset

    def run(self):
        extractor = None
        try:
            logger.info(f"Zone extraction started for: {self.file_path}")

            extractor = ZoneExtractor(
                page_callback=self.on_page,
                page_offset=self.page_offset
            )

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
