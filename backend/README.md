# Al-Muallim Backend API

FastAPI backend for the multi-tenant PWA grading system.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

## API Endpoints

- `POST /auth/send-code` - Start Telegram login
- `POST /auth/verify` - Verify SMS code
- `POST /quiz/upload` - Upload quiz image
- `GET /status` - Check bot status
