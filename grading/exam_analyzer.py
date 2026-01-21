"""
Exam Analyzer Module
====================
Analyzes an exam PDF to extract its structure before grading.
This enables dynamic, exam-agnostic grading.
"""

import json
from pathlib import Path
from typing import Dict, Optional
from google import genai

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import GOOGLE_API_KEY, GEMINI_MODEL
from utils.logger import setup_logger

logger = setup_logger("exam_analyzer")

# Cache for analyzed exams (path -> structure)
_exam_cache: Dict[str, dict] = {}

ANALYSIS_PROMPT = """أنت محلل امتحانات ذكي. مهمتك تحليل ورقة الأسئلة المرفقة واستخراج هيكلها بدقة.

## المطلوب:
حلل ورقة الامتحان واستخرج المعلومات التالية بتنسيق JSON:

```json
{
  "total_questions": <عدد الأسئلة الرئيسية>,
  "total_points": <مجموع الدرجات>,
  "questions": [
    {
      "number": <رقم السؤال>,
      "title": "<عنوان أو موضوع السؤال>",
      "type": "<نوع السؤال>",
      "sub_count": <عدد الأسئلة الفرعية أو الفقرات>,
      "points": <درجة السؤال>,
      "requirement": "<ما المطلوب من الطالب>",
      "special_instructions": "<أي تعليمات خاصة مثل 'اختر واحداً' أو 'أجب عن جميع'>"
    }
  ]
}
```

## أنواع الأسئلة الممكنة:
- "theoretical": أسئلة نظرية تتطلب شرح أو تعريف
- "comparison": مقارنة بين مفهومين أو أكثر
- "experiment": تجربة أو نشاط عملي
- "math": مسائل حسابية
- "choose_one": اختر واحداً من عدة خيارات
- "mixed": نوع مختلط

## تعليمات مهمة:
1. ابحث عن عبارات مثل "اختر" أو "أجب عن واحد فقط" أو "أحد الخيارين"
2. إذا وجدت "اختر واحداً" أو ما يشابهها، ضع requirement: "choose_one"
3. احسب عدد الأسئلة الفرعية بدقة (1-، 2-، أ)، ب)، إلخ)
4. إذا لم تحدد الدرجات، افترض توزيعاً متساوياً
5. بالنسبة للأسئلة من نوع "choose_one"، ضع sub_count كعدد الخيارات المتاحة

## مثال على الإخراج:
```json
{
  "total_questions": 4,
  "total_points": 100,
  "questions": [
    {
      "number": 1,
      "title": "أسئلة نظرية عن المتسعات",
      "type": "theoretical",
      "sub_count": 10,
      "points": 25,
      "requirement": "answer_all",
      "special_instructions": "أجب عن جميع الفقرات"
    },
    {
      "number": 2,
      "title": "مقارنة العوازل",
      "type": "comparison",
      "sub_count": 1,
      "points": 25,
      "requirement": "complete",
      "special_instructions": null
    },
    {
      "number": 3,
      "title": "تجربة أو نشاط",
      "type": "choose_one",
      "sub_count": 2,
      "points": 25,
      "requirement": "choose_one",
      "special_instructions": "اختر أحد الخيارين فقط للحصول على الدرجة الكاملة"
    }
  ]
}
```

أرجع JSON فقط بدون أي نص إضافي.
"""


class ExamAnalyzer:
    """Analyzes exam PDFs to extract structure for grading"""
    
    def __init__(self):
        """Initialize the Gemini client"""
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        logger.info("ExamAnalyzer initialized")
    
    def analyze_exam(self, exam_path: Path, force_refresh: bool = False) -> dict:
        """
        Analyze an exam PDF and extract its structure.
        
        Args:
            exam_path: Path to the exam PDF
            force_refresh: If True, re-analyze even if cached
            
        Returns:
            Dictionary with exam structure
        """
        path_key = str(exam_path)
        
        # Check cache first
        if not force_refresh and path_key in _exam_cache:
            logger.info(f"Using cached analysis for: {exam_path.name}")
            return _exam_cache[path_key]
        
        logger.info(f"Analyzing exam: {exam_path.name}")
        
        try:
            # Upload the PDF
            exam_file = self.client.files.upload(file=exam_path)
            logger.info("Exam PDF uploaded to Gemini")
            
            # Send analysis request
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    exam_file,
                    ANALYSIS_PROMPT
                ]
            )
            
            # Parse JSON response
            response_text = response.text.strip()
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            structure = json.loads(response_text)
            
            # Cache the result
            _exam_cache[path_key] = structure
            
            logger.info(f"Exam analysis complete: {structure.get('total_questions')} questions")
            self._log_structure(structure)
            
            return structure
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse exam structure JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            return self._get_default_structure()
        except Exception as e:
            logger.error(f"Error analyzing exam: {e}")
            return self._get_default_structure()
    
    def _log_structure(self, structure: dict):
        """Log the extracted structure for debugging"""
        logger.info(f"Total questions: {structure.get('total_questions')}")
        logger.info(f"Total points: {structure.get('total_points')}")
        for q in structure.get("questions", []):
            req = q.get("requirement", "answer_all")
            special = q.get("special_instructions", "")
            logger.info(
                f"  Q{q['number']}: {q['title'][:30] if 'title' in q else 'No title'} | "
                f"{q['type']} | {q['sub_count']} subs | "
                f"{q['points']} pts | {req} | {special[:30] if special else 'none'}"
            )
    
    def _get_default_structure(self) -> dict:
        """Return a safe default structure if analysis fails"""
        return {
            "total_questions": 4,
            "total_points": 100,
            "questions": [
                {"number": i, "type": "mixed", "sub_count": 5, 
                 "points": 25, "requirement": "answer_all", "special_instructions": None}
                for i in range(1, 5)
            ]
        }
    
    def get_grading_context(self, structure: dict) -> str:
        """
        Generate grading context string from exam structure.
        This will be included in the grading prompt.
        """
        context_lines = [
            "## 🎯 هيكل الامتحان (تم استخراجه تلقائياً):",
            f"- **عدد الأسئلة الرئيسية**: {structure.get('total_questions', 4)}",
            f"- **مجموع الدرجات**: {structure.get('total_points', 100)}",
            ""
        ]
        
        for q in structure.get("questions", []):
            q_num = q.get("number", "?")
            q_type = q.get("type", "mixed")
            sub_count = q.get("sub_count", 1)
            points = q.get("points", 25)
            requirement = q.get("requirement", "answer_all")
            special = q.get("special_instructions", "")
            
            context_lines.append(f"### السؤال {q_num}:")
            context_lines.append(f"- **النوع**: {q_type}")
            context_lines.append(f"- **عدد الفقرات/الأجزاء**: {sub_count}")
            context_lines.append(f"- **الدرجة**: {points}")
            
            # Special handling for choose_one - FIXED
            if requirement == "choose_one":
                context_lines.append(f"- **⚠️ مهم**: هذا سؤال من نوع 'اختر واحداً'")
                context_lines.append(f"- **المطلوب**: الطالب يختار خياراً واحداً فقط من {sub_count} خيارات!")
                context_lines.append(f"- **توزيع الدرجات**: إذا أجاب الطالب على خيار واحد بشكل كامل وصحيح = {points} نقطة كاملة!")
                context_lines.append(f"- **⚠️ تحذير**: لا تقسم الدرجة على عدد الخيارات. إذا أجاب على خيار واحد فقط بشكل صحيح = {points}/{points}")
                context_lines.append(f"- **إذا أجاب على أكثر من خيار**: خذ أول خيار فقط واعطيه {points} نقطة إذا كان صحيحاً")
            elif requirement == "complete":
                context_lines.append(f"- **المطلوب**: إجابة كاملة متكاملة")
            else:
                points_per_sub = points / sub_count if sub_count > 0 else points
                context_lines.append(f"- **المطلوب**: الإجابة على جميع الفقرات")
                context_lines.append(f"- **كل فقرة = {points_per_sub:.1f} نقطة**")
            
            if special:
                context_lines.append(f"- **ملاحظة خاصة**: {special}")
            
            context_lines.append("")
        
        return "\n".join(context_lines)


# Singleton instance
_analyzer: Optional[ExamAnalyzer] = None

def get_analyzer() -> ExamAnalyzer:
    """Get or create the exam analyzer singleton"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ExamAnalyzer()
    return _analyzer


def analyze_exam(exam_path: Path, force_refresh: bool = False) -> dict:
    """Convenience function to analyze an exam"""
    return get_analyzer().analyze_exam(exam_path, force_refresh)


def get_grading_context(exam_path: Path) -> str:
    """Get grading context for an exam (analyzes if needed)"""
    structure = analyze_exam(exam_path)
    return get_analyzer().get_grading_context(structure)
