FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install system dependencies and Python packages
RUN apt-get update && apt-get install -y \
    git \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the main script
COPY kb-mcp.py .

# Create logs directory
RUN mkdir -p logs

# Expose port for MCP server (if needed)
EXPOSE 8000

# Run the kb-mcp.py script as a daemon-like process
CMD ["python", "-u", "kb-mcp.py", "--daemon"]