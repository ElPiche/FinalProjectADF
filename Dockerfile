# Imagen base con Python
FROM python:3.11-slim

# Crear carpeta de trabajo
WORKDIR /MotorDA/

COPY requirements.txt .

# Copiar script
COPY MotorDA ./MotorDA

# Instalar dependencias necesarias
RUN pip install --no-cache-dir -r requirements.txt

# Comando de ejecución por defecto
CMD ["python", "-m" ,"Dispatcher.DADispatcher"]