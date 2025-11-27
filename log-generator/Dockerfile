# Unified Log Generator for Anomaly Detection Framework
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY unified_log_generator.py .

# Default environment variables
ENV ES_HOST=http://elasticsearch-dataset:9200
ENV INDEX_NAME=app-logs
ENV HISTORICAL_DAYS=365
ENV HISTORICAL_BATCH_SIZE=5000
ENV HISTORICAL_ANOMALY_RATE=0.02
ENV CONTINUOUS_INTERVAL=1.0
ENV LOGS_PER_INTERVAL_MIN=15
ENV LOGS_PER_INTERVAL_MAX=30
ENV CONTINUOUS_ANOMALY_RATE=0.02
ENV BURST_PROBABILITY=0.05
ENV BURST_SIZE_MIN=50
ENV BURST_SIZE_MAX=200

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "unified_log_generator.py" > /dev/null || exit 1

# Run the unified generator
CMD ["python", "-u", "unified_log_generator.py"]
