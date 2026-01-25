"""Configuration module for Al-Muallim Bot"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).parent
CURRICULUM_DATA_DIR = BASE_DIR / "curriculum_data"
TEMP_IMAGES_DIR = BASE_DIR / "temp_images"

# Create directories if they don't exist
CURRICULUM_DATA_DIR.mkdir(exist_ok=True)
TEMP_IMAGES_DIR.mkdir(exist_ok=True)

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Google Cloud API Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Gemini Model Configuration  
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
THINKING_LEVEL = os.getenv("THINKING_LEVEL", "high")

# Grading Configuration
MAX_SCORE = 10
CURRICULUM_FILE = CURRICULUM_DATA_DIR / "curriculum.json"

# Color codes for annotations
ANNOTATION_COLORS = {
    "correct": "green",
    "mistake": "red",
    "partial": "yellow",
    "unclear": "orange"
}
