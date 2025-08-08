# zone_extractor.py (streaming version with callback per page)
import ast
import os
import traceback
from datetime import datetime
import json
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import fitz  # PyMuPDF
from ultralytics import YOLO
import supervision as sv
import fitz
import json
from typing import Callable, List, Dict, Optional
import logging
from PyQt5.QtCore import QRunnable

from configParser import config_parser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ZoneExtractor:
    def __init__(self, page_callback: Optional[Callable[[int, List[Dict]], None]] = None, page_offset: int = 0):
        self.page_callback = page_callback
        self.all_zones = []
        self.file_path = None  # Used for cleanup tracking
        self.model_path = "D://yolo_detection//yolov11x_best.pt"
        self.conf_threshold = 0.2
        self.iou_threshold = 0.8

    def build_dom_once(self, file_path, page_offset):
        self.file_path = file_path
        logger.debug(f"Starting DOM build for: {file_path}")

        pdf_name = Path(self.file_path).stem
        output_dir = f"{pdf_name}_detections"
        os.makedirs(output_dir, exist_ok=True)

        # Initialize processors
        pdf_processor = PDFProcessor()
        yolo_processor = YOLODetectionProcessor(self.model_path)

        # Load PDF document
        pdf_document = fitz.open(self.file_path)

        # Convert PDF to images
        image_paths = pdf_processor.pdf_to_images(self.file_path, output_dir)

        if not image_paths:
            logger.debug(f"Failed to convert to images : {file_path}")
            return

        # Process each page
        for i, image_path in enumerate(image_paths):
            results, image, detections = yolo_processor.process_image(
                image_path, self.conf_threshold, self.iou_threshold
            )

            if detections is not None:
                # Get PDF page (ensure this is before page size usage)
                page = pdf_document[i]

                json_data = yolo_processor.detections_to_json(
                    detections,
                    results,
                    image.shape,
                    pdf_page_size=(page.rect.width, page.rect.height)
                )
                json_data["page_number"] = i + 1
                block_count = -1
                current_page = None
                current_page_zones = []
                zones = json_data["detections"]
                # Sort zones by Y-coordinate descending (bottom first, top last)
                zones.sort(key=lambda z: float(z["bbox"]["y1"]))
                for idx, node in enumerate(zones):
                    logger.debug(f"Processing node {idx}")
                    try:
                        # Adjust page number with offset
                        page_num = int(json_data["page_number"]) - 1 + page_offset
                    except Exception as e:
                        logger.warning(f"Node {idx} has invalid page value: {page} — {e}")
                        continue

                    bboxes = node.get("bbox")
                    x = bboxes['x1']
                    y = bboxes['y1']
                    width = node["width"]
                    height = node["height"]

                    bbox = [x, y, width, height]
                    if not bbox:
                        logger.debug(f"Node {idx} skipped: no bbox")
                        continue

                    if current_page is not None and page_num != current_page:
                        if self.page_callback:
                            logger.debug(f"Page change detected: sending zones for page {current_page}")
                            self.page_callback(current_page, current_page_zones)
                        current_page_zones = []
                        block_count = 0
                    elif current_page is None:
                        block_count = 0

                    current_page = page_num
                    block_count += 1

                    block_id = f"pz{page_num + 1}-{block_count}"
                    span_id = f"z{page_num + 1}-{block_count}"

                    zone_list = json.loads(config_parser.zones_type)
                    color = next(
                        (item["color"] for item in zone_list if item["type"] == node["label"]),
                        None
                    )

                    zone_data = {
                        "block_id": block_id,
                        "x": bboxes["x1"],
                        "y": bboxes["y1"],
                        "width": node["width"],
                        "height": node["height"],
                        "page": page_num,
                        "text": "",
                        "font_size": "",
                        "size_class": "",
                        "line_count": "",
                        "bbox": bbox,
                        "pg": page_num,
                        "span_id": span_id,
                        "label": node["label"],
                        "feats": "",
                        "type": node["label"],
                        "zone_color": color,
                        "action_type": "self",
                        "zone_object": {}
                    }
                    self.all_zones.append(zone_data)
                    current_page_zones.append(zone_data)

                if current_page_zones and self.page_callback:
                    logger.debug(f"Final flush: sending zones for page {current_page}")
                    self.page_callback(current_page, current_page_zones)

    def extract_id_with_split(self,html_string):
        try:
            id_value, zone_type = None, None
            parts = html_string.split("'id': '")
            if len(parts) > 0:
                if "." in parts[0]:
                    type_Split = parts[0].replace("{", "").split(".")
                    zone_type = type_Split[1].strip()
                id_value = parts[1].split("'")[0].strip()
            return id_value ,zone_type
        except Exception as e:
            traceback.print_exc()
            return None, None

class YOLODetectionProcessor:
    """Handle YOLO detection and data processing"""

    def __init__(self, model_path="yolov11x_best.pt"):
        self.model_path = model_path
        self.model = None
        self.load_model()

    def load_model(self):
        """Load YOLO model"""
        try:
            self.model = YOLO(self.model_path)
            print(f"✓ Model loaded: {self.model_path}")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None

    def process_image(self, image_path, conf_threshold=0.2, iou_threshold=0.8):
        """Process image with YOLO and return detections"""
        if self.model is None:
            return None, None, None

        try:
            # Run YOLO detection
            results = self.model(image_path, conf=conf_threshold, iou=iou_threshold)[0]
            image = cv2.imread(image_path)
            detections = sv.Detections.from_ultralytics(results)

            return results, image, detections

        except Exception as e:
            print(f"Error processing image: {e}")
            return None, None, None

    def detections_to_json(self, detections, results, image_shape, pdf_page_size=None):
        """Convert detections to JSON format with optional scaling to PDF page size."""
        if detections is None or len(detections) == 0:
            return {"detections": [], "metadata": {"total_detections": 0}}

        img_h, img_w = image_shape[:2]

        if pdf_page_size:
            pdf_w, pdf_h = pdf_page_size
        else:
            pdf_w, pdf_h = img_w, img_h  # default: no scaling

        scale_x = pdf_w / img_w
        scale_y = pdf_h / img_h

        json_detections = []
        class_names = self.model.names if self.model else {}

        for i, (bbox, conf, class_id) in enumerate(
                zip(detections.xyxy, detections.confidence, detections.class_id)
        ):
            x1, y1, x2, y2 = bbox

            # Scale to PDF size but keep image-origin Y
            x1_scaled = float(x1) * scale_x
            y1_scaled = float(y1) * scale_y
            x2_scaled = float(x2) * scale_x
            y2_scaled = float(y2) * scale_y

            detection = {
                "id": i,
                "bbox": {
                    "x1": x1_scaled,
                    "y1": y1_scaled,
                    "x2": x2_scaled,
                    "y2": y2_scaled
                },
                "confidence": float(conf),
                "class_id": int(class_id),
                "label": class_names.get(int(class_id), f"class_{int(class_id)}"),
                "width": x2_scaled - x1_scaled,
                "height": y2_scaled - y1_scaled,
                "area": (x2_scaled - x1_scaled) * (y2_scaled - y1_scaled)
            }
            json_detections.append(detection)

        # Create metadata
        unique_classes = list(set(det["label"] for det in json_detections))
        class_counts = {cls: sum(1 for det in json_detections if det["label"] == cls) for cls in unique_classes}

        json_data = {
            "detections": json_detections,
            "metadata": {
                "total_detections": len(json_detections),
                "unique_classes": unique_classes,
                "class_counts": class_counts,
                "image_shape": {
                    "height": image_shape[0],
                    "width": image_shape[1],
                    "channels": image_shape[2] if len(image_shape) > 2 else None
                },
                "format": "xyxy",
                "created_at": datetime.now().isoformat(),
                "model_info": {
                    "model_path": self.model_path,
                    "confidence_threshold": float(min(detections.confidence)) if len(
                        detections.confidence) > 0 else 0.0,
                    "class_names": class_names
                }
            }
        }

        return json_data


class PDFProcessor:
    """Handle PDF to image conversion"""

    @staticmethod
    def pdf_to_images(pdf_path, output_dir, dpi=150):
        """Convert PDF pages to images"""
        try:
            doc = fitz.open(pdf_path)
            image_paths = []

            for page_num in range(doc.page_count):
                page = doc[page_num]
                # Create matrix for desired DPI
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)

                # Save as image
                image_filename = f"page_{page_num + 1:03d}.png"
                image_path = os.path.join(output_dir, image_filename)
                pix.save(image_path)
                image_paths.append(image_path)

            doc.close()
            return image_paths

        except Exception as e:
            print(f"Error converting PDF: {e}")
            return []


class BackgroundZoneExtractionTask(QRunnable):
    def __init__(self, file_path, on_finish=None, on_page=None, page_offset: int = 0):
        super().__init__()
        self.file_path = file_path
        self.on_finish = on_finish
        self.on_page = on_page
        self.page_offset = page_offset

    def run(self):
        try:
            logger.info(f"Zone extraction started for: {self.file_path}")
            extractor = ZoneExtractor(page_callback=self.on_page, page_offset=self.page_offset)
            extractor.build_dom_once(self.file_path,self.page_offset)
            logger.info("Zone extraction finished successfully")
            if self.on_finish:
                self.on_finish(extractor)
        except Exception as e:
            logger.exception(f"Zone extraction error: {e}")
            if self.on_finish:
                self.on_finish(None)
