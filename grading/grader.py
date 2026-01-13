"""AI Grading Engine using Gemini 3 Pro with Thinking Mode

This module handles the core grading logic by sending student images and curriculum
context to Gemini 3 Pro and parsing the structured JSON response.
"""
import json
from pathlib import Path
from typing import Dict, List
import sys

from google import genai

sys.path.append(str(Path(__file__).parent.parent))
from config import GOOGLE_API_KEY, GEMINI_MODEL, THINKING_LEVEL, CURRICULUM_FILE, MAX_SCORE
from utils.logger import setup_logger

logger = setup_logger("grader")

class PhysicsGrader:
    """AI-powered physics grader using Gemini 3 Pro"""
    
    def __init__(self):
        """Initialize the Gemini client and upload curriculum PDFs"""
        logger.info("Initializing PhysicsGrader")
        
        # Initialize Gemini client
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        logger.info(f"Using model: {GEMINI_MODEL}")
        
        # Upload curriculum PDFs to Gemini (persistent files)
        self.curriculum_files = self._upload_curriculum_pdfs()
        logger.info("Curriculum PDFs uploaded successfully")
    
    def _upload_curriculum_pdfs(self) -> Dict:
        """Upload curriculum PDFs to Gemini as persistent files"""
        from .pdf_finder import find_curriculum_pdfs
        
        # Find PDFs by file size (avoids Arabic filename encoding issues)
        pdf_paths = find_curriculum_pdfs()
        
        if not pdf_paths:
            raise Exception("Curriculum PDFs not found!")
        
        uploaded_files = {}
        
        for category, pdf_path in pdf_paths.items():
            if not pdf_path.exists():
                logger.warning(f"PDF not found: {pdf_path}")
                continue
                
            logger.info(f"Uploading {category} ({pdf_path.stat().st_size // 1_000_000}MB)...")
            try:
                # Upload PDF file using path
                file_obj = self.client.files.upload(file=pdf_path)
                uploaded_files[category] = file_obj
                logger.info(f"✓ {category} uploaded successfully")
            except Exception as e:
                logger.error(f"Failed to upload {category}: {e}")

        if not uploaded_files:
            raise Exception("No curriculum PDFs could be uploaded!")
            
        return uploaded_files
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for grading"""
        
        
        prompt = f"""أنت "المعلم" (Al-Muallim)، مُصحح فيزياء دقيق جداً ومتسق.

## المنهج الدراسي (مرجع الإجابات):
لقد تم إرسال ملفات PDF الكاملة للمنهج الدراسي معك في هذه المحادثة. راجع هذه الملفات للحصول على الإجابات الصحيحة:
- ملف "الكلاميات": يحتوي على جميع الأسئلة النظرية والإجابات
- ملف "المسائل": يحتوي على جميع المسائل والحلول

**يجب عليك قراءة الملفات المرفقة بعناية قبل تقييم إجابة الطالب.**

## 📊 نظام النقاط المحدد (DETERMINISTIC SCORING - يجب الالتزام 100%):

### خطوة 1: عد الأسئلة
أولاً، احسب عدد الأسئلة الكلي في الصورة (N).

### خطوة 2: احسب النقاط لكل سؤال
كل سؤال يستحق (10 ÷ N) نقاط. مثال: إذا كان هناك 5 أسئلة، كل سؤال = 2 نقاط.

### خطوة 3: طبق القواعد التالية بدقة:
- ✅ **إجابة صحيحة كاملة** = النقاط الكاملة للسؤال
- ⚠️ **إجابة صحيحة جزئياً** = نصف نقاط السؤال
- ❌ **إجابة خاطئة** = 0 نقاط
- ⬜ **سؤال لم تتم إجابته** = 0 نقاط

### خطوة 4: اجمع النقاط
الدرجة النهائية = مجموع نقاط جميع الأسئلة (مقربة لأقرب رقم صحيح)

### مثال حسابي:
- 5 أسئلة، كل سؤال = 2 نقاط
- س1: صحيح = 2، س2: جزئي = 1، س3: خطأ = 0، س4: صحيح = 2، س5: ناقص = 0
- المجموع = 2+1+0+2+0 = 5/10

## قواعد التقييم المهمة (اقرأها بعناية):
1. **اقرأ السؤال بدقة** - اقرأ صورة السؤال أولاً لتفهم بالضبط ماذا يُطلب من الطالب
2. **راجع المنهج** - تحقق من المنهج الدراسي أعلاه للإجابة الصحيحة
3. **قارن بعناية** - قارن إجابة الطالب بالإجابة الصحيحة من المنهج
4. **تحقق مرتين** - قبل أن تحكم على إجابة، راجعها مرة أخرى

## ⚠️ قواعد الاتساق الصارمة (CRITICAL - يجب الالتزام 100%):

### 1. تعريف "السؤال الناقص" (Missing Question):
- السؤال الناقص = سؤال موجود في ورقة السؤال لكن لا توجد له إجابة في ورقة الطالب
- إذا كتب الطالب أي شيء للإجابة (حتى لو خاطئ)، فهو ليس ناقصاً
- **ممنوع منعاً باتاً**: ذكر سؤال في قسم "الناقص" وفي نفس الوقت وضع annotation له

### 2. قاعدة عدم التناقض (NO CONTRADICTIONS):
- إذا وضعت annotation بـ label="correct" → يجب ذكره في قسم "الصحيح" في feedback_ar
- إذا وضعت annotation بـ label="mistake" → يجب ذكره في قسم "الخاطئ" في feedback_ar
- إذا وضعت annotation بـ label="partial" → يجب ذكره في قسم "الجزئي" في feedback_ar
- **ممنوع**: إجابة تظهر في annotations لكن تُذكر في قسم "الناقص"
- **ممنوع**: إجابة بـ label="correct" لكن تُذكر في "الخاطئ"

### 3. خطوة التحقق الإجبارية (قبل الإرسال):
قبل أن ترسل JSON النهائي، تحقق من:
✓ كل annotation موجود في القسم الصحيح من feedback_ar
✓ لا يوجد أي سؤال مذكور في "الناقص" وله annotation
✓ عدد العناصر في "الصحيح" = عدد annotations بـ label="correct"
✓ عدد العناصر في "الخاطئ" = عدد annotations بـ label="mistake"

## مثال على عملية التقييم:
1. اقرأ السؤال: "س1-1: اختر الإجابة الصحيحة: الدائرة التي يتحقق فيها..."
2. اقرأ من المنهج: الإجابة الصحيحة هي "التوازي" لأن...
3. اقرأ إجابة الطالب: كتب "التوالي" بجانب س1-1
4. قارن: "التوالي" ≠ "التوازي" → خطأ
5. النتيجة: {{"text": "التوالي", "label": "mistake"}}
6. التحقق: السؤال مجاب (خطأ) لكن ليس ناقصاً!

## متطلبات الإخراج (JSON فقط):

{{
  "score": <رقم من 0 إلى {MAX_SCORE}>,
  "feedback_ar": "<نقاط واضحة ومباشرة>",
  "annotations": [
    {{
      "text": "<النص المكتوب - انسخه بدقة تامة>",
      "label": "correct|mistake|partial|unclear"
    }}
  ]
}}

## تعليمات annotations (حرجة للغاية):

### 1. انسخ النص بدقة:
- اكتب النص **بالضبط** كما هو مكتوب في الصورة
- لا تضف كلمات أو تحذف كلمات
- انسخ حتى الأخطاء الإملائية
- **مهم**: اكتب فقط نص الإجابة، لا تنسخ رقم السؤال

### 2. مثال صحيح:
إذا كان مكتوباً: "المقاومة والملف"
✓ صحيح: {{"text": "المقاومة والملف", "label": "correct"}}
✗ خاطئ: {{"text": "س1: المقاومة والملف", "label": "correct"}} (لا تضف رقم السؤال!)

### 3. حدد label بدقة:
- **correct**: صحيح 100%
- **mistake**: خاطئ
- **partial**: جزئياً صحيح
- **unclear**: غير واضح ولا يمكن قراءته

### 4. كل إجابة = annotation واحد:
- كل سطر أو فقرة إجابة = عنصر منفصل
- لا تدمج عدة أسطر في annotation واحد

## شكل feedback_ar (يجب أن يطابق annotations):

**الصحيح:**
• [قائمة فقط الإجابات التي label="correct"]

**الخاطئ:**
• [قائمة فقط الإجابات التي label="mistake"]

**الجزئي:**
• [قائمة فقط الإجابات التي label="partial"]

**الناقص:**
• [فقط الأسئلة التي لا توجد لها إجابة نهائياً - إذا كتب الطالب أي شيء فليست ناقصة!]

## مثال كامل:

{{
  "score": 7,
  "feedback_ar": "**الصحيح:**\\n• تحديد العوامل المؤثرة على الممانعة\\n• استخدام قانون عامل النوعية\\n\\n**الخاطئ:**\\n• اختيار دائرة التوالي في س2-1 (الصحيح: التوازي)\\n\\n**الناقص:**\\n• السؤال 3-2 لم تتم الإجابة عليه",
  "annotations": [
    {{"text": "R, L, C, f", "label": "correct"}},
    {{"text": "Qf = (1/R)√(L/C)", "label": "correct"}},
    {{"text": "التوالي", "label": "mistake"}},
    {{"text": "لأن المحث لا يستهلك طاقة", "label": "correct"}}
  ]
}}

## 🚨 تحذيرات نهائية حرجة:
⚠️ **ممنوع التناقض المطلق**: annotations و feedback_ar يجب أن يطابقان بعضهما 100%
⚠️ **السؤال الناقص ≠ الإجابة الخاطئة**: إذا كتب إجابة (حتى خاطئة)، فليست ناقصة!
⚠️ **راجع قبل الإرسال**: تأكد من قائمة التحقق أعلاه قبل إرسال JSON
⚠️ **انسخ النص بدقة**: text في annotations يجب أن يكون نسخة دقيقة 100% من الصورة
⚠️ **تحقق من كل قسم**: "الصحيح" و "الخاطئ" و "الجزئي" و "الناقص" يجب أن يطابق annotations
"""
        return prompt
    
    def grade_answer(
        self,
        question_image_path: Path,
        answer_image_path: Path
    ) -> Dict:
        """
        Grade a student's answer using Gemini 3 Pro with DETERMINISTIC OCR-first approach.
        
        The key insight: We extract text FIRST using Google Cloud Vision OCR (deterministic),
        then send the extracted TEXT to Gemini for grading. This ensures the same image
        always produces the same grade.
        
        Args:
            question_image_path: Path to the question image
            answer_image_path: Path to the student's answer image
            
        Returns:
            Dictionary with score, feedback_ar, and annotations
        """
        logger.info("Starting DETERMINISTIC grading process (OCR-first)")
        logger.info(f"Question: {question_image_path}")
        logger.info(f"Answer: {answer_image_path}")
        
        try:
            # STEP 1: Extract text using Google Cloud Vision OCR (DETERMINISTIC)
            from utils.ocr_detector import extract_full_text
            
            logger.info("Step 1: Extracting text via OCR (deterministic)...")
            question_text = extract_full_text(question_image_path)
            answer_text = extract_full_text(answer_image_path)
            
            logger.info(f"Question text extracted: {len(question_text)} chars")
            logger.info(f"Answer text extracted: {len(answer_text)} chars")
            
            # Log first 200 chars for debugging
            logger.debug(f"Question preview: {question_text[:200]}...")
            logger.debug(f"Answer preview: {answer_text[:200]}...")
            
            # STEP 2: Build prompt with TEXT (not images) for deterministic grading
            system_prompt = self._build_system_prompt()
            
            # Create request with curriculum PDFs + extracted text
            logger.info(f"Step 2: Sending TEXT to {GEMINI_MODEL} for grading...")
            
            # Build contents list with curriculum PDFs first
            contents = [system_prompt]
            
            # Add curriculum PDFs (we still need these for reference answers)
            for category, file_obj in self.curriculum_files.items():
                contents.append(file_obj)
            
            # Add EXTRACTED TEXT instead of images (THIS IS THE KEY CHANGE!)
            contents.extend([
                "النص التالي هو نص السؤال (تم استخراجه بواسطة OCR):",
                f"```\n{question_text}\n```",
                "والآن إليك نص إجابة الطالب (تم استخراجه بواسطة OCR):",
                f"```\n{answer_text}\n```",
                "ملاحظة مهمة: هذا النص تم استخراجه آلياً من صورة بخط اليد. قد تكون هناك أخطاء بسيطة في القراءة."
            ])
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config={
                    "temperature": 0.0,  # Zero temperature for deterministic grading
                    "response_mime_type": "application/json"
                }
            )
            
            # Parse response
            logger.info("Received response from Gemini")
            result_text = response.text
            
            # Parse JSON
            result = json.loads(result_text)
            
            logger.info(f"Grading complete. Score: {result.get('score', 'N/A')}/{MAX_SCORE}")
            logger.info(f"Annotations: {len(result.get('annotations', []))}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {result_text}")
            raise
        except Exception as e:
            logger.error(f"Grading error: {e}")
            raise

    def format_feedback_message(self, grading_result: Dict) -> str:
        """Format the grading result into a user-friendly message"""
        score = grading_result.get("score", 0)
        feedback = grading_result.get("feedback_ar", "")
        
        message = f"""🎯 النتيجة: {score}/{MAX_SCORE}

📝 الملاحظات:
{feedback}

✅ العلامات على الصورة المرفقة:
- ✓ أخضر: صحيح
- ✗ أحمر: خطأ
- ! أصفر: جزئي
"""
        return message
