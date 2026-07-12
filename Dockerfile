# Production Dockerfile for NaijaBoost AI — Dual-Brain Conversational SMM Layer
# Target Platform: Google Cloud Run (Port 8080)
FROM python:3.12-slim

# Prevent Python from writing bytecode (`.pyc` files) and enable unbuffered logging for cloud monitoring
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install system dependencies required for building and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies without cache
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create a non-privileged system user for secure container execution
RUN useradd -m -u 1000 naijaboost && \
    mkdir -p ${APP_HOME} && \
    chown -R naijaboost:naijaboost ${APP_HOME}

# Copy workspace code and templates
COPY --chown=naijaboost:naijaboost . .

# Switch to non-privileged user
USER naijaboost

# Expose Google Cloud Run target port
EXPOSE 8080

# Execute FastAPI application with Uvicorn worker bound to 0.0.0.0:8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
