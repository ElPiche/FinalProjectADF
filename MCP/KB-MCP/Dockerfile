FROM python:3.11-slim

WORKDIR /app

COPY server.py .

RUN apt-get update && apt-get install -y git && \
    pip install git+https://github.com/modelcontextprotocol/python-sdk.git croniter elasticsearch==8.15.0 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

CMD ["python", "server.py"]