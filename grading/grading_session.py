"""
Grading Session Module
======================
Manages grading sessions with Gemini context caching.
Creates a cached context (curriculum + exam) once per midterm,
then grades each student's ALL images in a single request.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import GOOGLE_API_KEY, GEMINI_MODEL
from utils.logger import setup_logger

logger = setup_logger("grading_session")


# System prompt for holistic grading
HOLISTIC_GRADING_PROMPT = """أنت "المعلم" (Al-Muallim)، مُصحح فيزياء متفهم وعادل.

## مهمتك:
أمامك ورقة امتحان (PDF) ومجموعة صور تحتوي على إجابات طالب واحد.

---

## 📋 الخطوة 1: تحليل هيكل الامتحان (من ملف PDF)

**قبل البدء بالتصحيح، اقرأ ملف الامتحان PDF وحدد:**

لكل سؤال رئيسي:
1. **عدد الفقرات الكلي** (مثل: 12 فقرة)
2. **عدد الفقرات المطلوب الإجابة عليها** (مثل: أجب عن 10)
3. **نوع السؤال:**
   - `multiple_parts` = فقرات متعددة (أجب عن X من Y)
   - `choose_one` = اختر واحداً فقط (نشاط أو تجربة)
   - `compulsory` = سؤال إجباري كامل
4. **احسب درجة كل فقرة:**
   - إذا كان `multiple_parts`: درجة الفقرة = 25 ÷ العدد المطلوب
   - إذا كان `choose_one`: درجة الخيار الواحد = 25 كاملة
   - إذا كان `compulsory`: الدرجة الكاملة = 25

**⚠️ قاعدة إجبارية:**
- تجاهل أي درجات مكتوبة في ورقة الامتحان!
- **كل سؤال رئيسي = 25 درجة بالضبط**
- **المجموع الكلي = 100 درجة (4 أسئلة × 25)**

---

## 🔍 الخطوة 2: تحديد رقم السؤال لكل صورة

### الطريقة الأولى: البحث عن علامات صريحة
ابحث عن علامات مثل: "س1" أو "ج1" أو "س1/4" أو "1-" أو "4/"

### الطريقة الثانية: مطابقة المحتوى (إذا لم توجد علامات)
**إذا لم يكتب الطالب رقم السؤال بوضوح:**
1. اقرأ محتوى الإجابة في الصورة
2. قارن المحتوى مع كل سؤال في الامتحان
3. حدد أي سؤال تنتمي إليه هذه الإجابة بناءً على الموضوع

---

## 📊 الخطوة 3: حساب درجة كل صورة

**استخدم الدرجات التي حسبتها في الخطوة 1:**

1. حدد رقم السؤال الذي تجيب عليه الصورة
2. عد عدد الفقرات/المسائل الصحيحة في الصورة
3. احسب: **درجة الصورة = عدد الإجابات الصحيحة × درجة الفقرة الواحدة**

**أمثلة (افتراضية - استخدم القيم التي حسبتها):**
- إذا كان س1 يتطلب 10 فقرات: درجة الفقرة = 2.5
  - صورة فيها 3 فقرات صحيحة → 3 × 2.5 = 7.5
- إذا كان س4 يتطلب 4 مسائل: درجة المسألة = 6.25
  - صورة فيها مسألة واحدة صحيحة → 1 × 6.25 = 6.25
- إذا كان س3 "اختر واحداً": أي نشاط صحيح = 25 كاملة

---

## ✅ قواعد التقييم:

### الفهم أهم من الحفظ:
✅ إذا شرح الطالب الفكرة بشكل صحيح بكلماته الخاصة → صحيح!
✅ إذا استخدم مصطلحات مختلفة لكن المعنى صحيح → صحيح!
❌ فقط إذا كان المفهوم أو المنطق خاطئ → خطأ!

### تجميع الإجابات:
- الطالب قد يجيب على أجزاء من السؤال في صور مختلفة
- اجمع كل الإجابات للسؤال الواحد من جميع الصور
- لا تعطِ درجة لنفس الفقرة مرتين

## المنهج الدراسي:
ملفات PDF المرفقة تحتوي على المفاهيم الصحيحة.

## متطلبات الإخراج (JSON فقط):

```json
{
  "exam_analysis": {
    "total_questions": 4,
    "total_points": 100,
    "questions": [
      {
        "number": <رقم>,
        "type": "<نوع>",
        "points": 25,
        "sub_count": <عدد الفقرات>,
        "required_count": <العدد المطلوب>,
        "requirement": "<المطلوب>"
      }
    ]
  },
  "student_grades": {
    "Q1": {
      "score": <درجة من 0 إلى 25>,
      "max_score": 25,
      "answered_parts": ["<الأجزاء التي أجاب عليها>"],
      "found_in_images": ["<أسماء الصور>"],
      "feedback": "<ملاحظات>"
    },
    "Q2": { "score": <0-25>, "max_score": 25, ... },
    "Q3": { "score": <0-25>, "max_score": 25, ... },
    "Q4": { "score": <0-25>, "max_score": 25, ... }
  },
  "image_annotations": {
    "<اسم الصورة>": {
      "question_number": <رقم السؤال>,
      "score": <مساهمة هذه الصورة في درجة السؤال>,
      "max_score": 25,
      "annotations": [
        {
          "text": "<أول 15-20 حرف من خط يد الطالب بالضبط>",
          "label": "correct|mistake|partial"
        }
      ]
    }
  },
  "total_score": <المجموع من 0 إلى 100>,
  "total_max": 100,
  "overall_feedback": "<ملاحظات عامة>"
}
```

### ⚠️ قواعد حساب درجة كل صورة (مهم جداً!):

**score في image_annotations = مساهمة هذه الصورة فقط في درجة السؤال**

مثال: السؤال الأول (س1) = 25 درجة، 10 فقرات مطلوبة، كل فقرة = 2.5 درجة
- صورة فيها 1 فقرة صحيحة → score: 2.5
- صورة فيها 3 فقرات صحيحة → score: 7.5
- صورة فيها 7 فقرات صحيحة → score: 17.5

مثال: السؤال الثاني (س2) = سؤال إجباري كامل = 25 درجة
- صورة فيها إجابة س2 كاملة صحيحة → score: 25

مثال: السؤال الثالث (س3) = اختر واحداً = 25 درجة
- صورة فيها نشاط واحد صحيح → score: 25

### ⚠️ قواعد التعليقات التوضيحية:
- **text**: يجب أن يكون **الحروف الأولى بالضبط** من خط يد الطالب
  - ✅ صحيح: "كلا لا يمكن لان" (نسخ حرفي من الصورة)
  - ❌ خطأ: "إجابة عن سبب عدم إمكانية" (ملخص أو وصف)
- **استخدم أول 15-20 حرف فقط** من كل إجابة كما كتبها الطالب حرفياً
- **label**: 
  - "correct" = إجابة صحيحة (✓)
  - "mistake" = إجابة خاطئة (✗)
  - "partial" = إجابة جزئية (~)

**تذكير: كل سؤال = 25 درجة، المجموع = 100 درجة!**


أرجع JSON فقط بدون أي نص إضافي.
"""


class GradingSession:
    """
    Manages a grading session with cached context.
    
    Usage:
        session = GradingSession.create(
            curriculum_pdfs=["kalamiat.pdf", "masael.pdf"],
            exam_pdf="exam.pdf",
            ttl_hours=24
        )
        result = session.grade_student(student_images)
        session.close()
    """
    
    def __init__(self, cache_name: str, client: genai.Client, exam_structure: dict = None):
        """Initialize with an existing cache"""
        self.cache_name = cache_name
        self.client = client
        self.exam_structure = exam_structure
        logger.info(f"GradingSession initialized with cache: {cache_name}")
    
    @classmethod
    def create(
        cls,
        curriculum_pdfs: List[Path],
        exam_pdf: Path,
        ttl_hours: int = 24,
        display_name: str = None
    ) -> 'GradingSession':
        """
        Create a new grading session with cached context.
        
        Args:
            curriculum_pdfs: List of paths to curriculum PDF files
            exam_pdf: Path to the exam PDF file
            ttl_hours: How long to keep the cache (default 24 hours)
            display_name: Optional name for the cache
            
        Returns:
            GradingSession instance
        """
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        logger.info("Creating grading session...")
        logger.info(f"Curriculum PDFs: {[p.name for p in curriculum_pdfs]}")
        logger.info(f"Exam PDF: {exam_pdf.name}")
        logger.info(f"TTL: {ttl_hours} hours")
        
        # Upload all files
        uploaded_files = []
        
        for pdf_path in curriculum_pdfs:
            logger.info(f"Uploading {pdf_path.name}...")
            file = client.files.upload(file=pdf_path)
            uploaded_files.append(file)
            logger.info(f"✓ {pdf_path.name} uploaded")
        
        logger.info(f"Uploading {exam_pdf.name}...")
        exam_file = client.files.upload(file=exam_pdf)
        uploaded_files.append(exam_file)
        logger.info(f"✓ {exam_pdf.name} uploaded")
        
        # Create cache with all context
        if display_name is None:
            display_name = f"midterm-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        ttl_seconds = ttl_hours * 3600
        
        logger.info(f"Creating cached context: {display_name}")
        
        cache = client.caches.create(
            model=GEMINI_MODEL,
            config=types.CreateCachedContentConfig(
                display_name=display_name,
                system_instruction=HOLISTIC_GRADING_PROMPT,
                contents=uploaded_files,
                ttl=f"{ttl_seconds}s"
            )
        )
        
        logger.info(f"✓ Cache created: {cache.name}")
        logger.info(f"  Expires: {cache.expire_time}")
        
        return cls(cache_name=cache.name, client=client)
    
    @classmethod
    def create_free_tier(
        cls,
        curriculum_pdfs: List[Path],
        exam_pdf: Path,
        display_name: str = None
    ) -> 'GradingSession':
        """
        Create a grading session WITHOUT context caching (for free tier API).
        
        Note: This uploads files each time but doesn't use caching.
        Works with Google AI Studio free API keys.
        
        Args:
            curriculum_pdfs: List of paths to curriculum PDF files
            exam_pdf: Path to the exam PDF file
            display_name: Optional name for logging
            
        Returns:
            GradingSession instance (with uploaded_files instead of cache)
        """
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        logger.info("Creating FREE TIER grading session (no caching)...")
        logger.info(f"Curriculum PDFs: {[p.name for p in curriculum_pdfs]}")
        logger.info(f"Exam PDF: {exam_pdf.name}")
        
        # Upload all files
        uploaded_files = []
        
        for pdf_path in curriculum_pdfs:
            logger.info(f"Uploading {pdf_path.name}...")
            file = client.files.upload(file=pdf_path)
            uploaded_files.append(file)
            logger.info(f"✓ {pdf_path.name} uploaded")
        
        # Upload exam PDF
        logger.info(f"Uploading {exam_pdf.name}...")
        exam_file = client.files.upload(file=exam_pdf)
        uploaded_files.append(exam_file)
        logger.info(f"✓ {exam_pdf.name} uploaded")
        
        logger.info(f"Free tier session ready with {len(uploaded_files)} files")
        
        # Create instance with files stored directly (no cache)
        instance = cls(cache_name=None, client=client)
        instance.uploaded_context_files = uploaded_files
        instance.is_free_tier = True
        return instance
    
    def grade_student(self, student_images: List[Path], output_dir: Path = None) -> Dict:
        """
        Grade a student's submission (all images at once) and annotate images.
        
        Args:
            student_images: List of paths to student answer images
            output_dir: Optional directory to save annotated images
            
        Returns:
            Dictionary with grades for each question, total, and annotated image paths
        """
        logger.info(f"Grading student with {len(student_images)} images")
        
        # Create output directory if needed
        if output_dir is None:
            output_dir = student_images[0].parent.parent / "graded_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a mapping of image name to path
        image_path_map = {img.name: img for img in student_images}
        
        # Upload student images
        uploaded_images = []
        image_names = []
        
        for img_path in student_images:
            logger.info(f"  Uploading: {img_path.name}")
            img_file = self.client.files.upload(file=img_path)
            uploaded_images.append(img_file)
            image_names.append(img_path.name)
        
        # Create grading request with image names for reference
        image_list = "\n".join([f"- {name}" for name in image_names])
        prompt = f"""قم بتصحيح إجابات هذا الطالب.

الصور المرفقة (بالترتيب):
{image_list}

حلل جميع الصور وأعطني درجة كل سؤال والمجموع مع التعليقات التوضيحية لكل صورة.
"""
        
        # Build contents list
        contents = uploaded_images + [prompt]
        
        logger.info("Sending grading request to Gemini...")
        
        # Check if we're in free tier mode (no cache)
        if getattr(self, 'is_free_tier', False):
            # Free tier: include context files directly in request
            all_contents = self.uploaded_context_files + contents
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=all_contents,
                config=types.GenerateContentConfig(
                    system_instruction=HOLISTIC_GRADING_PROMPT
                )
            )
        else:
            # Paid tier: use cached context
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    cached_content=self.cache_name
                )
            )
        
        logger.info(f"Response received. Usage: {response.usage_metadata}")
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Extract JSON from markdown code blocks if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        
        try:
            result = json.loads(response_text)
            self._log_results(result)
            
            # Annotate images if annotations are provided
            if "image_annotations" in result:
                annotated_paths = self._annotate_images(
                    result["image_annotations"],
                    image_path_map,
                    output_dir,
                    result.get("total_score", 0),
                    result.get("total_max", 100)
                )
                result["annotated_images"] = annotated_paths
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse grading response: {e}")
            logger.error(f"Raw response: {response_text[:1000]}")
            return {"error": str(e), "raw_response": response_text}
    
    def _annotate_images(
        self, 
        image_annotations: Dict, 
        image_path_map: Dict[str, Path],
        output_dir: Path,
        total_score: int,
        total_max: int
    ) -> Dict[str, Path]:
        """
        Annotate student images with checkmarks/X marks based on grading results.
        
        Args:
            image_annotations: Dict of {image_name: {annotations: [...]}}
            image_path_map: Dict of {image_name: Path}
            output_dir: Directory to save annotated images
            total_score: Student's total score
            total_max: Maximum possible score
            
        Returns:
            Dict of {image_name: annotated_image_path}
        """
        from grading.annotator import draw_annotations_with_ocr
        
        logger.info(f"Annotating {len(image_annotations)} images...")
        annotated_paths = {}
        running_total = 0
        
        for img_name, img_data in image_annotations.items():
            if img_name not in image_path_map:
                logger.warning(f"Image not found: {img_name}")
                continue
            
            img_path = image_path_map[img_name]
            annotations = img_data.get("annotations", [])
            score = img_data.get("score", 0)
            max_score = img_data.get("max_score", 25)
            running_total += score
            
            output_path = output_dir / f"graded_{img_name}"
            
            try:
                annotated_path = draw_annotations_with_ocr(
                    image_path=img_path,
                    text_annotations=annotations,
                    score=score,
                    max_score=max_score,
                    running_total=(running_total, total_max),
                    output_path=output_path
                )
                annotated_paths[img_name] = str(annotated_path)
                logger.info(f"  ✓ Annotated: {img_name}")
            except Exception as e:
                logger.error(f"  ✗ Failed to annotate {img_name}: {e}")
        
        logger.info(f"Annotation complete: {len(annotated_paths)} images annotated")
        return annotated_paths
    
    def _log_results(self, result: Dict):
        """Log grading results"""
        if "student_grades" in result:
            logger.info("=" * 50)
            logger.info("GRADING RESULTS")
            logger.info("=" * 50)
            
            for q_key, q_data in result.get("student_grades", {}).items():
                score = q_data.get("score", 0)
                max_score = q_data.get("max_score", 25)
                feedback = q_data.get("feedback", "")[:50]
                logger.info(f"  {q_key}: {score}/{max_score} - {feedback}...")
            
            total = result.get("total_score", 0)
            total_max = result.get("total_max", 100)
            logger.info(f"  TOTAL: {total}/{total_max}")
    
    def close(self):
        """Delete the cache to free resources"""
        try:
            self.client.caches.delete(name=self.cache_name)
            logger.info(f"Cache deleted: {self.cache_name}")
        except Exception as e:
            logger.warning(f"Failed to delete cache: {e}")
    
    @classmethod
    def list_active_sessions(cls) -> List[Dict]:
        """List all active grading sessions"""
        client = genai.Client(api_key=GOOGLE_API_KEY)
        sessions = []
        for cache in client.caches.list():
            sessions.append({
                "name": cache.name,
                "display_name": cache.display_name,
                "expire_time": cache.expire_time
            })
        return sessions


# Convenience function for quick grading
def grade_student_submission(
    curriculum_pdfs: List[Path],
    exam_pdf: Path,
    student_images: List[Path],
    ttl_hours: int = 24
) -> Dict:
    """
    One-shot function to grade a student's complete submission.
    
    Creates a session, grades the student, and returns results.
    For grading multiple students, use GradingSession directly to reuse the cache.
    """
    session = GradingSession.create(
        curriculum_pdfs=curriculum_pdfs,
        exam_pdf=exam_pdf,
        ttl_hours=ttl_hours
    )
    
    try:
        result = session.grade_student(student_images)
        return result
    finally:
        # Don't close session in case of reuse
        pass
