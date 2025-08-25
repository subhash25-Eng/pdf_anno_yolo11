import json
from PIL import Image
import numpy as np
from transformers import LayoutLMv3Processor, LayoutLMv3Model
import os


# Optional: PaddleOCR is very accurate for LayoutLMv3 preprocessing
from paddleocr import PaddleOCR
ocr_engine = PaddleOCR(use_angle_cls=True, lang='en')


def normalize_bbox_xyxy_to_1000(bbox, page_w, page_h):
    """Convert absolute xyxy to 0-1000 normalized coordinates."""
    x1, y1, x2, y2 = bbox
    return [
        int((x1 / page_w) * 1000),
        int((y1 / page_h) * 1000),
        int((x2 / page_w) * 1000),
        int((y2 / page_h) * 1000)
    ]


def auto_column_partition_by_gaps(items, page_width, min_gap_ratio=0.07, gap_multiplier=3.0):
    """Partition items into columns using large horizontal gaps."""
    if len(items) <= 1:
        return [list(range(len(items)))]

    x_centers = np.array([(it['bbox'][0] + it['bbox'][2]) / 2 for it in items])
    sort_idx = np.argsort(x_centers)
    sorted_centers = x_centers[sort_idx]

    diffs = np.diff(sorted_centers)
    median_gap = np.median(diffs) if len(diffs) > 0 else page_width
    threshold = max(page_width * min_gap_ratio, median_gap * gap_multiplier)

    breakpoints = np.where(diffs > threshold)[0]

    columns = []
    start = 0
    for b in breakpoints:
        group_idx = sort_idx[start:b + 1].tolist()
        columns.append(group_idx)
        start = b + 1
    columns.append(sort_idx[start:].tolist())

    col_avg_x = [np.mean([items[i]['bbox'][0] for i in col]) for col in columns]
    cols_sorted = [col for _, col in sorted(zip(col_avg_x, columns), key=lambda x: x[0])]

    return cols_sorted


def sort_items_reading_order(items, page_width, page_height):
    """Sort OCR results or JSON items into proper reading order."""
    if not items:
        return []

    columns = auto_column_partition_by_gaps(items, page_width)

    sorted_items = []
    for col in columns:
        col_items = [items[i] for i in col]
        col_items_sorted = sorted(col_items, key=lambda o: (o['bbox'][1], o['bbox'][0]))  # sort by y, then x
        sorted_items.extend(col_items_sorted)

    for seq, obj in enumerate(sorted_items, start=1):
        obj['sequence'] = seq
        obj['bbox'] = normalize_bbox_xyxy_to_1000(obj['bbox'], page_width, page_height)

    return sorted_items


from paddleocr import PaddleOCR
from PIL import Image
import numpy as np

def run_ocr(image_path):
    image = Image.open(image_path).convert("RGB")
    page_w, page_h = image.size
    img_np = np.array(image)

    try:
        ocr_result = ocr_engine.predict(img_np)  # Pass image array instead of path
    except TypeError:
        ocr_result = ocr_engine.ocr(img_np)

    data = []
    for page in ocr_result:
        for line in page:
            try:
                points = line[0]
                if len(points) >= 4:
                    x1, y1 = points[0]
                    x2, y2 = points[2]
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                    if text.strip():
                        data.append({"text": text, "bbox": [x1, y1, x2, y2]})
            except Exception as e:
                print(f"[OCR Warning] Skipped line: {e}")
    return data, page_w, page_h



def prepare_layoutlmv3_inputs(json_path=None, image_path=None, processor=None, max_length=512):
    """
    Prepares LayoutLMv3 inputs from either:
      - json_path + image_path (pre-labeled data)
      - image_path only (OCR mode)
    """
    if image_path is None:
        raise ValueError("image_path is required")

    image = Image.open(image_path).convert("RGB")
    page_w, page_h = image.size

    # If JSON provided, use it
    if json_path and os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure bbox in xyxy form
        data_xyxy = []
        for obj in data:
            x, y, w, h = obj["bbox"]
            data_xyxy.append({
                "text": obj["text"],
                "bbox": [x, y, x + w, y + h]
            })
        sorted_data = sort_items_reading_order(data_xyxy, page_w, page_h)

    else:
        # Run OCR mode
        ocr_data, page_w, page_h = run_ocr(image_path)
        sorted_data = sort_items_reading_order(ocr_data, page_w, page_h)

    # Prepare for LayoutLMv3
    words = [d['text'] for d in sorted_data]
    boxes = [d['bbox'] for d in sorted_data]

    encoding = processor(
        images=image,
        text=words,
        boxes=boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=max_length
    )

    # Save sorted JSON
    out_json = (os.path.splitext(json_path)[0] if json_path else os.path.splitext(image_path)[0]) + "_sorted.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)

    return encoding, sorted_data


# Example usage
if __name__ == "__main__":
    processor = LayoutLMv3Processor.from_pretrained("microsoft/layoutlmv3-base", apply_ocr=False)
    model = LayoutLMv3Model.from_pretrained("microsoft/layoutlmv3-base")

    encoding, sorted_data = prepare_layoutlmv3_inputs(
        # json_path=r"D:\projects\pdf_anno_yolo11\saved_zones\30028_11.json",
        image_path=r"D:\projects\pdf_anno_yolo11\temp_train_data\30028_11\images\30028_11_page_001.png",
        processor=processor
    )

    print(f"Sorted {sorted_data} elements. JSON saved with sequence numbers.")
