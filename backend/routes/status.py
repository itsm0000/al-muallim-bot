"""
Status routes - check bot and teacher status
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Teacher, Quiz, GradingLog

router = APIRouter()


class StatusResponse(BaseModel):
    total_teachers: int
    active_teachers: int
    total_gradings: int


@router.get("/", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    """
    Get overall system status
    """
    # Count teachers
    total_result = await db.execute(select(func.count(Teacher.id)))
    total_teachers = total_result.scalar()
    
    active_result = await db.execute(
        select(func.count(Teacher.id)).where(Teacher.is_active == True)
    )
    active_teachers = active_result.scalar()
    
    # Count gradings
    gradings_result = await db.execute(select(func.count(GradingLog.id)))
    total_gradings = gradings_result.scalar()
    
    return StatusResponse(
        total_teachers=total_teachers or 0,
        active_teachers=active_teachers or 0,
        total_gradings=total_gradings or 0
    )


@router.get("/teacher/{teacher_id}")
async def get_teacher_status(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get status for a specific teacher
    """
    # Get teacher
    result = await db.execute(
        select(Teacher).where(Teacher.id == teacher_id)
    )
    teacher = result.scalar_one_or_none()
    
    if not teacher:
        return {"found": False}
    
    # Get current quiz
    quiz_result = await db.execute(
        select(Quiz).where(Quiz.teacher_id == teacher_id, Quiz.is_active == True)
    )
    quiz = quiz_result.scalar_one_or_none()
    
    # Count gradings for this teacher
    gradings_result = await db.execute(
        select(func.count(GradingLog.id)).where(GradingLog.teacher_id == teacher_id)
    )
    grading_count = gradings_result.scalar()
    
    return {
        "found": True,
        "teacher": {
            "id": teacher.id,
            "first_name": teacher.first_name,
            "phone": teacher.phone[:4] + "****" + teacher.phone[-2:],  # Mask phone
            "is_active": teacher.is_active,
            "last_login": teacher.last_login.isoformat() if teacher.last_login else None
        },
        "has_quiz": quiz is not None,
        "total_gradings": grading_count or 0,
        "bot_running": teacher.is_active and teacher.session_string is not None
    }
