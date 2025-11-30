"""PDF Curriculum Ingestion Script

This script extracts text from the physics curriculum PDFs and stores them
in a structured JSON format for use by the grading bot.
"""
import json
import pdfplumber
from pathlib import Path
import sys

# Add parent directory to path to import config
sys.path.append(str(Path(__file__).parent.parent))
from config import CURRICULUM_DATA_DIR
from utils.logger import setup_logger

logger = setup_logger("curriculum_ingest")

# PDF paths (relative to project root)
PDF_PATHS = {
    "الكلاميات": Path(__file__).parent.parent.parent / "فتح_فتح__⁨حسين_محمد_الكلاميات_2025⁩_2.pdf",
    "المسائل": Path(__file__).parent.parent.parent / "فتح_فتح__⁨حسين_محمد_المسائل_2025⁩.pdf"
}

def extract_pdf_text(pdf_path: Path) -> list:
    """
    Extract text from PDF file page by page.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        List of dictionaries with page number and text content
    """
    logger.info(f"Processing PDF: {pdf_path.name}")
    pages_data = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Total pages: {total_pages}")
            
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    pages_data.append({
                        "page_num": page_num,
                        "text": text.strip()
                    })
                    logger.debug(f"Extracted page {page_num}/{total_pages}")
                else:
                    logger.warning(f"No text found on page {page_num}")
                    
        logger.info(f"Successfully extracted {len(pages_data)} pages from {pdf_path.name}")
        return pages_data
        
    except Exception as e:
        logger.error(f"Error processing {pdf_path.name}: {e}")
        raise

def main():
    """Main ingestion function"""
    logger.info("=" * 50)
    logger.info("Starting Curriculum Ingestion")
    logger.info("=" * 50)
    
    curriculum_data = {}
    
    for category, pdf_path in PDF_PATHS.items():
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            logger.error(f"Please ensure the PDF is in the correct location")
            continue
            
        curriculum_data[category] = {
            "source_file": pdf_path.name,
            "pages": extract_pdf_text(pdf_path)
        }
    
    # Save to JSON
    output_path = CURRICULUM_DATA_DIR / "curriculum.json"
    logger.info(f"Saving curriculum data to: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(curriculum_data, f, ensure_ascii=False, indent=2)
    
    logger.info("=" * 50)
    logger.info("Curriculum Ingestion Complete!")
    logger.info(f"Output: {output_path}")
    logger.info("=" * 50)
    
    # Print summary
    for category, data in curriculum_data.items():
        logger.info(f"{category}: {len(data['pages'])} pages extracted")

if __name__ == "__main__":
    main()
