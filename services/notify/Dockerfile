# Multi-stage build for notification service
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r notifyuser && useradd -r -g notifyuser notifyuser

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/notifyuser/.local

# Copy application code
COPY app/ ./app/
COPY worker.py .

# Create necessary directories and set permissions
RUN mkdir -p /app/logs && \
    chown -R notifyuser:notifyuser /app

# Switch to non-root user
USER notifyuser

# Add local Python packages to PATH
ENV PATH=/home/notifyuser/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8006/health/live || exit 1

# Expose port
EXPOSE 8006

# Default command (can be overridden)
CMD ["celery", "-A", "worker", "worker", "--loglevel=info"] 