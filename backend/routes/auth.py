"""
Authentication routes - Telegram login flow
"""
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError

from database import get_db, Teacher, PendingAuth

router = APIRouter()

# Telegram API credentials (same as userbot)
API_ID = os.getenv("TELEGRAM_API_ID", "30619302")
API_HASH = os.getenv("TELEGRAM_API_HASH", "a501dc4dd3e7e2288cdc3dc18ff9e3ce")


class SendCodeRequest(BaseModel):
    phone: str


class SendCodeResponse(BaseModel):
    success: bool
    message: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str
    password: str | None = None  # For 2FA accounts


class VerifyCodeResponse(BaseModel):
    success: bool
    message: str
    teacher_id: int | None = None
    first_name: str | None = None


# Store temporary clients for auth flow
_auth_clients: dict[str, TelegramClient] = {}


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(request: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 1: Send verification code to phone number
    """
    phone = request.phone.strip()
    
    # Normalize phone number
    if not phone.startswith("+"):
        phone = "+" + phone
    
    try:
        # Create a temporary client with StringSession for this auth flow
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        # Send the code
        result = await client.send_code_request(phone)
        
        # Store the phone_code_hash in database
        # Check for existing pending auth and update or create new
        existing = await db.execute(
            select(PendingAuth).where(PendingAuth.phone == phone)
        )
        existing_auth = existing.scalar_one_or_none()
        
        if existing_auth:
            # Update existing record
            existing_auth.phone_code_hash = result.phone_code_hash
            existing_auth.created_at = datetime.utcnow()
        else:
            # Create new pending auth
            pending = PendingAuth(
                phone=phone,
                phone_code_hash=result.phone_code_hash
            )
            db.add(pending)
        
        await db.commit()
        
        # Store client for verification step
        _auth_clients[phone] = client
        
        return SendCodeResponse(
            success=True,
            message="تم إرسال رمز التحقق إلى تيليجرام"
        )
        
    except Exception as e:
        return SendCodeResponse(
            success=False,
            message=f"خطأ: {str(e)}"
        )


@router.post("/verify", response_model=VerifyCodeResponse)
async def verify_code(request: VerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    """
    Step 2: Verify the code and create session
    """
    phone = request.phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    
    code = request.code.strip()
    
    # Get pending auth
    result = await db.execute(
        select(PendingAuth).where(PendingAuth.phone == phone)
    )
    pending = result.scalar_one_or_none()
    
    if not pending:
        raise HTTPException(status_code=400, detail="لم يتم طلب رمز لهذا الرقم")
    
    # Get the client
    client = _auth_clients.get(phone)
    if not client:
        raise HTTPException(status_code=400, detail="انتهت صلاحية الجلسة، أعد المحاولة")
    
    try:
        # Try to sign in
        await client.sign_in(phone, code, phone_code_hash=pending.phone_code_hash)
        
    except SessionPasswordNeededError:
        # 2FA is enabled
        if not request.password:
            raise HTTPException(status_code=400, detail="هذا الحساب يتطلب كلمة مرور المصادقة الثنائية")
        
        await client.sign_in(password=request.password)
        
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح")
    
    except PhoneCodeExpiredError:
        raise HTTPException(status_code=400, detail="انتهت صلاحية رمز التحقق")
    
    # Get user info
    me = await client.get_me()
    
    # Save session string
    session_string = client.session.save()
    
    # Check if teacher already exists
    existing = await db.execute(
        select(Teacher).where(Teacher.phone == phone)
    )
    teacher = existing.scalar_one_or_none()
    
    if teacher:
        # Update existing
        teacher.telegram_id = me.id
        teacher.first_name = me.first_name
        teacher.session_string = session_string
        teacher.last_login = datetime.utcnow()
        teacher.is_active = True
    else:
        # Create new
        teacher = Teacher(
            phone=phone,
            telegram_id=me.id,
            first_name=me.first_name,
            session_string=session_string,
            last_login=datetime.utcnow()
        )
        db.add(teacher)
    
    # Clean up pending auth
    await db.delete(pending)
    
    # Commit all changes
    await db.commit()
    
    # Refresh to get ID
    await db.refresh(teacher)
    
    # Clean up client from temp storage
    del _auth_clients[phone]
    
    # TODO: Start userbot for this teacher
    # await bot_manager.start_for_teacher(teacher.id, session_string)
    
    return VerifyCodeResponse(
        success=True,
        message="تم تسجيل الدخول بنجاح!",
        teacher_id=teacher.id,
        first_name=me.first_name
    )


@router.post("/logout")
async def logout(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """
    Log out a teacher - stop their bot and deactivate session
    """
    result = await db.execute(
        select(Teacher).where(Teacher.id == teacher_id)
    )
    teacher = result.scalar_one_or_none()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    teacher.is_active = False
    teacher.session_string = None
    await db.commit()
    
    # TODO: Stop userbot for this teacher
    # await bot_manager.stop_for_teacher(teacher_id)
    
    return {"success": True, "message": "تم تسجيل الخروج"}
