# Dockerfile for Al-Muallim Telegram Bot
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp_images directory
RUN mkdir -p temp_images

# Run the userbot
CMD ["python", "userbot.py"]
