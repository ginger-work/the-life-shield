FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir pg8000==1.31.2

# Expose port
EXPOSE 8000

# Copy application code
COPY . .

# Start command - shell form so $PORT expands
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
