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
        """Initialize the Gemini client and load curriculum"""
        logger.info("Initializing PhysicsGrader")
        
        # Initialize Gemini client
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        logger.info(f"Using model: {GEMINI_MODEL}")
        
        # Load curriculum
        self.curriculum = self._load_curriculum()
        logger.info("Curriculum loaded successfully")
    
    def _load_curriculum(self) -> Dict:
        """Load curriculum from JSON file"""
        if not CURRICULUM_FILE.exists():
            raise FileNotFoundError(
                f"Curriculum file not found: {CURRICULUM_FILE}\n"
                "Please run: python scripts/ingest_curriculum.py"
            )
        
        with open(CURRICULUM_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _build_curriculum_context(self) -> str:
        """Build curriculum context string for the prompt"""
        context_parts = []
        
        for category, data in self.curriculum.items():
            context_parts.append(f"\n## {category}\n")
            for page in data['pages']:
                context_parts.append(f"### صفحة {page['page_num']}\n")
                context_parts.append(page['text'])
                context_parts.append("\n")
        
        return "\n".join(context_parts)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for grading"""
        curriculum_context = self._build_curriculum_context()
        
        prompt = f"""أنت "المعلم" (Al-Muallim)، مُصحح فيزياء دقيق جداً ومتسق.

## المنهج الدراسي (مرجع الإجابات):
{curriculum_context}

## التقييم المتوازن:
- **10/10**: حل مثالي بدون أي أخطاء
- **8-9/10**: حل ممتاز مع خطأ بسيط جداً
- **7/10**: حل جيد جداً مع أخطاء قليلة أو أجزاء ناقصة
- **6/10**: حل جيد لكن فيه عدة أخطاء
- **4-5/10**: حل متوسط - الفكرة صحيحة لكن التنفيذ ضعيف
- **2-3/10**: حل ضعيف مع أخطاء كثيرة
- **0-1/10**: لا يوجد حل أو حل خاطئ تماماً

## قواعد التقييم المهمة (اقرأها بعناية):
1. **اقرأ السؤال بدقة** - اقرأ صورة السؤال أولاً لتفهم بالضبط ماذا يُطلب من الطالب
2. **راجع المنهج** - تحقق من المنهج الدراسي أعلاه للإجابة الصحيحة
3. **قارن بعناية** - قارن إجابة الطالب بالإجابة الصحيحة من المنهج
4. **تحقق مرتين** - قبل أن تحكم على إجابة، راجعها مرة أخرى
5. **اكتشف الأسئلة غير المجاب عنها** - اذكرها في feedback_ar
6. **لا تناقض نفسك** - إذا كان النص في annotations بـ label="correct" فلا تذكره في قسم "الخاطئ" في feedback_ar
7. **تحقق من المنهج بدقة** - قبل أن تعتبر إجابة خاطئة، تأكد أنها فعلاً تخالف المنهج
8. **تقبل الاختلافات البسيطة** - إذا كانت الإجابة صحيحة بشكل عام حتى لو صياغتها مختلفة قليلاً، اعتبرها صحيحة

## مثال على عملية التقييم:
1. اقرأ السؤال: "اختر الإجابة الصحيحة: الدائرة التي يتحقق فيها..."
2. اقرأ من المنهج: الإجابة الصحيحة هي "التوازي" لأن...
3. اقرأ إجابة الطالب: كتب "التوالي"
4. قارن: "التوالي" ≠ "التوازي" → خطأ
5. النتيجة: label="mistake"

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
• [اذكر الأسئلة التي لم يجب عنها الطالب]

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

## تحذيرات نهائية:
⚠️ **لا تناقض**: إذا كان annotation بـ label="correct" لا تذكره في قسم "الخاطئ"
⚠️ **راجع مرتين**: تأكد أن feedback_ar يطابق annotations بالضبط
⚠️ **انسخ بدقة**: النص يجب أن يكون مطابق 100% لما في الصورة
⚠️ **اكتشف الناقص**: اذكر أي سؤال لم يجب عنه الطالب
"""
        return prompt
    
    def grade_answer(
        self,
        question_image_path: Path,
        answer_image_path: Path
    ) -> Dict:
        """
        Grade a student's answer using Gemini 3 Pro.
        
        Args:
            question_image_path: Path to the question image
            answer_image_path: Path to the student's answer image
            
        Returns:
            Dictionary with score, feedback_ar, and annotations
        """
        logger.info("Starting grading process")
        logger.info(f"Question: {question_image_path}")
        logger.info(f"Answer: {answer_image_path}")
        
        try:
            # Upload images
            logger.info("Uploading images to Gemini...")
            question_file = self.client.files.upload(file=str(question_image_path))
            answer_file = self.client.files.upload(file=str(answer_image_path))
            
            # Build prompt
            system_prompt = self._build_system_prompt()
            
            # Create request
            logger.info(f"Sending request to {GEMINI_MODEL}...")
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    system_prompt,
                    question_file,
                    "الصورة أعلاه هي السؤال. والآن إليك إجابة الطالب:",
                    answer_file
                ],
                config={
                    "temperature": 0.1,  # Low temperature for consistent grading
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
    
    def _load_curriculum(self) -> Dict:
        """Load curriculum from JSON file"""
        if not CURRICULUM_FILE.exists():
            raise FileNotFoundError(
                f"Curriculum file not found: {CURRICULUM_FILE}\n"
                "Please run: python scripts/ingest_curriculum.py"
            )
        
        with open(CURRICULUM_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _build_curriculum_context(self) -> str:
        """Build curriculum context string for the prompt"""
        context_parts = []
        
        for category, data in self.curriculum.items():
            context_parts.append(f"\n## {category}\n")
            for page in data['pages']:
                context_parts.append(f"### صفحة {page['page_num']}\n")
                context_parts.append(page['text'])
                context_parts.append("\n")
        
        return "\n".join(context_parts)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for grading"""
        curriculum_context = self._build_curriculum_context()
        
        prompt = f"""أنت "المعلم" (Al-Muallim)، مُصحح فيزياء دقيق جداً ومتسق.

## المنهج الدراسي (مرجع الإجابات):
{curriculum_context}

## التقييم المتوازن:
- **10/10**: حل مثالي بدون أي أخطاء
- **8-9/10**: حل ممتاز مع خطأ بسيط جداً
- **7/10**: حل جيد جداً مع أخطاء قليلة أو أجزاء ناقصة
- **6/10**: حل جيد لكن فيه عدة أخطاء
- **4-5/10**: حل متوسط - الفكرة صحيحة لكن التنفيذ ضعيف
- **2-3/10**: حل ضعيف مع أخطاء كثيرة
- **0-1/10**: لا يوجد حل أو حل خاطئ تماماً

## قواعد التقييم المهمة (اقرأها بعناية):
1. **اقرأ السؤال بدقة** - اقرأ صورة السؤال أولاً لتفهم بالضبط ماذا يُطلب من الطالب
2. **راجع المنهج** - تحقق من المنهج الدراسي أعلاه للإجابة الصحيحة
3. **قارن بعناية** - قارن إجابة الطالب بالإجابة الصحيحة من المنهج
4. **تحقق مرتين** - قبل أن تحكم على إجابة، راجعها مرة أخرى
5. **اكتشف الأسئلة غير المجاب عنها** - اذكرها في feedback_ar
6. **لا تناقض نفسك** - إذا كان النص في annotations بـ label="correct" فلا تذكره في قسم "الخاطئ" في feedback_ar
7. **تحقق من المنهج بدقة** - قبل أن تعتبر إجابة خاطئة، تأكد أنها فعلاً تخالف المنهج
8. **تقبل الاختلافات البسيطة** - إذا كانت الإجابة صحيحة بشكل عام حتى لو صياغتها مختلفة قليلاً، اعتبرها صحيحة

## مثال على عملية التقييم:
1. اقرأ السؤال: "اختر الإجابة الصحيحة: الدائرة التي يتحقق فيها..."
2. اقرأ من المنهج: الإجابة الصحيحة هي "التوازي" لأن...
3. اقرأ إجابة الطالب: كتب "التوالي"
4. قارن: "التوالي" ≠ "التوازي" → خطأ
5. النتيجة: label="mistake"

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
• [اذكر الأسئلة التي لم يجب عنها الطالب]

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

## تحذيرات نهائية:
⚠️ **لا تناقض**: إذا كان annotation بـ label="correct" لا تذكره في قسم "الخاطئ"
⚠️ **راجع مرتين**: تأكد أن feedback_ar يطابق annotations بالضبط
⚠️ **انسخ بدقة**: النص يجب أن يكون مطابق 100% لما في الصورة
⚠️ **اكتشف الناقص**: اذكر أي سؤال لم يجب عنه الطالب
"""
        return prompt
    
    def grade_answer(
        self,
        question_image_path: Path,
        answer_image_path: Path
    ) -> Dict:
        """
        Grade a student's answer using Gemini 3 Pro.
        
        Args:
            question_image_path: Path to the question image
            answer_image_path: Path to the student's answer image
            
        Returns:
            Dictionary with score, feedback_ar, and annotations
        """
        logger.info("Starting grading process")
        logger.info(f"Question: {question_image_path}")
        logger.info(f"Answer: {answer_image_path}")
        
        try:
            # Upload images
            logger.info("Uploading images to Gemini...")
            question_file = self.client.files.upload(file=str(question_image_path))
            answer_file = self.client.files.upload(file=str(answer_image_path))
            
            # Build prompt
            system_prompt = self._build_system_prompt()
            
            # Create request
            logger.info(f"Sending request to {GEMINI_MODEL}...")
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    system_prompt,
                    question_file,
                    "الصورة أعلاه هي السؤال. والآن إليك إجابة الطالب:",
                    answer_file
                ],
                config={
                    "temperature": 0.1,  # Low temperature for consistent grading
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
