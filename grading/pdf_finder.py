"""Simplified PDF Upload Helper

Uses simple English filenames to avoid Unicode encoding issues.
"""
from pathlib import Path

def find_curriculum_pdfs():
    """Find curriculum PDFs in curriculum directory"""
    curriculum_dir = Path(__file__).parent.parent / "curriculum"
    
    # Use simple English filenames
    result = {
        "kalamiat": curriculum_dir / "curriculum1.pdf",  # 41MB - الكلاميات
        "masael": curriculum_dir / "curriculum2.pdf"     # 23MB - المسائل
}
    
    # Verify files exist
    for category, path in list(result.items()):
        if not path.exists():
            del result[category]
    
    return result
