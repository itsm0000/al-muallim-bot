"""
Quiz management routes
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Teacher, Quiz, MidtermConfig
from bot_manager import bot_manager

router = APIRouter()

QUIZZES_DIR = Path(__file__).parent.parent / "quizzes"


class MidtermConfigRequest(BaseModel):
    teacher_id: int
    is_active: bool
    total_questions: int = 6
    total_marks: int = 100
class QuizResponse(BaseModel):
    id: int
    image_url: str
    created_at: datetime
    is_active: bool


@router.post("/upload")
async def upload_quiz(
    teacher_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a new quiz image for a teacher
    """
    # Verify teacher exists
    result = await db.execute(
        select(Teacher).where(Teacher.id == teacher_id)
    )
    teacher = result.scalar_one_or_none()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    # Validate file type - accept images OR PDFs
    allowed_types = ["image/", "application/pdf"]
    is_valid = any(
        file.content_type.startswith(t) if t.endswith("/") else file.content_type == t 
        for t in allowed_types
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="File must be an image or PDF")
    
    # Create directory for teacher if not exists
    teacher_dir = QUIZZES_DIR / str(teacher_id)
    teacher_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"quiz_{timestamp}.{ext}"
    file_path = teacher_dir / filename
    
    # Save file
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Deactivate all previous quizzes for this teacher
    old_quizzes = await db.execute(
        select(Quiz).where(Quiz.teacher_id == teacher_id, Quiz.is_active == True)
    )
    for old_quiz in old_quizzes.scalars():
        old_quiz.is_active = False
    
    # Create new quiz record
    quiz = Quiz(
        teacher_id=teacher_id,
        image_path=str(file_path),
        is_active=True
    )
    db.add(quiz)
    await db.commit()
    
    await db.refresh(quiz)
    
    # Update the quiz path for the running bot (if bot is running)
    await bot_manager.update_quiz(teacher_id, file_path)
    
    return {
        "success": True,
        "message": "تم رفع الاختبار بنجاح!",
        "quiz_id": quiz.id,
        "image_path": str(file_path)
    }


@router.get("/current/{teacher_id}")
async def get_current_quiz(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get the current active quiz for a teacher
    """
    result = await db.execute(
        select(Quiz).where(Quiz.teacher_id == teacher_id, Quiz.is_active == True)
    )
    quiz = result.scalar_one_or_none()
    
    if not quiz:
        return {"has_quiz": False, "quiz": None}
    
    return {
        "has_quiz": True,
        "quiz": {
            "id": quiz.id,
            "created_at": quiz.created_at.isoformat(),
            "image_path": quiz.image_path
        }
    }


@router.get("/history/{teacher_id}")
async def get_quiz_history(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get all quizzes for a teacher (history)
    """
    result = await db.execute(
        select(Quiz).where(Quiz.teacher_id == teacher_id).order_by(Quiz.created_at.desc())
    )
    quizzes = result.scalars().all()
    
    return {
        "quizzes": [
            {
                "id": q.id,
                "created_at": q.created_at.isoformat(),
                "is_active": q.is_active
            }
            for q in quizzes
        ]
    }


@router.post("/midterm-config")
async def set_midterm_config(
    config: MidtermConfigRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Set or update midterm mode configuration for a teacher.
    
    When is_active=True, the bot grades in midterm mode:
    - Total marks = 100 (configurable)
    - Each question = 100 / total_questions
    - Running totals tracked per student
    """
    # Get or create config
    result = await db.execute(
        select(MidtermConfig).where(MidtermConfig.teacher_id == config.teacher_id)
    )
    midterm = result.scalar_one_or_none()
    
    if midterm is None:
        midterm = MidtermConfig(
            teacher_id=config.teacher_id,
            is_active=config.is_active,
            total_questions=config.total_questions,
            total_marks=config.total_marks
        )
        db.add(midterm)
    else:
        midterm.is_active = config.is_active
        midterm.total_questions = config.total_questions
        midterm.total_marks = config.total_marks
    
    await db.commit()
    
    mode = "midterm" if config.is_active else "quiz"
    return {
        "success": True,
        "message": f"Mode set to {mode}",
        "config": {
            "is_active": midterm.is_active,
            "total_questions": midterm.total_questions,
            "total_marks": midterm.total_marks,
            "points_per_question": midterm.total_marks // midterm.total_questions
        }
    }


@router.get("/midterm-config/{teacher_id}")
async def get_midterm_config(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """Get current midterm configuration for a teacher"""
    result = await db.execute(
        select(MidtermConfig).where(MidtermConfig.teacher_id == teacher_id)
    )
    midterm = result.scalar_one_or_none()
    
    if midterm is None:
        return {
            "is_active": False,
            "total_questions": 6,
            "total_marks": 100,
            "points_per_question": 16
        }
    
    return {
        "is_active": midterm.is_active,
        "total_questions": midterm.total_questions,
        "total_marks": midterm.total_marks,
        "points_per_question": midterm.total_marks // midterm.total_questions
    }


@router.post("/reset-student-progress/{teacher_id}")
async def reset_student_progress(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """
    Reset all student progress for a teacher (for new midterm exam).
    Call this when starting a new midterm to clear old running totals.
    """
    from database import StudentProgress
    
    result = await db.execute(
        select(StudentProgress).where(StudentProgress.teacher_id == teacher_id)
    )
    progress_records = result.scalars().all()
    
    for record in progress_records:
        await db.delete(record)
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Reset progress for {len(progress_records)} students"
    }

