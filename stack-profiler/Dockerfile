FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY profiler.py .
COPY create_dashboard.py .

# Environment variables with defaults
ENV ES_URL=http://elasticsearch-dataset:9200
ENV KIBANA_URL=http://kibana:5601
ENV COLLECTION_INTERVAL=5
ENV CREATE_DASHBOARD=true

# Run the profiler
CMD ["sh", "-c", "if [ \"$CREATE_DASHBOARD\" = \"true\" ]; then python create_dashboard.py || true; fi && python profiler.py"]
