# Get the official Playwright image
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set the working folder
WORKDIR /app

# 1. THE FIX: Force Python to print logs immediately (No buffering)
ENV PYTHONUNBUFFERED=1

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium browser
RUN playwright install chromium

# Copy the rest of your code
COPY . .

# Run the bot
CMD ["python3", "loop_bot.py"]