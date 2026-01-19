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
    
    def _build_system_prompt(self, max_score: int = 10, total_questions: int = None) -> str:
        """Build the system prompt for grading with configurable max score
        
        Args:
            max_score: Maximum score for this question
            total_questions: Total number of questions in midterm (for validation)
        """
        
        # Add question detection instructions for midterm mode
        question_detection_note = ""
        if total_questions:
            question_detection_note = f"""
## 🔢 تحديد رقم السؤال الرئيسي (مهم جداً!):

**⚠️ تحذير مهم: فرّق بين الأسئلة الرئيسية والأسئلة الفرعية!**

هذا الامتحان يحتوي على {total_questions} أسئلة رئيسية فقط (Q1, Q2, Q3, Q4 أو س1، س2، س3، س4).

### كيف تحدد السؤال الرئيسي:
ابحث عن علامات السؤال الرئيسي **صراحةً**:
- "س1" أو "السؤال الأول" أو "Q1" ← سؤال رئيسي 1
- "س2" أو "السؤال الثاني" أو "Q2" ← سؤال رئيسي 2
- وهكذا...

### ⚠️ لا تخلط بين الأسئلة الفرعية والأسئلة الرئيسية!
إذا رأيت أرقاماً مثل "1-"، "2-"، "3-"، "أ)"، "ب)" داخل الإجابة:
- هذه **أسئلة فرعية** ضمن سؤال رئيسي واحد
- **لا تعتبرها** أسئلة رئيسية منفصلة!
- إذا لم يذكر الطالب رقم السؤال الرئيسي صراحةً، أرجع [1] كافتراضي

### مثال:
- الطالب كتب: "1- ... 2- ... 3- ..." ← هذه إجابات على أسئلة فرعية ضمن سؤال رئيسي واحد
- أرجع: [1] (سؤال رئيسي واحد فقط)
- **لا ترجع** [1,2,3] لأن هذه ستعني 3 أسئلة رئيسية!

**أرقام الأسئلة الصالحة**: 1 إلى {total_questions} فقط
"""
        
        prompt = f"""أنت "المعلم" (Al-Muallim)، مُصحح فيزياء متفهم وعادل.

## 🎯 فلسفة التصحيح: الفهم أهم من الحفظ!

**قاعدة ذهبية**: لا تقارن النص حرفياً! قيّم بناءً على **فهم الطالب للمفهوم**.

✅ إذا شرح الطالب الفكرة بشكل صحيح **بكلماته الخاصة** → صحيح!
✅ إذا استخدم مصطلحات مختلفة لكن المعنى صحيح → صحيح!
✅ إذا الإجابة تدل على فهم المفهوم العلمي → صحيح!
❌ فقط إذا كان المفهوم أو المنطق خاطئ → خطأ!
{question_detection_note}
## المنهج الدراسي (للمرجعية فقط):
ملفات PDF المرفقة تحتوي على المفاهيم الصحيحة. استخدمها لفهم ما يجب أن يعرفه الطالب، لكن **لا تتوقع أن ينسخ الطالب النص حرفياً**.

## 📊 نظام النقاط (الدرجة القصوى: {max_score}):

### تحديد عدد الأسئلة الفرعية:
1. انظر إلى ورقة السؤال وعدّ الأسئلة الفرعية (T)
2. كل سؤال فرعي = {max_score} ÷ T نقاط

### معايير التقييم:
- **correct** ✅: الطالب يفهم المفهوم ويشرحه بشكل صحيح (حتى لو بأسلوبه الخاص)
- **partial** ⚠️: فهم جزئي - بعض الأفكار صحيحة وبعضها ناقص
- **mistake** ❌: المفهوم خاطئ أو المنطق خاطئ تماماً
- **unclear** ❔: لا يمكن قراءة الخط

### أمثلة على التقييم الصحيح:

**مثال 1 - يجب أن يكون correct:**
- السؤال: ما هي العوامل المؤثرة في المقاومة؟
- إجابة المنهج: "طول السلك، مساحة المقطع، نوع المادة، درجة الحرارة"
- إجابة الطالب: "المقاومة تعتمد على طول الموصل وثخانته والمادة المصنوع منها"
- ✅ **صحيح!** الطالب يفهم المفهوم حتى لو استخدم كلمات مختلفة

**مثال 2 - يجب أن يكون mistake:**
- السؤال: في أي دائرة تتحقق حالة الرنين؟
- الإجابة الصحيحة: دائرة RLC المتوالية
- إجابة الطالب: "دائرة التوازي فقط"
- ❌ **خطأ!** المفهوم نفسه خاطئ

**مثال 3 - يجب أن يكون partial:**
- السؤال: اشرح ظاهرة الرنين الكهربائي
- إجابة الطالب: "هي الظاهرة التي تصل فيها التيار لأعلى قيمة" (صحيح لكن ناقص)
- ⚠️ **جزئي!** فهم جزء من المفهوم لكن لم يذكر الشروط

## متطلبات الإخراج (JSON فقط):

{{
  "score": <رقم من 0 إلى {max_score}>,
  "question_numbers": [<قائمة أرقام الأسئلة التي يجيب عليها الطالب، مثال: [1] أو [2,3]>],
  "feedback_ar": "<ملاحظات مختصرة>",
  "annotations": [
    {{
      "text": "<انسخ نص إجابة الطالب بالضبط>",
      "label": "correct|mistake|partial|unclear"
    }}
  ]
}}

**ملاحظة مهمة**: حقل "question_numbers" إجباري! إذا لم تستطع تحديد رقم السؤال، أرجع [1] كافتراضي.

## تعليمات annotations:

### 1. انسخ نص الإجابة بدقة:
- انسخ ما كتبه الطالب **بالضبط** كما يظهر
- هذا لمطابقة الموقع على الصورة، ليس للتقييم

### 2. قيّم المفهوم وليس الكلمات:
- **لا تقارن النص حرفياً بالمنهج**
- اسأل: هل الطالب يفهم الفكرة؟ هل المنطق صحيح؟

### 3. كن كريماً مع الإجابات الجيدة:
- إذا الجوهر صحيح → correct
- إذا جزء صحيح وجزء ناقص → partial  
- فقط إذا خطأ مفهومي واضح → mistake

## ⚠️ تحذير مهم:
**لا تكن صارماً جداً!** الطالب ليس مطلوباً منه أن يحفظ النص. 
إذا أظهر فهماً للمفهوم العلمي، أعطه الدرجة.
"""
        return prompt
    
    def grade_answer(
        self,
        question_image_path: Path,
        answer_image_path: Path,
        max_score: int = 10,
        total_questions: int = None
    ) -> Dict:
        """
        Grade a student's answer using Gemini 3 Pro with DETERMINISTIC OCR-first approach.
        
        The key insight: We extract text FIRST using Google Cloud Vision OCR (deterministic),
        then send the extracted TEXT to Gemini for grading. This ensures the same image
        always produces the same grade.
        
        Args:
            question_image_path: Path to the question image
            answer_image_path: Path to the student's answer image
            max_score: Maximum score for this answer (default 10, can be 25 for midterms)
            total_questions: Total number of questions in midterm (for AI question detection)
            
        Returns:
            Dictionary with score, question_numbers, feedback_ar, and annotations
        """
        logger.info(f"Starting grading process (max_score={max_score}, total_questions={total_questions})")
        logger.info(f"Question: {question_image_path}")
        logger.info(f"Answer: {answer_image_path}")
        
        try:
            from utils.ocr_detector import extract_full_text
            
            # Check if question is a PDF (PDFs can't be OCR'd, but Gemini supports them directly)
            is_question_pdf = str(question_image_path).lower().endswith('.pdf')
            
            # STEP 1: Handle question file based on type
            if is_question_pdf:
                logger.info("Step 1: Question is PDF - will upload directly to Gemini")
                # Upload PDF to Gemini for this request
                question_file = self.client.files.upload(file=question_image_path)
                question_content = question_file  # Pass file object directly
                question_text = None  # No OCR text for PDF
            else:
                logger.info("Step 1: Question is image - extracting text via OCR...")
                question_text = extract_full_text(question_image_path)
                question_content = None  # No file object for images
                logger.info(f"Question text extracted: {len(question_text)} chars")
            
            # STEP 2: Extract text from student answer (always an image)
            logger.info("Step 2: Extracting student answer text via OCR...")
            answer_text = extract_full_text(answer_image_path)
            logger.info(f"Answer text extracted: {len(answer_text)} chars")
            
            # Log preview for debugging
            if question_text:
                logger.debug(f"Question preview: {question_text[:200]}...")
            logger.debug(f"Answer preview: {answer_text[:200]}...")
            
            # STEP 3: Build prompt and send to Gemini
            system_prompt = self._build_system_prompt(max_score=max_score, total_questions=total_questions)
            logger.info(f"Step 3: Sending to {GEMINI_MODEL} for grading...")
            
            # Build contents list with curriculum PDFs first
            contents = [system_prompt]
            
            # Add curriculum PDFs (reference answers)
            for category, file_obj in self.curriculum_files.items():
                contents.append(file_obj)
            
            # Add question content (either PDF file or OCR text)
            if is_question_pdf and question_content:
                contents.extend([
                    "الملف التالي هو ملف السؤال (PDF):",
                    question_content,
                ])
            else:
                contents.extend([
                    "النص التالي هو نص السؤال (تم استخراجه بواسطة OCR):",
                    f"```\n{question_text}\n```",
                ])
            
            # Add student answer (always OCR text)
            contents.extend([
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
            
            # Detailed logging for debugging (server-side only, not visible to students)
            logger.info(f"Grading complete. Score: {result.get('score', 'N/A')}/{max_score}")
            logger.info(f"Detected question numbers: {result.get('question_numbers', [])}")
            logger.info(f"Annotations: {len(result.get('annotations', []))}")
            
            # Log each annotation's label for debugging
            for i, annot in enumerate(result.get('annotations', [])):
                label = annot.get('label', 'unknown')
                text_preview = annot.get('text', '')[:40]
                logger.info(f"  Annotation {i+1}: [{label}] '{text_preview}...'")
            
            # Log feedback summary
            feedback = result.get('feedback_ar', '')
            if feedback:
                logger.info(f"Feedback preview: {feedback[:100]}...")
            
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
