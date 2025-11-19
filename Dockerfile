FROM python:3.11-slim

# Install system dependencies for Chrome, Selenium, and Docker CLI
RUN apt-get update && apt-get install -y     wget     gnupg     unzip     curl     chromium     chromium-driver     docker.io     docker-compose     && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy ONLY requirements for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories (but don't copy code - use volumes)
RUN mkdir -p /app/data /app/logs /app/logs/screenshots /app/data/backups

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Expose Flask port
EXPOSE 5000

# Default command (can be overridden in docker-compose)
CMD ["python", "app/app.py"]
