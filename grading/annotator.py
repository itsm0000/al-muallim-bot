"""Image Annotation Module

Hand-drawn style annotations using Bezier curves with pressure simulation.
Blue checkmarks that look natural and teacher-like.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys
import math
import random

sys.path.append(str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("annotator")

# Hand-drawn annotation color (bright blue like teacher's pen)
HANDDRAWN_COLOR = (59, 158, 255)  # #3B9EFF


def bezier_point(t: float, p0: tuple, p1: tuple, p2: tuple) -> tuple:
    """Calculate point on quadratic Bezier curve at parameter t"""
    x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
    y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
    return (x, y)


def draw_bezier_with_pressure(draw: ImageDraw, p0: tuple, p1: tuple, p2: tuple, 
                               base_width: int = 8, steps: int = 30):
    """
    Draw a Bezier curve with variable width to simulate pen pressure.
    
    Pressure profile: thick at start -> thin in middle -> thick at end
    This mimics how a teacher draws a checkmark with pen pressure.
    """
    points = []
    for i in range(steps + 1):
        t = i / steps
        point = bezier_point(t, p0, p1, p2)
        points.append(point)
    
    # Draw line segments with varying width
    for i in range(len(points) - 1):
        t = i / (len(points) - 1)
        
        # Pressure curve: thick at ends, thin in middle
        # Using sine curve for smooth pressure variation
        pressure = 0.4 + 0.6 * (math.sin(t * math.pi) ** 0.5)
        width = max(3, int(base_width * pressure))
        
        # Add slight jitter for organic feel
        jitter_x = random.uniform(-1, 1) * 0.5
        jitter_y = random.uniform(-1, 1) * 0.5
        
        start = (points[i][0] + jitter_x, points[i][1] + jitter_y)
        end = (points[i+1][0] + jitter_x, points[i+1][1] + jitter_y)
        
        draw.line([start, end], fill=HANDDRAWN_COLOR, width=width)


def draw_handdrawn_checkmark(draw: ImageDraw, bbox: list, scale: float = 1.0):
    """
    Draw a natural-looking hand-drawn checkmark that spans across the answer region.
    
    The checkmark has two strokes:
    1. Short downward stroke (bottom of the check)
    2. Long upward sweep (the main check)
    
    Args:
        draw: ImageDraw object
        bbox: [x_min, y_min, x_max, y_max] of the answer region
        scale: Scale factor for the checkmark size
    """
    x_min, y_min, x_max, y_max = bbox
    width = x_max - x_min
    height = y_max - y_min
    
    # Calculate checkmark dimensions (span most of the answer region)
    check_width = min(width * 0.8, height * 1.2) * scale
    check_height = min(height * 0.9, width * 0.6) * scale
    
    # Position: slightly offset from center toward left
    center_x = x_min + width * 0.4
    center_y = y_min + height * 0.5
    
    # Key points of the checkmark
    # Start point (top of short stroke)
    start_x = center_x - check_width * 0.15
    start_y = center_y - check_height * 0.1
    
    # Bottom point (where the two strokes meet)
    bottom_x = center_x
    bottom_y = center_y + check_height * 0.4
    
    # End point (top right of the long sweep)
    end_x = center_x + check_width * 0.5
    end_y = center_y - check_height * 0.5
    
    # Add randomness for natural look
    jitter = lambda: random.uniform(-3, 3)
    
    # Stroke 1: Short downward stroke
    p0 = (start_x + jitter(), start_y + jitter())
    p1 = (start_x - 5 + jitter(), (start_y + bottom_y) / 2 + jitter())
    p2 = (bottom_x + jitter(), bottom_y + jitter())
    draw_bezier_with_pressure(draw, p0, p1, p2, base_width=10, steps=20)
    
    # Stroke 2: Long upward sweep
    p0 = (bottom_x + jitter(), bottom_y + jitter())
    p1 = ((bottom_x + end_x) / 2 + jitter(), (bottom_y + end_y) / 2 - check_height * 0.1 + jitter())
    p2 = (end_x + jitter(), end_y + jitter())
    draw_bezier_with_pressure(draw, p0, p1, p2, base_width=12, steps=35)


def draw_handdrawn_x(draw: ImageDraw, bbox: list, scale: float = 1.0):
    """
    Draw a natural-looking hand-drawn X mark for wrong answers.
    
    Args:
        draw: ImageDraw object
        bbox: [x_min, y_min, x_max, y_max] of the answer region
        scale: Scale factor
    """
    x_min, y_min, x_max, y_max = bbox
    width = x_max - x_min
    height = y_max - y_min
    
    # X dimensions (smaller than checkmark)
    x_size = min(width * 0.4, height * 0.6, 80) * scale
    
    # Center position
    center_x = x_min + width * 0.3
    center_y = y_min + height * 0.5
    
    jitter = lambda: random.uniform(-2, 2)
    
    # First stroke: top-left to bottom-right
    p0 = (center_x - x_size/2 + jitter(), center_y - x_size/2 + jitter())
    p1 = (center_x + jitter() * 2, center_y + jitter() * 2)
    p2 = (center_x + x_size/2 + jitter(), center_y + x_size/2 + jitter())
    draw_bezier_with_pressure(draw, p0, p1, p2, base_width=8, steps=20)
    
    # Second stroke: top-right to bottom-left
    p0 = (center_x + x_size/2 + jitter(), center_y - x_size/2 + jitter())
    p1 = (center_x + jitter() * 2, center_y + jitter() * 2)
    p2 = (center_x - x_size/2 + jitter(), center_y + x_size/2 + jitter())
    draw_bezier_with_pressure(draw, p0, p1, p2, base_width=8, steps=20)


def draw_handdrawn_partial(draw: ImageDraw, bbox: list, scale: float = 1.0):
    """
    Draw a curved line/squiggle for partial answers (half-credit).
    
    Args:
        draw: ImageDraw object
        bbox: [x_min, y_min, x_max, y_max] of the answer region
        scale: Scale factor
    """
    x_min, y_min, x_max, y_max = bbox
    width = x_max - x_min
    height = y_max - y_min
    
    # Wavy line dimensions
    wave_width = min(width * 0.5, 100) * scale
    wave_height = min(height * 0.3, 40) * scale
    
    center_x = x_min + width * 0.35
    center_y = y_min + height * 0.5
    
    jitter = lambda: random.uniform(-2, 2)
    
    # Draw a wavy underline with a small checkmark hook
    p0 = (center_x - wave_width/2 + jitter(), center_y + jitter())
    p1 = (center_x + jitter(), center_y - wave_height/2 + jitter())
    p2 = (center_x + wave_width/2 + jitter(), center_y - wave_height + jitter())
    draw_bezier_with_pressure(draw, p0, p1, p2, base_width=7, steps=25)

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


def draw_annotations_with_ocr(image_path: Path, text_annotations: list, score: int = None, 
                               max_score: int = 10, running_total: tuple = None, 
                               output_path: Path = None) -> Path:
    """
    Draw hand-drawn style annotations on image using OCR-detected text boxes.
    
    Args:
        image_path: Path to the student's answer image
        text_annotations: List of text-based annotations from AI:
                         [{"text": "V = I × R", "label": "correct|mistake|partial|unclear"}]
        score: Score for this question
        max_score: Maximum score for this question (default 10, can be 25 for midterms)
        running_total: Optional tuple of (current_total, max_total) for midterm mode
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
        
        # Draw score circle(s) in top-left corner
        if score is not None:
            _draw_score_circles(draw, score, max_score, running_total)
        
        # Group nearby OCR boxes into answer regions
        logger.info(f"Merging {len(ocr_boxes)} OCR boxes into answer regions...")
        merged_boxes = merge_nearby_boxes(ocr_boxes, vertical_threshold=30, horizontal_threshold=50)
        logger.info(f"Merged into {len(merged_boxes)} answer regions")
        
        # Draw hand-drawn marks for each answer region
        annotations_drawn = 0
        used_annotations = set()  # Track which annotations have been matched
        
        for idx, merged_box in enumerate(merged_boxes):
            bbox = merged_box["bbox"]  # [x_min, y_min, x_max, y_max]
            merged_text = merged_box["text"]
            
            # Determine label using FUZZY MATCHING (not exact substring)
            label = None
            best_match_score = 0.0
            best_annotation = None
            
            from difflib import SequenceMatcher
            
            for annot_idx, annotation in enumerate(text_annotations):
                if annot_idx in used_annotations:
                    continue  # Skip already-matched annotations
                    
                annot_label = annotation.get("label", "")
                annot_text = annotation.get("text", "").strip()
                
                if not annot_text:
                    continue
                
                # Calculate similarity between annotation text and OCR merged text
                merged_text_clean = merged_text.strip()
                
                # Try multiple matching approaches:
                # 1. Direct fuzzy match
                similarity1 = SequenceMatcher(None, annot_text.lower(), merged_text_clean.lower()).ratio()
                
                # 2. Check if annotation is substring (with normalization)
                substring_match = annot_text.lower() in merged_text_clean.lower()
                
                # 3. Check if OCR text contains most of the annotation words
                annot_words = set(annot_text.split())
                merged_words = set(merged_text_clean.split())
                word_overlap = len(annot_words & merged_words) / max(len(annot_words), 1)
                
                # Use the best matching approach
                similarity = max(similarity1, word_overlap, 0.9 if substring_match else 0.0)
                
                # Lower threshold for Arabic text (OCR differences are common)
                if similarity > best_match_score and similarity >= 0.4:
                    best_match_score = similarity
                    best_annotation = annotation
                    label = annot_label
                    best_annot_idx = annot_idx
            
            # Skip if no label found or unclear
            if label is None or label == "unclear":
                continue
            
            # Mark this annotation as used
            if best_annotation:
                used_annotations.add(best_annot_idx)
                logger.debug(f"Matched annotation '{best_annotation.get('text', '')[:30]}' to OCR '{merged_text[:30]}' (score: {best_match_score:.2f})")
            
            # Draw hand-drawn mark based on label
            if label == "correct":
                draw_handdrawn_checkmark(draw, bbox, scale=1.0)
            elif label == "mistake":
                draw_handdrawn_x(draw, bbox, scale=1.0)
            elif label == "partial":
                # Partial = checkmark but half grade (user requested same visual as correct)
                draw_handdrawn_checkmark(draw, bbox, scale=1.0)
            
            annotations_drawn += 1
            logger.debug(f"Drew hand-drawn {label} for '{merged_text[:30]}...'")
        
        logger.info(f"Successfully drew {annotations_drawn} hand-drawn annotations")
        
        # Save annotated image
        if output_path is None:
            output_path = image_path.parent / f"annotated_{image_path.name}"
        
        image.save(output_path)
        logger.info(f"Saved annotated image to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error annotating image: {e}")
        raise


def _draw_score_circles(draw: ImageDraw, score: int, max_score: int = 10, 
                        running_total: tuple = None):
    """
    Draw score circle(s) in the top-left corner.
    
    For midterm mode, draws two circles:
    - Circle 1: This question's score (e.g., "20/25")
    - Circle 2: Running total (e.g., "60/100")
    
    Args:
        draw: ImageDraw object
        score: Score for this question
        max_score: Maximum score for this question
        running_total: Optional tuple (current_total, max_total) for midterm mode
    """
    circle_radius = 90
    circle_center = (circle_radius + 20, circle_radius + 20)
    
    # Load font
    font = _get_score_font(72)
    small_font = _get_score_font(48)
    
    # Draw main score circle
    draw.ellipse(
        [
            (circle_center[0] - circle_radius, circle_center[1] - circle_radius),
            (circle_center[0] + circle_radius, circle_center[1] + circle_radius)
        ],
        fill='white',
        outline=HANDDRAWN_COLOR,
        width=5
    )
    
    # Draw score text
    score_text = f"{score}/{max_score}"
    bbox = draw.textbbox((0, 0), score_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_position = (
        circle_center[0] - text_width // 2,
        circle_center[1] - text_height // 2
    )
    draw.text(text_position, score_text, fill=HANDDRAWN_COLOR, font=font)
    
    # Draw running total circle if provided (for midterm mode)
    if running_total is not None:
        current_total, max_total = running_total
        
        # Position below main circle
        total_center = (circle_center[0], circle_center[1] + circle_radius * 2 + 30)
        total_radius = 70
        
        draw.ellipse(
            [
                (total_center[0] - total_radius, total_center[1] - total_radius),
                (total_center[0] + total_radius, total_center[1] + total_radius)
            ],
            fill='white',
            outline=HANDDRAWN_COLOR,
            width=4
        )
        
        total_text = f"{current_total}/{max_total}"
        bbox = draw.textbbox((0, 0), total_text, font=small_font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_position = (
            total_center[0] - text_width // 2,
            total_center[1] - text_height // 2
        )
        draw.text(text_position, total_text, fill=HANDDRAWN_COLOR, font=small_font)


def _get_score_font(size: int) -> ImageFont:
    """Get font for score display, trying multiple system fonts."""
    font_options = [
        "arial.ttf",           # Windows
        "Arial.ttf",           # Windows (case variant)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux (common)
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux (Ubuntu)
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",  # Linux (Arch)
        "DejaVuSans-Bold.ttf",  # Fallback name
    ]
    
    for font_path in font_options:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue
    
    # Fallback to default
    logger.warning("Using default font - score may appear small")
    return ImageFont.load_default()

def create_color_legend(width: int = 300, height: int = 150) -> Image:
    """
    Create a small legend image explaining the hand-drawn marks.
    
    Returns:
        PIL Image with legend
    """
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # All marks are now blue hand-drawn style
    legend_items = [
        ("✓ صحيح", "Checkmark"),
        ("✗ خطأ", "X mark"),
        ("~ جزئي", "Wave")
    ]
    
    y_offset = 20
    for text, desc in legend_items:
        # Draw blue sample mark
        draw.rectangle([(10, y_offset), (40, y_offset + 20)], fill=HANDDRAWN_COLOR)
        # Draw text
        draw.text((50, y_offset), text, fill='black')
        y_offset += 40
    
    return img
