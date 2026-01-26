# Get the official Playwright image (comes with Python + Linux libraries pre-installed)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set the working folder
WORKDIR /app

# Copy the requirements file and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium browser specifically
RUN playwright install chromium

# Copy the rest of your code
COPY . .

# Run the bot
CMD ["python3", "loop_bot.py"]