"""OCR Text Detection Module

Uses EasyOCR to detect individual text lines in images with precise bounding boxes.
This provides pixel-perfect coordinates for annotation instead of AI-generated estimates.
"""
from pathlib import Path
from typing import List, Dict, Tuple
import sys

import easyocr

sys.path.append(str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("ocr_detector")

# Global OCR reader (cached for performance)
_reader = None

def get_ocr_reader():
    """Get or create cached OCR reader instance"""
    global _reader
    if _reader is None:
        logger.info("Initializing EasyOCR reader (this may take a moment on first run)...")
        # Initialize with Arabic and English, disable verbose to avoid Windows encoding errors
        _reader = easyocr.Reader(['ar', 'en'], gpu=False, verbose=False)
        logger.info("EasyOCR reader initialized successfully")
    return _reader

def detect_text_boxes(image_path: Path) -> List[Dict]:
    """
    Detect all text boxes in an image using OCR.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        List of dictionaries with format:
        [
            {
                "text": "detected text content",
                "bbox": [x_min, y_min, x_max, y_max],
                "confidence": 0.95
            },
            ...
        ]
    """
    logger.info(f"Detecting text boxes in: {image_path}")
    
    try:
        reader = get_ocr_reader()
        
        # Detect text with bounding boxes
        # readtext returns: [([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence)]
        results = reader.readtext(str(image_path))
        
        text_boxes = []
        for detection in results:
            bbox_points, text, confidence = detection
            
            # Convert polygon to bounding box [x_min, y_min, x_max, y_max]
            xs = [point[0] for point in bbox_points]
            ys = [point[1] for point in bbox_points]
            
            bbox = [
                int(min(xs)),  # x_min
                int(min(ys)),  # y_min
                int(max(xs)),  # x_max
                int(max(ys))   # y_max
            ]
            
            text_boxes.append({
                "text": text.strip(),
                "bbox": bbox,
                "confidence": confidence
            })
            
            logger.debug(f"Detected: '{text}' at {bbox} (confidence: {confidence:.2f})")
        
        logger.info(f"Detected {len(text_boxes)} text boxes")
        return text_boxes
        
    except Exception as e:
        logger.error(f"Error detecting text boxes: {e}")
        raise

def find_text_box(text_boxes: List[Dict], search_text: str, min_similarity: float = 0.6) -> Dict:
    """
    Find a text box that matches the search text using fuzzy matching.
    
    Args:
        text_boxes: List of detected text boxes from detect_text_boxes()
        search_text: Text to search for
        min_similarity: Minimum similarity score (0-1) to consider a match
        
    Returns:
        Best matching text box dict, or None if no match found
    """
    from difflib import SequenceMatcher
    
    best_match = None
    best_score = 0
    
    search_text_clean = search_text.strip().lower()
    
    for box in text_boxes:
        box_text_clean = box["text"].strip().lower()
        
        # Calculate similarity
        similarity = SequenceMatcher(None, search_text_clean, box_text_clean).ratio()
        
        if similarity > best_score and similarity >= min_similarity:
            best_score = similarity
            best_match = box
    
    if best_match:
        logger.debug(f"Found match for '{search_text}': '{best_match['text']}' (score: {best_score:.2f})")
    
    return best_match
