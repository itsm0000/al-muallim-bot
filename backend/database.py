"""
Database models and initialization
"""
from datetime import datetime
from pathlib import Path
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = "sqlite+aiosqlite:///./almuallim.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class Teacher(Base):
    """Teacher account linked to Telegram"""
    __tablename__ = "teachers"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    first_name = Column(String, nullable=True)
    session_string = Column(Text, nullable=True)  # Encrypted session data
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    quizzes = relationship("Quiz", back_populates="teacher")


class Quiz(Base):
    """Quiz images per teacher"""
    __tablename__ = "quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))
    image_path = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    teacher = relationship("Teacher", back_populates="quizzes")


class GradingLog(Base):
    """Log of grading operations"""
    __tablename__ = "grading_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))
    student_id = Column(Integer)
    student_name = Column(String, nullable=True)
    score = Column(Integer, nullable=True)
    graded_at = Column(DateTime, default=datetime.utcnow)


# Pending auth sessions (phone_code_hash storage)
class PendingAuth(Base):
    """Temporary storage for Telegram auth flow"""
    __tablename__ = "pending_auth"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    phone_code_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class MidtermConfig(Base):
    """
    Midterm exam configuration per teacher.
    
    When is_active=True, the bot operates in midterm mode:
    - Scores are out of 100 total
    - Each question worth (100 / total_questions) points
    - Running totals are tracked per student
    """
    __tablename__ = "midterm_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), unique=True)
    is_active = Column(Boolean, default=False)  # True = midterm mode, False = quiz mode
    total_questions = Column(Integer, default=6)  # Number of questions in the midterm
    total_marks = Column(Integer, default=100)  # Total marks (usually 100)
    exam_end_time = Column(DateTime, nullable=True)  # When exam ends - triggers final grades
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudentProgress(Base):
    """
    Track running totals per student per teacher during midterm exams.
    
    Each time a student submits an answer, this record is updated with:
    - Which question(s) they answered
    - Their score on each question
    - Running total so far
    """
    __tablename__ = "student_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))
    student_telegram_id = Column(Integer)  # Telegram user ID of the student
    student_name = Column(String, nullable=True)
    questions_answered = Column(Text, default="{}")  # JSON: {"Q1": 20, "Q2": 25, ...}
    total_score = Column(Integer, default=0)
    questions_count = Column(Integer, default=0)  # Number of questions answered
    has_answered_last = Column(Boolean, default=False)  # True after answering last question number
    last_answer_image_path = Column(String, nullable=True)  # For re-sending at exam end
    final_grade_sent = Column(Boolean, default=False)  # Prevent duplicate final sends
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


async def init_db():
    """Create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for getting database session"""
    async with async_session() as session:
        yield session
