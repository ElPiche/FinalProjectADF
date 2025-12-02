FROM python:3.11-slim

WORKDIR /app

# Conservative defaults for validation/timeout behavior (overridable at runtime)
ENV EXTRACTOR_VALIDATION_TIMEOUT_SECONDS=10 \
    ELASTICSEARCH_SQL_PREVIEW_TIMEOUT_SECONDS=5 \
    ELASTICSEARCH_SQL_QUERY_TIMEOUT_SECONDS=30 \
    MIN_TRAINING_WINDOW_SECONDS=1 \
    MIN_DETECTION_WINDOW_SECONDS=1 \
    LARGE_WINDOW_THRESHOLD_DAYS=30 \
    ENFORCE_UNIQUE_CONFIG_NAMES=false \
    LOG_LEVEL=INFO

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install system dependencies and Python packages
RUN apt-get update && apt-get install -y \
    git \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy all Python modules and packages
COPY *.py .
COPY mcp_tools_pkg/ ./mcp_tools_pkg/
COPY tests/ ./tests/

# Note: 
# - shared/ directory is mounted as volume in docker-compose.yml
# - mcp_tools/ directory is NOT copied (it's a dev-time split package)
#   The mcp_tools.py file is the main module used at runtime

# Create logs directory
RUN mkdir -p logs

# Expose port for MCP server (if needed)
EXPOSE 8000

# Run the kb-mcp.py script as a daemon-like process
CMD ["python", "-u", "kb-mcp.py", "--daemon"]