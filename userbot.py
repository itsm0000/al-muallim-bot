"""Teacher Userbot - Automated Grading Assistant

This userbot monitors the teacher's Telegram account for incoming student answers,
automatically grades them using the AI grading engine, and creates scheduled message
drafts for teacher approval.

Usage:
    python userbot.py

First run will prompt for phone number and verification code.
"""
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendScheduledMessagesRequest
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from config import TEMP_IMAGES_DIR
from utils.logger import setup_logger
from grading.grader import PhysicsGrader
from grading.annotator import draw_annotations_with_ocr

# Load environment variables
load_dotenv()

logger = setup_logger("userbot")

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID", "30619302")
API_HASH = os.getenv("TELEGRAM_API_HASH", "a501dc4dd3e7e2288cdc3dc18ff9e3ce")
SESSION_NAME = "teacher_session"

# Global grader instance (cached)
_grader = None

# Active quiz question path (teacher sets this)
_active_quiz_path = None


def get_grader():
    """Get or create cached PhysicsGrader instance"""
    global _grader
    if _grader is None:
        logger.info("Initializing PhysicsGrader (first time)...")
        _grader = PhysicsGrader()
        logger.info("PhysicsGrader cached for all future grading")
    return _grader


def set_active_quiz(image_path: Path):
    """Set the active quiz question image"""
    global _active_quiz_path
    _active_quiz_path = image_path
    logger.info(f"Active quiz set to: {image_path}")


def get_active_quiz() -> Path:
    """Get the current active quiz question path"""
    return _active_quiz_path


async def grade_student_answer(answer_path: Path) -> tuple:
    """
    Grade a student's answer using the active quiz.
    
    Returns:
        Tuple of (annotated_image_path, feedback_message, score)
    """
    quiz_path = get_active_quiz()
    if not quiz_path or not quiz_path.exists():
        raise Exception("No active quiz set! Teacher must set a quiz first.")
    
    logger.info(f"Grading answer: {answer_path}")
    logger.info(f"Using quiz: {quiz_path}")
    
    # Get grader and grade
    grader = get_grader()
    grading_result = grader.grade_answer(quiz_path, answer_path)
    
    # Annotate the image
    text_annotations = grading_result.get('annotations', [])
    score = grading_result.get('score', 0)
    annotated_path = draw_annotations_with_ocr(answer_path, text_annotations, score=score)
    
    # Format feedback
    feedback_message = grader.format_feedback_message(grading_result)
    
    return annotated_path, feedback_message, score


async def main():
    """Main userbot function"""
    logger.info("=" * 50)
    logger.info("Starting Teacher Userbot")
    logger.info("=" * 50)
    
    # Create Telegram client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    @client.on(events.NewMessage(incoming=True))
    async def handle_incoming_message(event):
        """Handle incoming messages to teacher's account"""
        
        # Skip messages from channels/groups - only private chats
        if not event.is_private:
            return
        
        sender = await event.get_sender()
        sender_name = sender.first_name if sender else "Unknown"
        
        # Check if message has a photo (student answer)
        if event.photo:
            logger.info(f"Received photo from {sender_name} (ID: {sender.id})")
            
            # Check if we have an active quiz
            if not get_active_quiz():
                logger.warning("No active quiz set - ignoring photo")
                return
            
            try:
                # Download the photo
                answer_path = TEMP_IMAGES_DIR / f"student_{sender.id}_{event.id}.jpg"
                await client.download_media(event.photo, answer_path)
                logger.info(f"Downloaded answer to: {answer_path}")
                
                # Grade the answer (silently - no messages to student)
                annotated_path, feedback, score = await grade_student_answer(answer_path)
                
                # Create ONLY a scheduled message (draft) - no other messages!
                # Set for distant future so it never auto-sends
                schedule_time = datetime.now() + timedelta(days=365)
                
                # Send the graded result as a scheduled message (teacher reviews and sends)
                await client.send_file(
                    event.chat_id,
                    annotated_path,
                    caption=f"🎯 النتيجة: {score}/10",
                    schedule=schedule_time
                )
                
                logger.info(f"Created scheduled draft for {sender_name} with score {score}/10")
                
                # Cleanup temp files
                answer_path.unlink(missing_ok=True)
                annotated_path.unlink(missing_ok=True)
                
            except Exception as e:
                logger.error(f"Error grading: {e}")
        
        # Check for quiz setup command from teacher (to themselves in Saved Messages or specific chat)
        elif event.raw_text and event.raw_text.startswith("/setquiz"):
            # If next message is a photo, use it as the quiz
            logger.info("Quiz setup command received - waiting for quiz image...")
            await event.reply("📷 أرسل صورة السؤال لتعيينها كاختبار نشط.")
    
    @client.on(events.NewMessage(outgoing=True))
    async def handle_outgoing_message(event):
        """Handle outgoing messages (teacher commands)"""
        
        # Teacher sets quiz by sending /setquiz followed by a photo
        if event.photo and event.raw_text == "":
            # Check if there was a recent /setquiz command
            # For simplicity, teacher can just send photo to Saved Messages with caption "quiz"
            pass
    
    # Start the client
    await client.start()
    logger.info("Userbot logged in successfully!")
    logger.info("Listening for incoming student answers...")
    logger.info("To set a quiz, send /setquiz then a photo")
    
    # Check if we have a quiz image in temp_images folder (any image file)
    quiz_found = False
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    for ext in image_extensions:
        for quiz_file in TEMP_IMAGES_DIR.glob(f"*{ext}"):
            # Skip student answer files and annotated files
            if not quiz_file.name.startswith(('student_', 'annotated_', 'answer_', 'question_')):
                set_active_quiz(quiz_file)
                logger.info(f"Loaded quiz: {quiz_file.name}")
                quiz_found = True
                break
        if quiz_found:
            break
    
    if not quiz_found:
        logger.warning("No quiz image found in temp_images folder. Place a quiz image there!")
    
    # Run forever
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Userbot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
