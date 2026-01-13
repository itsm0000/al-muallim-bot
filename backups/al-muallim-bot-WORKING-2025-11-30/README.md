# Al-Muallim AI Physics Bot

An intelligent Telegram bot that grades handwritten physics exams using AI-powered analysis with Google's Gemini 3 Pro model.

## Features

- 📝 Grades handwritten physics exams automatically
- 🎯 Provides detailed feedback in Arabic
- 🖼️ Annotates images with color-coded corrections
- 🤖 Uses Gemini 3 Pro with "thinking mode" for deep reasoning
- 📚 References uploaded curriculum as the source of truth

## Prerequisites

- Python 3.9 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Cloud API Key with Gemini 3 Pro access

## Installation

1. **Clone or navigate to the project directory**:
   ```bash
   cd al-muallim-bot
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**:
   - Copy `.env.example` to `.env`
   - Fill in your API keys:
     ```
     TELEGRAM_BOT_TOKEN=your_telegram_bot_token
     GOOGLE_API_KEY=your_google_api_key
     ```

## Setup

### 1. Ingest Curriculum PDFs

Before running the bot, you need to extract the curriculum from the PDF files:

```bash
python scripts/ingest_curriculum.py
```

This will:
- Parse the two curriculum PDFs
- Extract text content
- Save to `curriculum_data/curriculum.json`

### 2. Verify Setup

Verify that the curriculum was extracted successfully:

```bash
# Check if curriculum.json exists
dir curriculum_data\curriculum.json
```

## Running the Bot

Start the bot:

```bash
python bot.py
```

You should see:
```
Starting Al-Muallim Bot
Bot is running... Press Ctrl+C to stop
```

## Usage

1. **Start a conversation** with your bot on Telegram
2. Send `/start` to see the welcome message
3. Send `/grade` to begin grading
4. Upload the **question image**
5. Upload the **student's answer image**
6. Wait for the AI to grade (10-30 seconds)
7. Receive annotated image with score and feedback

### Available Commands

- `/start` - Welcome message and bot introduction
- `/grade` - Start a new grading session
- `/help` - Display help information
- `/cancel` - Cancel current grading session

### Color Coding

The bot annotates images with colored bounding boxes:

- 🟢 **Green**: Correct step
- 🔴 **Red**: Mistake
- 🟡 **Yellow**: Partially correct
- 🟠 **Orange**: Unclear/ambiguous

## Project Structure

```
al-muallim-bot/
├── bot.py                  # Main bot entry point
├── config.py               # Configuration and environment variables
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variable template
├── .gitignore             # Git ignore rules
├── handlers/
│   └── upload_handler.py  # Image upload conversation flow
├── grading/
│   ├── grader.py          # AI grading engine (Gemini 3 Pro)
│   └── annotator.py       # Image annotation with Pillow
├── scripts/
│   └── ingest_curriculum.py  # PDF curriculum extraction
├── utils/
│   └── logger.py          # Logging utility with Arabic support
├── curriculum_data/       # Extracted curriculum JSON
└── temp_images/           # Temporary image storage
```

## Technical Details

### AI Model

- **Model**: `gemini-3-pro-preview`
- **Thinking Level**: `high` (enables deep reasoning)
- **Temperature**: `0.1` (for consistent grading)
- **Output Format**: Structured JSON

### Curriculum Format

The curriculum is stored as JSON:

```json
{
  "الكلاميات": {
    "source_file": "filename.pdf",
    "pages": [
      {
        "page_num": 1,
        "text": "..."
      }
    ]
  },
  "المسائل": {
    ...
  }
}
```

### Grading Response Format

The AI returns:

```json
{
  "score": 8,
  "feedback_ar": "الحل صحيح بشكل عام...",
  "annotations": [
    {
      "coords": [100, 50, 150, 200],
      "color": "correct",
      "note_ar": "خطوة صحيحة"
    }
  ]
}
```

## Troubleshooting

### "Curriculum file not found"
Run the ingestion script:
```bash
python scripts/ingest_curriculum.py
```

### "Invalid API key"
- Verify your `.env` file has the correct keys
- Ensure your Google Cloud project has Gemini API enabled

### Bot not responding
- Check that the bot is running (`python bot.py`)
- Verify your Telegram token is correct
- Check the logs in `bot.log`

### Arabic text not displaying
- Ensure your terminal/console supports UTF-8
- The bot uses UTF-8 encoding for all Arabic text

## Development

### Adding New Features

1. Handlers go in `handlers/`
2. Grading logic goes in `grading/`
3. Utilities go in `utils/`
4. Update `config.py` for new settings

### Logging

All modules use the centralized logger:

```python
from utils.logger import setup_logger
logger = setup_logger("module_name")
logger.info("Message")
```

Logs are written to:
- Console (INFO level)
- `bot.log` file (DEBUG level)

## License

This project is for educational purposes.

## Credits

- **AI Model**: Google Gemini 3 Pro
- **Curriculum**: حسين محمد - فيزياء 2025
- **Framework**: python-telegram-bot
