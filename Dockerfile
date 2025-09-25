# Imagen base con Python
FROM python:3.11-slim

# Crear carpeta de trabajo
WORKDIR /app

# Copiar script
COPY da-algorithm-zScore.py .

# Instalar dependencias necesarias
RUN pip install --no-cache-dir pandas numpy

# Comando de ejecución por defecto
CMD ["python", "da-algorithm-zScore.py"]

FROM docker.elastic.co/logstash/logstash:8.19.4 AS logstash-mongo

#Instalación plugin mongo db para logstash
RUN logstash-plugin install logstash-output-mongodb