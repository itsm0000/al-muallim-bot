# Quick Setup Guide

## Prerequisites
- Python 3.9+
- Telegram Bot Token
- Google Cloud API Key (with Gemini 3 Pro access)

## FastSetup Steps

### 1. Install Dependencies
```bash
# Navigate to project directory
cd al-muallim-bot

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install all packages
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
# Copy the example file
copy .env.example .env

# Edit .env and add your API keys:
# TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
# GOOGLE_API_KEY=your_google_cloud_api_key
```

### 3. Extract Curriculum
```bash
# Run the ingestion script
python scripts\ingest_curriculum.py

# Verify output
dir curriculum_data\curriculum.json
```

### 4. Run the Bot
```bash
python bot.py
```

## Getting API Keys

### Telegram Bot Token
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow instructions to create your bot
4. Copy the token provided

### Google Cloud API Key
1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key
3. Ensure Gemini API is enabled
4. Copy the API key

## Verification

After starting the bot, you should see:
```
Starting Al-Muallim Bot
Bot is running... Press Ctrl+C to stop
```

Test in Telegram:
1. Find your bot by username
2. Send `/start`
3. Send `/grade` to begin grading

## Troubleshooting

**"ModuleNotFoundError: No module named 'X'"**
- Ensure virtual environment is activated
- Re-run: `python -m pip install -r requirements.txt`

**"TELEGRAM_BOT_TOKEN not found"**
- Create `.env` file from `.env.example`
- Add your actual API tokens

**"Curriculum file not found"**
- Run: `python scripts\ingest_curriculum.py`
- Ensure PDF files are in parent directory

## Project Structure
```
al-muallim-bot/
├── bot.py                    # Start here - main bot entry
├── config.py                 # Configuration
├── requirements.txt          # Dependencies
├── .env                      # Your API keys (create this!)
├── handlers/
│   └── upload_handler.py     # Image upload logic
├── grading/
│   ├── grader.py             # Gemini 3 Pro integration
│   └── annotator.py          # Image annotation
└── scripts/
    └── ingest_curriculum.py  # PDF processor
```

## Next Steps

After setup:
1. Test with sample questions
2. Adjust grading prompts if needed (see `grading/grader.py`)
3. Monitor logs in `bot.log`
4. Share your bot with students!
