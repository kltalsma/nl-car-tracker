FROM python:3.11-slim

# Install system dependencies for Chrome, Selenium, and Docker CLI
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    docker.io \
    docker-compose \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/logs/screenshots /app/data/backups

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Expose Flask port
EXPOSE 5000

# Default command (can be overridden in docker-compose)
CMD ["python", "app/app.py"]

# Fix permissions for non-root user
RUN chmod -R 777 /app/data /app/logs && \
    chmod 666 /app/config.yaml
