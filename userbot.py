"""Teacher Userbot - Automated Grading Assistant with Parallel Processing

This userbot monitors the teacher's Telegram account for incoming student answers,
automatically grades them using the AI grading engine with PARALLEL PROCESSING,
and creates scheduled message drafts for teacher approval.

Features:
- Parallel grading: Up to 3 students graded simultaneously
- Queue-based processing: Handles burst traffic efficiently
- Silent operation: Only creates scheduled drafts (no intermediate messages)

Usage:
    python userbot.py

First run will prompt for phone number and verification code.
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Set

from telethon import TelegramClient, events
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from config import TEMP_IMAGES_DIR
from utils.logger import setup_logger
from grading.grader import PhysicsGrader
from grading.annotator import draw_annotations_with_ocr

# Database imports for midterm mode
try:
    from backend.database import async_session, MidtermConfig, StudentProgress
    from sqlalchemy import select
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Load environment variables
load_dotenv()

logger = setup_logger("userbot")

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID", "30619302")
API_HASH = os.getenv("TELEGRAM_API_HASH", "a501dc4dd3e7e2288cdc3dc18ff9e3ce")
SESSION_NAME = "teacher_session"

# File paths for persistent storage
TEACHERS_FILE = Path(__file__).parent / "teachers.json"

# Teacher IDs (users who can set quizzes but won't be graded)
_teacher_ids: Set[int] = set()

# State for waiting for quiz image
_waiting_for_quiz: Set[int] = set()


def load_teachers() -> Set[int]:
    """Load teacher IDs from file"""
    if TEACHERS_FILE.exists():
        try:
            with open(TEACHERS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('teacher_ids', []))
        except Exception as e:
            logger.error(f"Error loading teachers: {e}")
    return set()


def save_teachers(teacher_ids: Set[int]):
    """Save teacher IDs to file"""
    try:
        with open(TEACHERS_FILE, 'w') as f:
            json.dump({'teacher_ids': list(teacher_ids)}, f)
        logger.info(f"Saved {len(teacher_ids)} teachers")
    except Exception as e:
        logger.error(f"Error saving teachers: {e}")


def add_teacher(teacher_id: int) -> bool:
    """Add a teacher ID"""
    global _teacher_ids
    if teacher_id not in _teacher_ids:
        _teacher_ids.add(teacher_id)
        save_teachers(_teacher_ids)
        return True
    return False


def remove_teacher(teacher_id: int) -> bool:
    """Remove a teacher ID"""
    global _teacher_ids
    if teacher_id in _teacher_ids:
        _teacher_ids.discard(teacher_id)
        save_teachers(_teacher_ids)
        return True
    return False


def is_teacher(user_id: int) -> bool:
    """Check if a user is a teacher"""
    return user_id in _teacher_ids

# Load session from environment variable if available (for cloud deployment)
def setup_session_from_env():
    """Load session from TELEGRAM_SESSION env var if available"""
    session_b64 = os.getenv("TELEGRAM_SESSION")
    if session_b64:
        import base64
        session_path = Path(__file__).parent / f"{SESSION_NAME}.session"
        if not session_path.exists():
            logger.info("Loading session from TELEGRAM_SESSION environment variable...")
            session_data = base64.b64decode(session_b64)
            session_path.write_bytes(session_data)
            logger.info("Session file created from environment variable")

# Run session setup on import
setup_session_from_env()

# Parallel processing configuration
NUM_WORKERS = 3  # Number of concurrent grading workers
MAX_QUEUE_SIZE = 100  # Maximum pending jobs

# Global grader instance (cached)
_grader = None

# Per-teacher quiz paths (each teacher has their own quiz)
_teacher_quizzes: dict[int, Path] = {}

# Global Telegram client (for workers to use)
_client = None


@dataclass
class GradingJob:
    """Represents a grading job in the queue"""
    chat_id: int
    sender_id: int
    sender_name: str
    answer_path: Path
    event_id: int
    teacher_id: int  # The teacher who should receive the graded result
    quiz_path: Path  # The quiz to use for grading


def get_grader():
    """Get or create cached PhysicsGrader instance"""
    global _grader
    if _grader is None:
        logger.info("Initializing PhysicsGrader (first time)...")
        _grader = PhysicsGrader()
        logger.info("PhysicsGrader cached for all future grading")
    return _grader


def set_teacher_quiz(teacher_id: int, image_path: Path):
    """Set the quiz for a specific teacher"""
    global _teacher_quizzes
    _teacher_quizzes[teacher_id] = image_path
    logger.info(f"Quiz set for teacher {teacher_id}: {image_path}")


def get_teacher_quiz(teacher_id: int) -> Path:
    """Get the quiz for a specific teacher"""
    return _teacher_quizzes.get(teacher_id)


def set_active_quiz(image_path: Path):
    """Set the active quiz question image (for owner)"""
    # This is now an alias that sets quiz for teacher ID 0 (owner fallback)
    set_teacher_quiz(0, image_path)


def get_active_quiz() -> Path:
    """Get the current active quiz question path (owner's quiz)"""
    return _teacher_quizzes.get(0)


async def grade_student_answer(answer_path: Path, quiz_path: Path, 
                                teacher_id: int = None, sender_id: int = None,
                                sender_name: str = None) -> tuple:
    """
    Grade a student's answer using the specified quiz.
    
    Supports both quiz mode (10 points) and midterm mode (configurable points with running totals).
    
    Returns:
        Tuple of (annotated_image_path, feedback_message, score, max_score)
    """
    if not quiz_path or not quiz_path.exists():
        raise Exception("No active quiz set! Teacher must set a quiz first.")
    
    logger.info(f"Grading answer: {answer_path}")
    logger.info(f"Using quiz: {quiz_path}")
    
    # Check for midterm mode if database is available
    midterm_config = None
    max_score = 10  # Default quiz mode
    running_total = None
    
    logger.info(f"DB_AVAILABLE: {DB_AVAILABLE}, teacher_id: {teacher_id}")
    
    if DB_AVAILABLE and teacher_id:
        try:
            async with async_session() as session:
                # Get midterm config
                result = await session.execute(
                    select(MidtermConfig).where(MidtermConfig.teacher_id == teacher_id)
                )
                midterm_config = result.scalar_one_or_none()
                
                if midterm_config:
                    logger.info(f"Found MidtermConfig: is_active={midterm_config.is_active}, "
                               f"total_questions={midterm_config.total_questions}, "
                               f"total_marks={midterm_config.total_marks}")
                    
                    if midterm_config.is_active:
                        # Calculate points per question
                        total_marks = midterm_config.total_marks
                        total_questions = midterm_config.total_questions
                        max_score = total_marks // total_questions
                        logger.info(f"✓ MIDTERM MODE ACTIVE: {total_questions} questions, {max_score} points each")
                    else:
                        logger.info("MidtermConfig exists but is_active=False, using quiz mode")
                else:
                    logger.info(f"No MidtermConfig found for teacher_id={teacher_id}, using quiz mode (10 points)")
        except Exception as e:
            logger.error(f"Error checking midterm config: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        if not DB_AVAILABLE:
            logger.warning("Database not available - falling back to quiz mode")
    
    # Run grading in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    grader = get_grader()
    
    # Get total_questions for AI detection (midterm mode only)
    total_questions_for_ai = None
    if midterm_config and midterm_config.is_active:
        total_questions_for_ai = midterm_config.total_questions
    
    logger.info(f">>> Calling grader.grade_answer with max_score={max_score}, total_questions={total_questions_for_ai}")
    
    # Grade in thread pool (CPU-bound operation)
    grading_result = await loop.run_in_executor(
        None, 
        lambda: grader.grade_answer(
            quiz_path, answer_path, 
            max_score=max_score,
            total_questions=total_questions_for_ai
        )
    )
    
    # Get annotations and score
    text_annotations = grading_result.get('annotations', [])
    raw_score = grading_result.get('score', 0)
    score = min(raw_score, max_score)  # Cap at max
    
    # Get AI-detected question numbers
    detected_questions = grading_result.get('question_numbers', [])
    
    logger.info(f"<<< Grader returned: raw_score={raw_score}, capped_score={score}, max_score={max_score}")
    logger.info(f"    Detected questions: {detected_questions}")
    logger.info(f"    Annotations: {len(text_annotations)} items")
    
    # Update student progress and get running total (midterm mode only)
    q_label = None
    is_resubmission = False
    questions_info = None  # Initialize for smart progress display
    if DB_AVAILABLE and midterm_config and midterm_config.is_active and sender_id:
        try:
            async with async_session() as session:
                # Get or create student progress
                result = await session.execute(
                    select(StudentProgress).where(
                        StudentProgress.teacher_id == teacher_id,
                        StudentProgress.student_telegram_id == sender_id
                    )
                )
                progress = result.scalar_one_or_none()
                
                if progress is None:
                    import json as json_module
                    progress = StudentProgress(
                        teacher_id=teacher_id,
                        student_telegram_id=sender_id,
                        student_name=sender_name or "Unknown",
                        questions_answered="{}",
                        total_score=0,
                        questions_count=0
                    )
                    session.add(progress)
                
                # Parse existing answers
                import json as json_module
                questions_dict = json_module.loads(progress.questions_answered or "{}")
                
                # Determine question number(s) to update
                total_qs = midterm_config.total_questions
                if detected_questions:
                    # Validate and cap question numbers
                    valid_questions = [q for q in detected_questions if 1 <= q <= total_qs]
                    if not valid_questions:
                        logger.warning(f"AI detected invalid questions {detected_questions}, falling back to sequential")
                        valid_questions = [progress.questions_count + 1]
                else:
                    # Fall back to sequential if AI didn't detect
                    logger.info("No question numbers detected, using sequential")
                    valid_questions = [progress.questions_count + 1]
                
                # Handle the detected question(s)
                for q_num in valid_questions:
                    q_key = f"Q{q_num}"
                    if q_key in questions_dict:
                        # Re-submission: update existing score
                        old_score = questions_dict[q_key]
                        questions_dict[q_key] = score
                        is_resubmission = True
                        logger.info(f"RE-SUBMISSION: {q_key} updated from {old_score} to {score}")
                    else:
                        # New question
                        questions_dict[q_key] = score
                        progress.questions_count += 1
                        logger.info(f"NEW: {q_key} = {score}")
                
                # Recalculate total score from all questions
                progress.total_score = sum(questions_dict.values())
                progress.questions_answered = json_module.dumps(questions_dict)
                if sender_name:
                    progress.student_name = sender_name
                
                await session.commit()
                
                # Set running total for annotation
                running_total = (progress.total_score, midterm_config.total_marks)
                q_label = ",".join([f"Q{q}" for q in valid_questions])
                resubmit_note = " (update)" if is_resubmission else ""
                logger.info(f"Midterm progress: {q_label}={score}/{max_score}, Total={progress.total_score}/{midterm_config.total_marks}{resubmit_note}")
                
                # Build questions_info for smart progress display
                answered_questions = list(questions_dict.keys())  # ["Q1", "Q3", etc.]
                total_qs = midterm_config.total_questions
                is_complete = len(answered_questions) >= total_qs
                questions_info = {
                    "answered": answered_questions,
                    "total": total_qs,
                    "is_complete": is_complete
                }
                
        except Exception as e:
            logger.error(f"Error updating student progress: {e}")
    
    # Annotate the image with correct score format
    # questions_info is None for quiz mode, defined for midterm mode
    annotated_path = draw_annotations_with_ocr(
        answer_path, text_annotations, 
        score=score, max_score=max_score,
        running_total=running_total,
        questions_info=questions_info if DB_AVAILABLE and midterm_config and midterm_config.is_active else None
    )
    
    # Format feedback
    feedback_message = grader.format_feedback_message(grading_result)
    
    return annotated_path, feedback_message, score, max_score


async def grading_worker(worker_id: int, queue: asyncio.Queue):
    """
    Worker that processes grading jobs from the queue.
    Multiple workers run concurrently for parallel processing.
    """
    global _client
    
    logger.info(f"Worker {worker_id} started")
    
    while True:
        try:
            # Get job from queue (blocks until available)
            job: GradingJob = await queue.get()
            
            logger.info(f"Worker {worker_id} processing job for {job.sender_name} (teacher: {job.teacher_id})")
            
            try:
                # Grade the answer using the teacher's quiz (with midterm support)
                annotated_path, feedback, score, max_score = await grade_student_answer(
                    job.answer_path, job.quiz_path,
                    teacher_id=job.teacher_id,
                    sender_id=job.sender_id,
                    sender_name=job.sender_name
                )
                
                # Create scheduled message (draft) - send to the TEACHER, not the student
                schedule_time = datetime.now() + timedelta(days=365)
                
                # Include student name in the caption with dynamic score format
                caption = f"🎯 {job.sender_name}: {score}/{max_score}"
                
                await _client.send_file(
                    job.teacher_id,  # Send to teacher, not original chat
                    annotated_path,
                    caption=caption,
                    schedule=schedule_time
                )
                
                logger.info(f"Worker {worker_id}: Created draft for {job.sender_name} - Score: {score}/{max_score}")
                
                # Cleanup temp files
                job.answer_path.unlink(missing_ok=True)
                annotated_path.unlink(missing_ok=True)
                
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
            
            finally:
                # Mark job as done
                queue.task_done()
                
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} stopped")
            break


async def main():
    """Main userbot function with parallel processing"""
    global _client, _teacher_ids
    
    logger.info("=" * 50)
    logger.info("Starting Teacher Userbot (Parallel Processing Mode)")
    logger.info(f"Workers: {NUM_WORKERS} | Max Queue: {MAX_QUEUE_SIZE}")
    logger.info("=" * 50)
    
    # Load saved teachers
    _teacher_ids = load_teachers()
    logger.info(f"Loaded {len(_teacher_ids)} teachers from file")
    
    # Create job queue
    grading_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    
    # Create Telegram client
    _client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    @_client.on(events.NewMessage(incoming=True))
    async def handle_incoming_message(event):
        """Handle incoming messages to teacher's account"""
        
        # Skip messages from channels/groups - only private chats
        if not event.is_private:
            return
        
        sender = await event.get_sender()
        sender_name = sender.first_name if sender else "Unknown"
        sender_id = sender.id if sender else 0
        me = await _client.get_me()
        my_id = me.id
        
        # Check if this is the bot owner (main teacher)
        is_owner = (sender_id == my_id)
        
        # Handle text commands
        if event.raw_text:
            text = event.raw_text.strip().lower()
            
            # /quiz command - set quiz image (owner or teachers)
            if text == "/quiz" or text == "/سؤال":
                if is_owner or is_teacher(sender_id):
                    _waiting_for_quiz.add(sender_id)
                    await event.respond("📷 أرسل صورة السؤال لتعيينها كاختبار نشط.\nSend the quiz image to set it as active.")
                    logger.info(f"{sender_name} initiated quiz setup")
                return
            
            # /addteacher command (owner only)
            if text.startswith("/addteacher") or text.startswith("/اضف_معلم"):
                if not is_owner:
                    await event.respond("⛔ فقط المالك يمكنه إضافة معلمين.")
                    return
                await event.respond("📨 أرسل لي رسالة مُعاد توجيهها من المعلم الذي تريد إضافته.\nForward a message from the teacher you want to add.")
                logger.info("Waiting for forwarded message to add teacher")
                return
            
            # /removeteacher command (owner only)  
            if text.startswith("/removeteacher") or text.startswith("/حذف_معلم"):
                if not is_owner:
                    await event.respond("⛔ فقط المالك يمكنه حذف معلمين.")
                    return
                await event.respond("📨 أرسل لي رسالة مُعاد توجيهها من المعلم الذي تريد حذفه.\nForward a message from the teacher you want to remove.")
                return
            
            # /listteachers command (owner only)
            if text == "/listteachers" or text == "/المعلمين":
                if not is_owner:
                    return
                if _teacher_ids:
                    teacher_list = "\n".join([f"• {tid}" for tid in _teacher_ids])
                    await event.respond(f"👥 المعلمون المسجلون:\n{teacher_list}")
                else:
                    await event.respond("📭 لا يوجد معلمون مسجلون بعد.")
                return
            
            # /status command (owner only)
            if text == "/status" or text == "/حالة":
                if not is_owner:
                    return
                quiz = get_active_quiz()
                quiz_status = f"✅ {quiz.name}" if quiz else "❌ لا يوجد"
                teachers_count = len(_teacher_ids)
                await event.respond(
                    f"📊 حالة البوت:\n"
                    f"• الاختبار النشط: {quiz_status}\n"
                    f"• عدد المعلمين: {teachers_count}\n"
                    f"• العمال النشطون: {NUM_WORKERS}"
                )
                return
        
        # Handle forwarded messages (for adding teachers)
        if event.forward and event.forward.sender_id:
            forwarded_id = event.forward.sender_id
            forwarded_name = "Unknown"
            try:
                forwarded_user = await _client.get_entity(forwarded_id)
                forwarded_name = forwarded_user.first_name
            except:
                pass
            
            if add_teacher(forwarded_id):
                await event.respond(f"✅ تمت إضافة المعلم: {forwarded_name} (ID: {forwarded_id})")
                logger.info(f"Added teacher: {forwarded_name} ({forwarded_id})")
            else:
                await event.respond(f"ℹ️ المعلم موجود بالفعل: {forwarded_name}")
            return
        
        # Handle photos
        if event.photo:
            logger.info(f"Received photo from {sender_name} (ID: {sender_id})")
            
            # Check if this is a quiz image setup (from owner or registered teacher)
            if sender_id in _waiting_for_quiz:
                _waiting_for_quiz.discard(sender_id)
                
                # Save quiz image for THIS teacher
                quiz_path = TEMP_IMAGES_DIR / f"quiz_{sender_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                await _client.download_media(event.photo, quiz_path)
                
                # Set quiz for this specific teacher (or owner via ID 0 mapping)
                teacher_quiz_id = sender_id if is_teacher(sender_id) else my_id
                set_teacher_quiz(teacher_quiz_id, quiz_path)
                
                await event.respond(f"✅ تم تعيين الاختبار بنجاح!\nQuiz set successfully for you!")
                logger.info(f"Quiz set by {sender_name} (ID: {teacher_quiz_id}): {quiz_path}")
                return
            
            # If this is a registered teacher sending a photo, it might be a student answer they're forwarding
            # Check if the message is forwarded - this is how teachers submit student answers
            if event.forward and event.forward.sender_id:
                forwarded_from_id = event.forward.sender_id
                forwarded_from_name = "Student"
                try:
                    forwarded_user = await _client.get_entity(forwarded_from_id)
                    forwarded_from_name = forwarded_user.first_name or "Student"
                except:
                    pass
                
                # The sender (teacher) is submitting a student's answer for grading
                teacher_quiz_id = sender_id if is_teacher(sender_id) else my_id
                quiz_path = get_teacher_quiz(teacher_quiz_id) or get_teacher_quiz(my_id)
                
                if not quiz_path:
                    await event.respond("⚠️ لم يتم تعيين اختبار بعد! استخدم /quiz أولاً.\nNo quiz set! Use /quiz first.")
                    return
                
                # Download the forwarded photo
                answer_path = TEMP_IMAGES_DIR / f"student_{forwarded_from_id}_{event.id}.jpg"
                await _client.download_media(event.photo, answer_path)
                logger.info(f"Downloaded forwarded answer from {forwarded_from_name} to: {answer_path}")
                
                # Create grading job - results go back to the teacher who forwarded
                job = GradingJob(
                    chat_id=event.chat_id,
                    sender_id=forwarded_from_id,
                    sender_name=forwarded_from_name,
                    answer_path=answer_path,
                    event_id=event.id,
                    teacher_id=sender_id,  # Send result back to the teacher
                    quiz_path=quiz_path
                )
                
                try:
                    grading_queue.put_nowait(job)
                    logger.info(f"Job queued: {forwarded_from_name}'s answer for teacher {sender_name}")
                    await event.respond(f"📥 تم استلام إجابة {forwarded_from_name}، جاري التصحيح...")
                except asyncio.QueueFull:
                    logger.error(f"Queue full!")
                    await event.respond("⚠️ النظام مشغول، حاول مرة أخرى لاحقاً.")
                return
            
            # Skip grading for direct photos from teachers (not forwarded)
            if is_teacher(sender_id):
                logger.info(f"Ignoring direct (non-forwarded) photo from teacher: {sender_name}")
                return
            
            # Direct photo from a student to the owner's account
            quiz_path = get_teacher_quiz(my_id)
            if not quiz_path:
                logger.warning("No active quiz set - ignoring photo")
                return
            
            # Download the photo
            answer_path = TEMP_IMAGES_DIR / f"student_{sender_id}_{event.id}.jpg"
            await _client.download_media(event.photo, answer_path)
            logger.info(f"Downloaded answer to: {answer_path}")
            
            # Create grading job - results go to owner
            job = GradingJob(
                chat_id=event.chat_id,
                sender_id=sender_id,
                sender_name=sender_name,
                answer_path=answer_path,
                event_id=event.id,
                teacher_id=my_id,
                quiz_path=quiz_path
            )
            
            # Add to queue (non-blocking)
            try:
                grading_queue.put_nowait(job)
                queue_size = grading_queue.qsize()
                logger.info(f"Job queued for {sender_name} (Queue size: {queue_size})")
            except asyncio.QueueFull:
                logger.error(f"Queue full! Cannot process {sender_name}'s answer")
    
    # Start the client
    await _client.start()
    logger.info("Userbot logged in successfully!")
    
    # Load quiz from temp_images folder
    quiz_found = False
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    for ext in image_extensions:
        for quiz_file in TEMP_IMAGES_DIR.glob(f"*{ext}"):
            if not quiz_file.name.startswith(('student_', 'annotated_', 'answer_', 'question_')):
                set_active_quiz(quiz_file)
                logger.info(f"Loaded quiz: {quiz_file.name}")
                quiz_found = True
                break
        if quiz_found:
            break
    
    if not quiz_found:
        logger.warning("No quiz image found in temp_images folder!")
    
    # Start worker tasks
    workers = []
    for i in range(NUM_WORKERS):
        worker = asyncio.create_task(grading_worker(i + 1, grading_queue))
        workers.append(worker)
    
    logger.info(f"Started {NUM_WORKERS} grading workers")
    logger.info("Listening for incoming student answers...")
    
    # Run until disconnected
    try:
        await _client.run_until_disconnected()
    finally:
        # Cancel workers on shutdown
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Userbot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
