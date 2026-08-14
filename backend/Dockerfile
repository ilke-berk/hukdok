# Base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# fitz (pymupdf) and others might need build tools or system libraries
# libreoffice-writer/calc: Word/Excel -> PDF dönüşümü (headless soffice)
# fonts-liberation: Office belgelerinde Calibri/Times metrik uyumu
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ghostscript \
    fonts-dejavu-core \
    fonts-liberation \
    libreoffice-writer \
    libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Non-root kullanıcı (G6). Sabit UID: mevcut backend-data volume'u prod'da
# bir kez chown gerektirir: docker compose exec -u root backend chown -R appuser /app/data
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser

# Create data directory (will be mounted as volume)
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# Çalışan sürüm (/healthz "version" alanı) — deploy.sh git SHA'sını geçer,
# lokal build'de "dev". Son katmanlardan biri: sürüm değişimi üstteki ağır
# katmanların (apt, pip, COPY) cache'ini bozmaz.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

# Expose the port the app runs on
EXPOSE 8001

# Use entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
