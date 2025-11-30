"""Image Annotation Module

Uses Pillow to draw bounding boxes on student answer images based on AI grading feedback.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import ANNOTATION_COLORS
from utils.logger import setup_logger

logger = setup_logger("annotator")

def merge_nearby_boxes(ocr_boxes: list, vertical_threshold: int = 30, horizontal_threshold: int = 50) -> list:
    """
    Merge nearby OCR text boxes into larger answer regions.
    
    Args:
        ocr_boxes: List of OCR boxes from detect_text_boxes()
        vertical_threshold: Max vertical distance to consider boxes on same line
        horizontal_threshold: Max horizontal gap to merge boxes
        
    Returns:
        List of merged boxes with combined bboxes and text
    """
    if not ocr_boxes:
        return []
    
    # Sort boxes by vertical position (top to bottom)
    sorted_boxes = sorted(ocr_boxes, key=lambda b: b["bbox"][1])
    
    merged = []
    current_group = [sorted_boxes[0]]
    
    for box in sorted_boxes[1:]:
        last_box = current_group[-1]
        
        # Check if boxes are on same horizontal line (similar y-coordinate)
        y_diff = abs(box["bbox"][1] - last_box["bbox"][1])
        
        # Check horizontal gap
        x_gap = box["bbox"][0] - last_box["bbox"][2]
        
        if y_diff < vertical_threshold and x_gap < horizontal_threshold:
            # Add to current group
            current_group.append(box)
        else:
            # Save current group and start new one
            merged.append(merge_box_group(current_group))
            current_group = [box]
    
    # Don't forget the last group
    if current_group:
        merged.append(merge_box_group(current_group))
    
    return merged

def merge_box_group(boxes: list) -> dict:
    """Merge a group of boxes into one large box"""
    all_x_mins = [b["bbox"][0] for b in boxes]
    all_y_mins = [b["bbox"][1] for b in boxes]
    all_x_maxs = [b["bbox"][2] for b in boxes]
    all_y_maxs = [b["bbox"][3] for b in boxes]
    
    merged_bbox = [
        min(all_x_mins),
        min(all_y_mins),
        max(all_x_maxs),
        max(all_y_maxs)
    ]
    
    # Combine text
    merged_text = " ".join([b["text"] for b in boxes])
    
    return {
        "bbox": merged_bbox,
        "text": merged_text,
        "confidence": sum([b["confidence"] for b in boxes]) / len(boxes)
    }


def draw_annotations_with_ocr(image_path: Path, text_annotations: list, score: int = None, output_path: Path = None) -> Path:
    """
    Draw bounding boxes on image using OCR-detected text boxes matched with AI grading.
    
    Args:
        image_path: Path to the student's answer image
        text_annotations: List of text-based annotations from AI:
                         [{"text": "V = I × R", "label": "correct|mistake|partial|unclear"}]
        score: Optional score to display in a circle
        output_path: Optional custom output path
        
    Returns:
        Path to the annotated image
    """
    logger.info(f"Loading image with OCR: {image_path}")
    
    try:
        from utils.ocr_detector import detect_text_boxes, find_text_box
        
        # Load image
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)
        
        # Detect all text boxes using OCR
        logger.info("Running OCR to detect text boxes...")
        ocr_boxes = detect_text_boxes(image_path)
        logger.info(f"OCR detected {len(ocr_boxes)} text boxes")
        
        # Draw score circle in top-left corner if score is provided
        if score is not None:
            circle_radius = 60
            circle_center = (circle_radius + 20, circle_radius + 20)
            
            # Draw outer circle (background)
            draw.ellipse(
                [
                    (circle_center[0] - circle_radius, circle_center[1] - circle_radius),
                    (circle_center[0] + circle_radius, circle_center[1] + circle_radius)
                ],
                fill='white',
                outline='black',
                width=4
            )
            
            # Draw score text
            try:
                font = ImageFont.truetype("arial.ttf", 50)
            except:
                font = ImageFont.load_default()
            
            score_text = f"{score}/10"
            bbox = draw.textbbox((0, 0), score_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_position = (
                circle_center[0] - text_width // 2,
                circle_center[1] - text_height // 2
            )
            draw.text(text_position, score_text, fill='black', font=font)
        
        # Group nearby OCR boxes into answer regions
        logger.info(f"Merging {len(ocr_boxes)} OCR boxes into answer regions...")
        merged_boxes = merge_nearby_boxes(ocr_boxes, vertical_threshold=30, horizontal_threshold=50)
        logger.info(f"Merged into {len(merged_boxes)} answer regions")
        
        # Extract mistake keywords from annotations
        mistake_keywords = []
        for annotation in text_annotations:
            if annotation.get("label") == "mistake":
                text = annotation.get("text", "")
                if text:
                    # Extract key words (split by spaces)
                    words = text.split()
                    mistake_keywords.extend(words)
        
        logger.info(f"Mistake keywords: {mistake_keywords}")
        
        # Draw symbols instead of boxes
        for idx, merged_box in enumerate(merged_boxes):
            bbox = merged_box["bbox"]  # [x_min, y_min, x_max, y_max]
            merged_text = merged_box["text"]
            
            # Determine label: mistake/correct/partial
            label = "correct"  # Default
            for annotation in text_annotations:
                annot_label = annotation.get("label", "")
                annot_text = annotation.get("text", "")
                
                # Check if this merged text matches the annotation
                if annot_text and annot_text in merged_text:
                    label = annot_label
                    break
            
            # Skip if unclear
            if label == "unclear":
                continue
            
            # Determine color
            color_map = {
                "correct": "green",
                "mistake": "red",
                "partial": "yellow"
            }
            
            color_key = color_map.get(label, "green")
            color = ANNOTATION_COLORS.get(color_key, "green")
            
            # Calculate center position of the answer region
            center_x = (bbox[0] + bbox[2]) // 2
            center_y = (bbox[1] + bbox[3]) // 2
            
            # Draw background circle
            circle_radius = 25
            draw.ellipse(
                [
                    (center_x - circle_radius, center_y - circle_radius),
                    (center_x + circle_radius, center_y + circle_radius)
                ],
                fill='white',
                outline=color,
                width=3
            )
            
            # Draw the symbol as shapes
            if label == "correct":
                # Draw checkmark as two lines
                # Short vertical line
                draw.line(
                    [(center_x - 8, center_y), (center_x - 3, center_y + 10)],
                    fill=color,
                    width=4
                )
                # Longer diagonal line
                draw.line(
                    [(center_x - 3, center_y + 10), (center_x + 12, center_y - 8)],
                    fill=color,
                    width=4
                )
            elif label == "mistake":
                # Draw X as two diagonal lines
                draw.line(
                    [(center_x - 10, center_y - 10), (center_x + 10, center_y + 10)],
                    fill=color,
                    width=4
                )
                draw.line(
                    [(center_x + 10, center_y - 10), (center_x - 10, center_y + 10)],
                    fill=color,
                    width=4
                )
            elif label == "partial":
                # Draw exclamation mark
                # Top line
                draw.line(
                    [(center_x, center_y - 10), (center_x, center_y + 2)],
                    fill=color,
                    width=4
                )
                # Bottom dot
                draw.ellipse(
                    [(center_x - 2, center_y + 6), (center_x + 2, center_y + 10)],
                    fill=color
                )
            
            logger.debug(f"Drew {label} symbol for '{merged_text[:30]}...'")
        
        logger.info(f"Successfully drew {len(merged_boxes)} answer symbols")
        
        # Save annotated image
        if output_path is None:
            output_path = image_path.parent / f"annotated_{image_path.name}"
        
        image.save(output_path)
        logger.info(f"Saved annotated image to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error annotating image: {e}")
        raise

def create_color_legend(width: int = 300, height: int = 150) -> Image:
    """
    Create a small legend image explaining the color codes.
    
    Returns:
        PIL Image with color legend
    """
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    legend_items = [
        ("صحيح", "green"),
        ("خطأ", "red"),
        ("جزئي", "yellow"),
        ("غير واضح", "orange")
    ]
    
    y_offset = 20
    for text, color_key in legend_items:
        color = ANNOTATION_COLORS[color_key]
        # Draw colored box
        draw.rectangle([(10, y_offset), (40, y_offset + 20)], fill=color)
        # Draw text (using default font since Arabic requires special font handling)
        draw.text((50, y_offset), text, fill='black')
        y_offset += 30
    
    return img
