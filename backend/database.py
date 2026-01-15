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


async def init_db():
    """Create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for getting database session"""
    async with async_session() as session:
        yield session
