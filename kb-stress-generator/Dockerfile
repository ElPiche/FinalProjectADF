FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stress_generator.py .

# Default environment variables
ENV MONGODB_URI="mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"
ENV MONGODB_DB="knowledge_base"
ENV MONGODB_COLLECTION="kb_configs"
ENV BUCKET_COLLECTION="bucket_profiles"
ENV ES_URL="http://elasticsearch-dataset:9200"
ENV MODE="continuous"
ENV MIN_INTERVAL="10"
ENV MAX_INTERVAL="60"
ENV BURST_PROBABILITY="0.1"
ENV BURST_SIZE_MIN="3"
ENV BURST_SIZE_MAX="10"
ENV BUCKET_PROBABILITY="0.3"
ENV ALGORITHM_REGISTRY_PATH="/app/registry/algorithms.json"

CMD ["python", "-u", "stress_generator.py"]
