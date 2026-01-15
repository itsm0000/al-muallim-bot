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
        """Worker that processes grading jobs"""
        print(f"🔧 Worker {worker_id} started")
        
        while True:
            try:
                job = await self._grading_queue.get()
                
                bot = job['bot']
                event = job['event']
                sender_name = job['sender_name']
                
                print(f"🔧 Worker {worker_id}: Grading for teacher {bot.teacher_id}")
                
                try:
                    # Download the photo
                    answer_path = TEMP_IMAGES_DIR / f"answer_{bot.teacher_id}_{event.id}.jpg"
                    await bot.client.download_media(event.photo, answer_path)
                    
                    # Grade
                    grader = self.get_grader()
                    loop = asyncio.get_event_loop()
                    
                    result = await loop.run_in_executor(
                        None,
                        lambda: grader.grade_answer(bot.quiz_path, answer_path)
                    )
                    
                    # Annotate
                    annotations = result.get('annotations', [])
                    score = result.get('score', 0)
                    annotated_path = draw_annotations_with_ocr(answer_path, annotations, score=score)
                    
                    # Send as scheduled message (draft)
                    schedule_time = datetime.now() + timedelta(days=365)
                    await bot.client.send_file(
                        job['chat_id'],
                        annotated_path,
                        caption=f"🎯 النتيجة: {score}/10",
                        schedule=schedule_time
                    )
                    
                    print(f"✅ Worker {worker_id}: Graded {sender_name} - {score}/10")
                    
                    # Cleanup
                    answer_path.unlink(missing_ok=True)
                    annotated_path.unlink(missing_ok=True)
                    
                except Exception as e:
                    print(f"❌ Worker {worker_id} error: {e}")
                
                finally:
                    self._grading_queue.task_done()
                    
            except asyncio.CancelledError:
                break
    
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
