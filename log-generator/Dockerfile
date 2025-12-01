# Smart E-Commerce Log Generator for Anomaly Detection Framework
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy applications
COPY ecommerce_log_generator.py .
COPY unified_log_generator.py .

# Default environment variables for E-Commerce Generator
ENV ES_HOST=http://elasticsearch-dataset:9200
ENV INDEX_NAME=ecommerce-logs

# Historical data settings - MASSIVE DATA GENERATION
ENV HISTORICAL_DAYS=365
ENV HISTORICAL_BATCH_SIZE=10000
ENV BASE_REQUESTS_PER_HOUR=5000
ENV PEAK_MULTIPLIER=4.0
ENV HISTORICAL_ANOMALY_RATE=0.015

# Continuous generation settings
ENV CONTINUOUS_INTERVAL=1.0
ENV LOGS_PER_INTERVAL_MIN=50
ENV LOGS_PER_INTERVAL_MAX=150
ENV CONTINUOUS_ANOMALY_RATE=0.02

# Burst settings (flash sales, viral moments)
ENV BURST_PROBABILITY=0.03
ENV BURST_SIZE_MIN=200
ENV BURST_SIZE_MAX=1000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "ecommerce_log_generator.py" > /dev/null || exit 1

# Run the e-commerce generator by default
CMD ["python", "-u", "ecommerce_log_generator.py"]
