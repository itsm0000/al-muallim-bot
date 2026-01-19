"""
Multi-Session Bot Manager
Manages Telethon clients for multiple teachers
"""
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Add parent directory to path for grading imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from grading.grader import PhysicsGrader
from grading.annotator import draw_annotations_with_ocr
from config import TEMP_IMAGES_DIR

# Telegram API credentials
API_ID = os.getenv("TELEGRAM_API_ID", "30619302")
API_HASH = os.getenv("TELEGRAM_API_HASH", "a501dc4dd3e7e2288cdc3dc18ff9e3ce")


@dataclass
class TeacherBot:
    """Represents a running bot instance for a teacher"""
    teacher_id: int
    telegram_id: int
    client: TelegramClient
    quiz_path: Optional[Path] = None
    is_running: bool = False


class BotManager:
    """
    Manages multiple Telethon clients, one per teacher.
    Each teacher's bot runs on their own Telegram account.
    """
    
    def __init__(self):
        self.bots: dict[int, TeacherBot] = {}  # teacher_id -> TeacherBot
        self._grader: Optional[PhysicsGrader] = None
        self._grading_queue = asyncio.Queue(maxsize=100)
        self._workers: list[asyncio.Task] = []
    
    def get_grader(self) -> PhysicsGrader:
        """Get or create shared PhysicsGrader instance"""
        if self._grader is None:
            print("🔧 Initializing PhysicsGrader...")
            self._grader = PhysicsGrader()
        return self._grader
    
    async def start_for_teacher(
        self,
        teacher_id: int,
        session_string: str,
        quiz_path: Optional[Path] = None
    ) -> bool:
        """
        Start a bot instance for a specific teacher.
        
        Args:
            teacher_id: Database ID of the teacher
            session_string: Telethon StringSession data
            quiz_path: Path to the current quiz image
            
        Returns:
            True if started successfully
        """
        if teacher_id in self.bots and self.bots[teacher_id].is_running:
            print(f"⚠️ Bot for teacher {teacher_id} already running")
            return True
        
        try:
            # Create client from session string
            client = TelegramClient(
                StringSession(session_string),
                API_ID,
                API_HASH
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                print(f"❌ Session for teacher {teacher_id} is not authorized")
                return False
            
            me = await client.get_me()
            
            # Create bot instance
            bot = TeacherBot(
                teacher_id=teacher_id,
                telegram_id=me.id,
                client=client,
                quiz_path=quiz_path,
                is_running=True
            )
            
            # Set up message handler
            self._setup_handler(bot)
            
            # Store bot
            self.bots[teacher_id] = bot
            
            print(f"✅ Started bot for teacher {teacher_id} ({me.first_name})")
            return True
            
        except Exception as e:
            print(f"❌ Error starting bot for teacher {teacher_id}: {e}")
            return False
    
    def _setup_handler(self, bot: TeacherBot):
        """Set up message handler for a teacher's bot"""
        
        @bot.client.on(events.NewMessage(incoming=True))
        async def handle_message(event):
            # Only handle private messages
            if not event.is_private:
                return
            
            sender = await event.get_sender()
            sender_name = sender.first_name if sender else "Unknown"
            
            # Handle photos (student answers)
            if event.photo:
                if not bot.quiz_path or not bot.quiz_path.exists():
                    print(f"⚠️ No quiz set for teacher {bot.teacher_id}")
                    return
                
                print(f"📸 Teacher {bot.teacher_id}: Photo from {sender_name}")
                
                # Queue the grading job
                await self._grading_queue.put({
                    'bot': bot,
                    'event': event,
                    'sender_id': sender.id,
                    'sender_name': sender_name,
                    'chat_id': event.chat_id
                })
    
    async def _grading_worker(self, worker_id: int):
        """Worker that processes grading jobs with midterm mode support"""
        print(f"[Worker {worker_id}] Started")
        
        while True:
            try:
                job = await self._grading_queue.get()
                
                bot = job['bot']
                event = job['event']
                sender_id = job['sender_id']
                sender_name = job['sender_name']
                
                print(f"[Worker {worker_id}] Grading for teacher {bot.teacher_id}")
                
                try:
                    # Download the photo
                    answer_path = TEMP_IMAGES_DIR / f"answer_{bot.teacher_id}_{event.id}.jpg"
                    await bot.client.download_media(event.photo, answer_path)
                    
                    # Check if midterm mode is active for this teacher
                    midterm_config = await self._get_midterm_config(bot.teacher_id)
                    
                    if midterm_config and midterm_config.is_active:
                        # MIDTERM MODE
                        await self._process_midterm_grading(
                            worker_id, bot, job, answer_path, 
                            midterm_config, sender_id, sender_name
                        )
                    else:
                        # QUIZ MODE (default - score out of 10)
                        await self._process_quiz_grading(
                            worker_id, bot, job, answer_path, sender_name
                        )
                    
                    # Cleanup
                    answer_path.unlink(missing_ok=True)
                    
                except Exception as e:
                    print(f"[Worker {worker_id}] Error: {e}")
                    import traceback
                    traceback.print_exc()
                
                finally:
                    self._grading_queue.task_done()
                    
            except asyncio.CancelledError:
                break
    
    async def _get_midterm_config(self, teacher_id: int):
        """Get midterm config for a teacher from database"""
        try:
            from database import async_session, MidtermConfig
            from sqlalchemy import select
            
            async with async_session() as session:
                result = await session.execute(
                    select(MidtermConfig).where(MidtermConfig.teacher_id == teacher_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            print(f"[MidtermConfig] Error: {e}")
            return None
    
    async def _process_quiz_grading(self, worker_id: int, bot, job: dict, 
                                     answer_path: Path, sender_name: str):
        """Process grading in quiz mode (default - score out of 10)"""
        grader = self.get_grader()
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(
            None,
            lambda: grader.grade_answer(bot.quiz_path, answer_path)
        )
        
        # Annotate with hand-drawn style
        annotations = result.get('annotations', [])
        score = result.get('score', 0)
        annotated_path = draw_annotations_with_ocr(
            answer_path, annotations, 
            score=score, max_score=10
        )
        
        # Send as scheduled message
        schedule_time = datetime.now() + timedelta(days=365)
        await bot.client.send_file(
            job['chat_id'],
            annotated_path,
            caption=f"[RESULT] {score}/10",
            schedule=schedule_time
        )
        
        print(f"[Worker {worker_id}] Quiz mode: {sender_name} - {score}/10")
        annotated_path.unlink(missing_ok=True)
    
    async def _process_midterm_grading(self, worker_id: int, bot, job: dict,
                                        answer_path: Path, midterm_config,
                                        sender_id: int, sender_name: str):
        """
        Process grading in midterm mode with running totals.
        
        - Score is out of (total_marks / total_questions)
        - Running total is tracked per student
        - Uses AI-detected question numbers instead of sequential counting
        """
        from database import async_session, StudentProgress
        from sqlalchemy import select
        import json
        
        # Calculate points per question
        total_marks = midterm_config.total_marks
        total_questions = midterm_config.total_questions
        points_per_question = total_marks // total_questions
        
        print(f"[Midterm] {total_questions} questions, {points_per_question} points each")
        
        # Grade with adjusted max score AND total_questions for AI detection
        grader = self.get_grader()
        loop = asyncio.get_event_loop()
        
        result = await loop.run_in_executor(
            None,
            lambda: grader.grade_answer(
                bot.quiz_path, answer_path, 
                max_score=points_per_question,
                total_questions=total_questions
            )
        )
        
        annotations = result.get('annotations', [])
        score = result.get('score', 0)
        
        # Get AI-detected question numbers (fall back to sequential if not detected)
        detected_questions = result.get('question_numbers', [])
        
        # Ensure score doesn't exceed max
        score = min(score, points_per_question)
        
        # Initialize show_total flag (will be set based on last-question detection)
        show_total = False
        
        # Get or create student progress
        async with async_session() as session:
            result_db = await session.execute(
                select(StudentProgress).where(
                    StudentProgress.teacher_id == bot.teacher_id,
                    StudentProgress.student_telegram_id == sender_id
                )
            )
            progress = result_db.scalar_one_or_none()
            
            if progress is None:
                # Create new progress record
                progress = StudentProgress(
                    teacher_id=bot.teacher_id,
                    student_telegram_id=sender_id,
                    student_name=sender_name,
                    questions_answered="{}",
                    total_score=0,
                    questions_count=0
                )
                session.add(progress)
            
            # Parse existing answers
            questions_dict = json.loads(progress.questions_answered or "{}")
            
            # Determine question number(s) to update
            if detected_questions:
                # Validate and cap question numbers
                valid_questions = [q for q in detected_questions if 1 <= q <= total_questions]
                if not valid_questions:
                    print(f"[Midterm] WARNING: AI detected invalid questions {detected_questions}, falling back to sequential")
                    valid_questions = [progress.questions_count + 1]
            else:
                # Fall back to sequential if AI didn't detect
                print(f"[Midterm] No question numbers detected, using sequential")
                valid_questions = [progress.questions_count + 1]
            
            # Handle the detected question(s)
            is_resubmission = False
            for q_num in valid_questions:
                q_key = f"Q{q_num}"
                if q_key in questions_dict:
                    # Re-submission: update existing score
                    old_score = questions_dict[q_key]
                    questions_dict[q_key] = score
                    is_resubmission = True
                    print(f"[Midterm] RE-SUBMISSION: {q_key} updated from {old_score} to {score}")
                else:
                    # New question
                    questions_dict[q_key] = score
                    progress.questions_count += 1
                    print(f"[Midterm] NEW: {q_key} = {score}")
            
            # Recalculate total score from all questions
            progress.total_score = sum(questions_dict.values())
            progress.questions_answered = json.dumps(questions_dict)
            progress.student_name = sender_name
            
            await session.commit()
            
            # Calculate running total info
            current_total = progress.total_score
            questions_answered = progress.questions_count
            max_so_far = questions_answered * points_per_question
            
            # Determine if we should show the total circle
            # Show total if: 1) current answer is for last question, or 2) already answered last question
            is_last_question = max(valid_questions) == total_questions
            if is_last_question:
                progress.has_answered_last = True
                await session.commit()
            
            show_total = progress.has_answered_last
        
        # Build question label for display
        q_label = ",".join([f"Q{q}" for q in valid_questions])
        resubmit_note = " (تحديث)" if is_resubmission else ""
        
        print(f"[Midterm] Student {sender_name}: {q_label} = {score}/{points_per_question}, Total: {current_total}/{total_marks}{resubmit_note}")
        
        # Build questions_info for progress display
        answered_questions = list(questions_dict.keys())  # ["Q1", "Q3", etc.]
        questions_info = {
            "answered": answered_questions,
            "total": total_questions
        }
        
        # Annotate with running total and progress info
        annotated_path = draw_annotations_with_ocr(
            answer_path, annotations,
            score=score, 
            max_score=points_per_question,
            running_total=(current_total, total_marks),
            questions_info=questions_info,
            show_total=show_total
        )
        
        # Store the annotated image path for exam-end re-sending
        async with async_session() as session:
            progress = await session.get(StudentProgress, progress.id)
            if progress:
                progress.last_answer_image_path = str(annotated_path)
                await session.commit()
        
        # Send as scheduled message
        schedule_time = datetime.now() + timedelta(days=365)
        await bot.client.send_file(
            job['chat_id'],
            annotated_path,
            caption=f"[{q_label}] {score}/{points_per_question} | Total: {current_total}/{total_marks}{resubmit_note}",
            schedule=schedule_time
        )
        
        print(f"[Worker {worker_id}] Midterm: {sender_name} - {score}/{points_per_question} (Total: {current_total}/{total_marks})")
        annotated_path.unlink(missing_ok=True)
    
    async def start_workers(self, num_workers: int = 3):
        """Start grading workers"""
        for i in range(num_workers):
            task = asyncio.create_task(self._grading_worker(i + 1))
            self._workers.append(task)
        print(f"🚀 Started {num_workers} grading workers")
    
    async def stop_for_teacher(self, teacher_id: int):
        """Stop a bot for a specific teacher"""
        if teacher_id not in self.bots:
            return
        
        bot = self.bots[teacher_id]
        bot.is_running = False
        await bot.client.disconnect()
        del self.bots[teacher_id]
        
        print(f"🛑 Stopped bot for teacher {teacher_id}")
    
    async def update_quiz(self, teacher_id: int, quiz_path: Path):
        """Update the quiz for a teacher"""
        if teacher_id in self.bots:
            self.bots[teacher_id].quiz_path = quiz_path
            print(f"📝 Updated quiz for teacher {teacher_id}")
    
    async def stop_all(self):
        """Stop all bots and workers"""
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        
        # Disconnect all bots
        for teacher_id in list(self.bots.keys()):
            await self.stop_for_teacher(teacher_id)
        
        print("🛑 All bots stopped")
    
    async def start_all_from_db(self, db_session):
        """
        Start bots for all active teachers from database.
        Called on server startup.
        """
        from database import Teacher, Quiz
        from sqlalchemy import select
        
        # Get all active teachers
        result = await db_session.execute(
            select(Teacher).where(Teacher.is_active == True, Teacher.session_string != None)
        )
        teachers = result.scalars().all()
        
        print(f"🔄 Starting bots for {len(teachers)} teachers...")
        
        for teacher in teachers:
            # Get their active quiz
            quiz_result = await db_session.execute(
                select(Quiz).where(Quiz.teacher_id == teacher.id, Quiz.is_active == True)
            )
            quiz = quiz_result.scalar_one_or_none()
            
            quiz_path = Path(quiz.image_path) if quiz else None
            
            await self.start_for_teacher(
                teacher.id,
                teacher.session_string,
                quiz_path
            )
        
        # Start workers
        await self.start_workers(3)


# Global instance
bot_manager = BotManager()
