"""Upload Handler for Al-Muallim Bot

Manages the conversation flow for receiving question and answer images.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import TEMP_IMAGES_DIR
from utils.logger import setup_logger
from grading.grader import PhysicsGrader
from grading.annotator import draw_annotations_with_ocr

logger = setup_logger("upload_handler")

# Conversation states
WAITING_FOR_QUESTION, WAITING_FOR_ANSWER = range(2)

async def start_grading(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the grading conversation"""
    await update.message.reply_text(
        "مرحباً! أنا المعلم، مُصحح الفيزياء الآلي.\n\n"
        "📷 أرسل صورة السؤال أولاً."
    )
    return WAITING_FOR_QUESTION

async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and save the question image"""
    logger.info(f"Receiving question image from user {update.effective_user.id}")
    
    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        
        # Download the photo
        photo_file = await photo.get_file()
        question_path = TEMP_IMAGES_DIR / f"question_{update.effective_user.id}.jpg"
        await photo_file.download_to_drive(question_path)
        
        # Store in context
        context.user_data['question_image'] = str(question_path)
        
        logger.info(f"Question saved to: {question_path}")
        
        await update.message.reply_text(
            "✅ تم استلام صورة السؤال.\n\n"
            "📝 الآن أرسل صورة إجابة الطالب."
        )
        
        return WAITING_FOR_ANSWER
        
    except Exception as e:
        logger.error(f"Error receiving question: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ في استقبال الصورة. حاول مرة أخرى."
        )
        return ConversationHandler.END

async def receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive answer image and trigger grading"""
    logger.info(f"Receiving answer image from user {update.effective_user.id}")
    
    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        
        # Download the photo
        photo_file = await photo.get_file()
        answer_path = TEMP_IMAGES_DIR / f"answer_{update.effective_user.id}.jpg"
        await photo_file.download_to_drive(answer_path)
        
        logger.info(f"Answer saved to: {answer_path}")
        
        await update.message.reply_text(
            "🤔 جاري التصحيح... قد يستغرق هذا بضع ثوان.\n"
            "المُعلم يستخدم الذكاء الاصطناعي لتحليل إجابتك بدقة."
        )
        
        # Grade the answer
        grader = PhysicsGrader()
        question_image = Path(context.user_data['question_image'])
        
        grading_result = grader.grade_answer(question_image, answer_path)
        
        # Annotate the image using OCR + AI grading
        text_annotations = grading_result.get('annotations', [])
        score = grading_result.get('score', 0)
        annotated_path = draw_annotations_with_ocr(answer_path, text_annotations, score=score)
        
        # Format feedback message
        feedback_message = grader.format_feedback_message(grading_result)
        
        # Send annotated image with short caption
        score = grading_result.get('score', 0)
        short_caption = f"🎯 النتيجة: {score}/{10}\n\n✅ انظر الصورة للتعليقات الملونة، والرسالة التالية للتفاصيل الكاملة."
        
        with open(annotated_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=short_caption
            )
        
        # Send full feedback as a separate message
        await update.message.reply_text(feedback_message)
        
        logger.info(f"Grading complete for user {update.effective_user.id}")
        
        # Clean up
        question_image.unlink(missing_ok=True)
        answer_path.unlink(missing_ok=True)
        annotated_path.unlink(missing_ok=True)
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error during grading: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ أثناء التصحيح. حاول مرة أخرى لاحقاً.\n"
            f"تفاصيل الخطأ: {str(e)}"
        )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation"""
    await update.message.reply_text(
        "تم إلغاء التصحيح. أرسل /grade لبدء تصحيح جديد."
    )
    return ConversationHandler.END
