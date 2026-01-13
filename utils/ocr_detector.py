"""OCR Text Detection Module

Uses Google Cloud Vision API to detect individual text lines in images with precise bounding boxes.
This provides pixel-perfect coordinates for annotation instead of AI-generated estimates.
"""
from pathlib import Path
from typing import List, Dict
import sys
import os

sys.path.append(str(Path(__file__).parent.parent))
from utils.logger import setup_logger

logger = setup_logger("ocr_detector")

# Cached Vision client
_client = None

def get_vision_client():
    """Get or create cached Vision API client"""
    global _client
    if _client is None:
        logger.info("Initializing Google Cloud Vision client...")
        
        # Import here to avoid loading at module level
        from google.cloud import vision
        
        # Check for credentials file path in environment or project directory
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if not credentials_path:
            # Look for JSON key file in project directory
            project_dir = Path(__file__).parent.parent
            json_files = list(project_dir.glob("*.json"))
            
            # Filter for service account key files (they contain specific keys)
            for json_file in json_files:
                if "client" in json_file.name.lower() or json_file.name.startswith("gen-"):
                    credentials_path = str(json_file)
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                    logger.info(f"Found credentials file: {json_file.name}")
                    break
        
        if not credentials_path:
            raise Exception(
                "Google Cloud credentials not found! "
                "Please set GOOGLE_APPLICATION_CREDENTIALS environment variable "
                "or place your service account JSON file in the project directory."
            )
        
        _client = vision.ImageAnnotatorClient()
        logger.info("Google Cloud Vision client initialized successfully")
    
    return _client

def detect_text_boxes(image_path: Path) -> List[Dict]:
    """
    Detect all text boxes in an image using Google Cloud Vision OCR.
    
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
        from google.cloud import vision
        
        client = get_vision_client()
        
        # Read image file
        with open(image_path, "rb") as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        
        # Use document_text_detection for better handwriting support
        response = client.document_text_detection(
            image=image,
            image_context=vision.ImageContext(
                language_hints=["ar", "en"]  # Arabic and English
            )
        )
        
        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")
        
        text_boxes = []
        
        # Get word-level annotations for precise bounding boxes
        if response.full_text_annotation:
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    for paragraph in block.paragraphs:
                        # Get paragraph-level bounding box
                        vertices = paragraph.bounding_box.vertices
                        
                        # Extract coordinates
                        xs = [v.x for v in vertices]
                        ys = [v.y for v in vertices]
                        
                        bbox = [
                            min(xs),  # x_min
                            min(ys),  # y_min
                            max(xs),  # x_max
                            max(ys)   # y_max
                        ]
                        
                        # Build text from words
                        words = []
                        for word in paragraph.words:
                            word_text = "".join([
                                symbol.text for symbol in word.symbols
                            ])
                            words.append(word_text)
                        
                        text = " ".join(words)
                        
                        # Calculate average confidence
                        confidence = paragraph.confidence if hasattr(paragraph, 'confidence') else 0.9
                        
                        text_boxes.append({
                            "text": text.strip(),
                            "bbox": bbox,
                            "confidence": confidence
                        })
                        
                        logger.debug(f"Detected: '{text[:30]}...' at {bbox}")
        
        logger.info(f"Detected {len(text_boxes)} text boxes using Google Cloud Vision")
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


def extract_full_text(image_path: Path) -> str:
    """
    Extract all text from an image using Google Cloud Vision OCR.
    Returns a single string with all detected text, preserving line structure.
    
    This provides DETERMINISTIC text extraction - the same image will always
    return the same text, enabling consistent grading.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        String containing all detected text from the image
    """
    logger.info(f"Extracting full text from: {image_path}")
    
    try:
        from google.cloud import vision
        
        client = get_vision_client()
        
        # Read image file
        with open(image_path, "rb") as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        
        # Use document_text_detection for better handwriting support
        response = client.document_text_detection(
            image=image,
            image_context=vision.ImageContext(
                language_hints=["ar", "en"]  # Arabic and English
            )
        )
        
        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")
        
        # Get the full text annotation
        if response.full_text_annotation:
            full_text = response.full_text_annotation.text
            logger.info(f"Extracted {len(full_text)} characters of text")
            return full_text.strip()
        
        logger.warning("No text detected in image")
        return ""
        
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        raise

