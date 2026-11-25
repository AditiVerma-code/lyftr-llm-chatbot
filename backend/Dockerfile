# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilation tools if needed for any binary packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime shared libraries required by soundfile/litellm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /install /usr/local

# Create data directory for SQLite persistent volume
RUN mkdir -p /data && chmod 777 /data

# Copy application source code
COPY . .

# Set default environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/app.db \
    ENABLE_FAILURE_SIMULATION=true \
    ALLOWED_ORIGINS=*

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
