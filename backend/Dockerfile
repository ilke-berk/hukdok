# Base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# fitz (pymupdf) and others might need build tools or system libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Create data directory (will be mounted as volume)
RUN mkdir -p /app/data

# Expose the port the app runs on
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
