"""
Al-Muallim AI Physics Bot
Main bot entry point with Telegram integration
"""
import sys
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from config import TELEGRAM_BOT_TOKEN
from utils.logger import setup_logger
from handlers.upload_handler import (
    start_grading,
    receive_question,
    receive_answer,
    cancel,
    WAITING_FOR_QUESTION,
    WAITING_FOR_ANSWER
)

logger = setup_logger("bot")

async def start_command(update: Update, context) -> None:
    """Handle /start command"""
    welcome_message = """
مرحباً بك في المُعلم! 🎓

أنا بوت ذكي لتصحيح امتحانات الفيزياء المكتوبة بخط اليد.

**كيف أعمل:**
1. أرسل لي صورة السؤال
2. أرسل لي صورة إجابة الطالب
3. سأقوم بتحليل الإجابة ومقارنتها بالمنهج
4. سأعطيك درجة من 10 + ملاحظات تفصيلية
5. سأضع علامات ملونة على الأخطاء والصواب

**الأوامر المتاحة:**
- /grade - بدء تصحيح جديد
- /help - عرض المساعدة
- /cancel - إلغاء التصحيح الحالي

📚 المنهج الدراسي: حسين محمد - فيزياء 2025
🤖 مدعوم بـ Gemini 3 Pro (Thinking Mode)
"""
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context) -> None:
    """Handle /help command"""
    help_message = """
**مساعدة المُعلم** 📖

**خطوات التصحيح:**
1. استخدم الأمر /grade
2. أرسل صورة السؤال
3. أرسل صورة إجابة الطالب
4. انتظر النتيجة (قد يستغرق 10-30 ثانية)

**ألوان التصحيح:**
- 🟢 أخضر: خطوة صحيحة
- 🔴 أحمر: خطأ
- 🟡 أصفر: جزئي الصحة
- 🟠 برتقالي: غير واضح

**نصائح:**
- تأكد من وضوح الصور
- اكتب بخط واضح
- صور السؤال والإجابة بإضاءة جيدة

للإلغاء في أي وقت: /cancel
"""
    await update.message.reply_text(help_message)

def main():
    """Main bot function"""
    logger.info("=" * 50)
    logger.info("Starting Al-Muallim Bot")
    logger.info("=" * 50)
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Conversation handler for grading
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("grade", start_grading)],
        states={
            WAITING_FOR_QUESTION: [
                MessageHandler(filters.PHOTO, receive_question)
            ],
            WAITING_FOR_ANSWER: [
                MessageHandler(filters.PHOTO, receive_answer)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Start the bot
    logger.info("Bot is running... Press Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
