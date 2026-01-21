# Exam Structure Configuration
# This defines the structure of the specific exam being graded

EXAM_STRUCTURE = {
    "total_questions": 4,
    "total_points": 100,
    "points_per_question": 25,
    
    "questions": {
        1: {
            "type": "sub_questions",
            "description": "Theoretical questions about capacitors",
            "sub_question_count": 10,
            "answer_requirement": "all",  # Student must answer ALL 10
            "points_per_sub": 2.5,
            "total_points": 25
        },
        2: {
            "type": "comparison",
            "description": "Compare polar vs non-polar dielectrics",
            "sub_question_count": 1,
            "answer_requirement": "complete",  # One complete answer
            "points_per_sub": 25,
            "total_points": 25
        },
        3: {
            "type": "choose_one",
            "description": "Faraday experiment OR practical activity",
            "sub_question_count": 2,
            "answer_requirement": "choose_one",  # Answer ONLY 1 of 2 for full marks
            "points_per_sub": 25,  # Answering 1 correctly = full 25 points
            "total_points": 25
        },
        4: {
            "type": "math_problems",
            "description": "Capacitor circuit calculations",
            "sub_question_count": 5,
            "answer_requirement": "all",  # Answer all 5 problems
            "points_per_sub": 5,
            "total_points": 25
        }
    }
}

# Helper function to get grading instructions for a question
def get_question_instructions(question_num: int) -> str:
    """Get grading instructions for a specific question"""
    q = EXAM_STRUCTURE["questions"].get(question_num)
    if not q:
        return ""
    
    if q["answer_requirement"] == "choose_one":
        return f"""
🎯 السؤال {question_num}: اختر واحداً فقط!
- هذا السؤال يحتوي على {q['sub_question_count']} خيارات
- الطالب يجيب على واحد فقط للحصول على الدرجة الكاملة
- إذا أجاب بشكل صحيح على أي خيار = {q['total_points']}/25
"""
    elif q["answer_requirement"] == "complete":
        return f"""
🎯 السؤال {question_num}: إجابة كاملة مطلوبة
- هذا سؤال واحد متكامل
- إجابة صحيحة وكاملة = {q['total_points']}/25
"""
    else:  # "all"
        return f"""
🎯 السؤال {question_num}: {q['sub_question_count']} أسئلة فرعية
- كل سؤال فرعي = {q['points_per_sub']} نقطة
- الطالب يجيب على جميع الأسئلة الفرعية
- الدرجة = (عدد الإجابات الصحيحة × {q['points_per_sub']})
"""

def calculate_score(question_num: int, correct_count: int, partial_count: int = 0) -> float:
    """Calculate score for a question based on correct/partial answers"""
    q = EXAM_STRUCTURE["questions"].get(question_num)
    if not q:
        return 0
    
    if q["answer_requirement"] == "choose_one":
        # For "choose one" questions, 1 correct = full marks
        if correct_count >= 1:
            return q["total_points"]
        elif partial_count >= 1:
            return q["total_points"] / 2
        return 0
    
    elif q["answer_requirement"] == "complete":
        # For complete questions, check if fully correct
        if correct_count >= 1:
            return q["total_points"]
        elif partial_count >= 1:
            return q["total_points"] / 2
        return 0
    
    else:  # "all" - proportional scoring
        full_points = correct_count * q["points_per_sub"]
        partial_points = partial_count * (q["points_per_sub"] / 2)
        return min(full_points + partial_points, q["total_points"])
