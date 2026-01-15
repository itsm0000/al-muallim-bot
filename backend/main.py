"""
Al-Muallim Backend API
Multi-tenant PWA for Telegram grading bot
"""
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from database import init_db, async_session
from routes import auth, quiz, status
from bot_manager import bot_manager

load_dotenv()

# Create necessary directories
SESSIONS_DIR = Path(__file__).parent / "sessions"
QUIZZES_DIR = Path(__file__).parent / "quizzes"
SESSIONS_DIR.mkdir(exist_ok=True)
QUIZZES_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: Initialize database
    await init_db()
    print("✅ Database initialized")
    
    # Start bot manager for all active sessions
    async with async_session() as session:
        await bot_manager.start_all_from_db(session)
    
    yield
    
    # Shutdown: Stop all bots
    await bot_manager.stop_all()
    print("👋 Shutting down")


app = FastAPI(
    title="Al-Muallim API",
    description="Backend for multi-tenant Telegram grading bot",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for PWA frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(quiz.router, prefix="/quiz", tags=["Quiz Management"])
app.include_router(status.router, prefix="/status", tags=["Status"])


@app.get("/")
async def root():
    return {"message": "Al-Muallim API", "status": "running"}
