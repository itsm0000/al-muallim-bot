"""
Quiz management routes
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Teacher, Quiz

router = APIRouter()

QUIZZES_DIR = Path(__file__).parent.parent / "quizzes"


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
    
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
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
    
    async with db.begin():
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
    
    await db.refresh(quiz)
    
    # TODO: Notify bot manager to update quiz for this teacher
    # await bot_manager.update_quiz(teacher_id, file_path)
    
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
