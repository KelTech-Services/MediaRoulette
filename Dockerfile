FROM python:3.11-slim

LABEL org.opencontainers.image.title="PlexRoulette"
LABEL org.opencontainers.image.description="Can't decide what to watch? PlexRoulette randomly picks movies and TV shows from your Plex library."
LABEL org.opencontainers.image.source="https://github.com/KelTech-Services/PlexRoulette"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
