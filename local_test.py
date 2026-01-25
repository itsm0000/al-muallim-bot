"""
Local Testing Script for Al-Muallim Bot
========================================
Tests the new context caching architecture:
1. Creates a grading session (caches curriculum + exam)
2. Grades ALL student images in a SINGLE request
3. Returns coherent per-question scores
"""

import sys
from pathlib import Path
import json

# Configure console for UTF-8 (Windows fix)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from grading.grading_session import GradingSession


def find_exam_pdf() -> Path:
    """Find the exam PDF file"""
    # Check for exam.pdf in root (ASCII-friendly name)
    root = Path(__file__).parent
    exam_simple = root / "exam.pdf"
    if exam_simple.exists():
        return exam_simple
    
    # Fall back to midtermpdf.tmp folder
    midterm_folder = root / "midtermpdf.tmp"
    if midterm_folder.exists():
        pdfs = list(midterm_folder.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
    
    raise FileNotFoundError("No exam PDF found! Place exam.pdf in project root.")


def find_curriculum_pdfs() -> list:
    """Find curriculum PDF files"""
    root = Path(__file__).parent
    
    # Check curriculum/ folder first (actual location)
    curriculum_folder = root / "curriculum"
    if curriculum_folder.exists():
        pdfs = list(curriculum_folder.glob("*.pdf"))
        if pdfs:
            return sorted(pdfs)
    
    # Fall back to curriculum_data/ folder
    curriculum_data_folder = root / "curriculum_data"
    if curriculum_data_folder.exists():
        pdfs = list(curriculum_data_folder.glob("*.pdf"))
        if pdfs:
            return sorted(pdfs)
    
    raise FileNotFoundError("No curriculum PDFs found in curriculum/ or curriculum_data/")


def main():
    print("=" * 60)
    print("AL-MUALLIM LOCAL TESTING - CONTEXT CACHING ARCHITECTURE")
    print("=" * 60)
    print()
    
    # Find files
    try:
        exam_pdf = find_exam_pdf()
        print(f"[OK] Exam PDF: {exam_pdf.name}")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return
    
    try:
        curriculum_pdfs = find_curriculum_pdfs()
        print(f"[OK] Curriculum PDFs: {[p.name for p in curriculum_pdfs]}")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return
    
    # Find student answer images
    test_images_folder = Path(__file__).parent / "test_images"
    if not test_images_folder.exists():
        print("[ERROR] test_images/ folder not found!")
        print("Create it and add student answer images (*.jpg, *.png)")
        return
    
    student_images = sorted(
        list(test_images_folder.glob("*.jpg")) + 
        list(test_images_folder.glob("*.png"))
    )
    
    if not student_images:
        print("[ERROR] No images found in test_images/")
        return
    
    print(f"[OK] Found {len(student_images)} student answer images:")
    for i, img in enumerate(student_images, 1):
        print(f"     {i}. {img.name}")
    
    print()
    print("=" * 60)
    print("PHASE 1: CREATING GRADING SESSION (Free Tier - No Caching)")
    print("=" * 60)
    print()
    
    # Create grading session (FREE TIER - no context caching)
    session = GradingSession.create_free_tier(
        curriculum_pdfs=curriculum_pdfs,
        exam_pdf=exam_pdf,
        display_name="local-test-session"
    )
    
    print()
    print("=" * 60)
    print("PHASE 2: GRADING STUDENT (Single Request)")
    print("=" * 60)
    print()
    
    # Grade all images at once
    result = session.grade_student(student_images)
    
    print()
    print("=" * 60)
    print("GRADING RESULTS")
    print("=" * 60)
    print()
    
    if "error" in result:
        print(f"[ERROR] Grading failed: {result['error']}")
        print(f"Raw response: {result.get('raw_response', 'N/A')[:500]}")
        return
    
    # Display exam analysis
    if "exam_analysis" in result:
        exam = result["exam_analysis"]
        print("EXAM STRUCTURE:")
        print(f"  Total Questions: {exam.get('total_questions', 'N/A')}")
        print(f"  Total Points: {exam.get('total_points', 'N/A')}")
        print()
        for q in exam.get("questions", []):
            print(f"  Q{q.get('number')}: {q.get('type')} | {q.get('points')} pts | {q.get('requirement')}")
        print()
    
    # Display student grades
    if "student_grades" in result:
        print("STUDENT GRADES:")
        print("-" * 40)
        for q_key, q_data in result["student_grades"].items():
            score = q_data.get("score", 0)
            max_score = q_data.get("max_score", 25)
            parts = q_data.get("answered_parts", [])
            images = q_data.get("found_in_images", [])
            feedback = q_data.get("feedback", "")
            
            print(f"  {q_key}: {score}/{max_score}")
            if parts:
                print(f"       Parts answered: {', '.join(str(p) for p in parts[:5])}...")
            if images:
                print(f"       Found in: {', '.join(images[:3])}...")
            if feedback:
                print(f"       Feedback: {feedback[:80]}...")
            print()
    
    # Display total
    total = result.get("total_score", "N/A")
    total_max = result.get("total_max", 100)
    print("-" * 40)
    print(f"  TOTAL: {total}/{total_max}")
    print()
    
    # Overall feedback
    if "overall_feedback" in result:
        print("OVERALL FEEDBACK:")
        print(f"  {result['overall_feedback'][:200]}...")
    
    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    # Save results to file
    output_file = Path(__file__).parent / "grading_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[OK] Full results saved to: {output_file}")


if __name__ == "__main__":
    main()
