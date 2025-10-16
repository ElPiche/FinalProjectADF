# Guía de Deployment con Docker

Esta guía explica cómo construir y ejecutar el servicio ETL usando Docker y docker-compose.

## 🚀 Inicio Rápido

### 1. Levantar la infraestructura completa

```bash
# Levantar todos los servicios (MongoDB, Elasticsearch, Kibana)
docker-compose up -d mongodb elasticsearch-dataset kibana

# Esperar a que los servicios estén listos (verificar logs)
docker-compose logs -f kibana-init
```

### 2. Instalar datos de ejemplo de Kibana

```bash
# El servicio kibana-init se encarga automáticamente de:
# - Esperar a que Kibana esté disponible
# - Instalar los sample data logs
# - Detener Kibana para liberar recursos

# Verificar que los datos se instalaron correctamente
curl "http://localhost:9200/kibana_sample_data_logs/_count"
```

### 3. Configurar MongoDB con configuraciones ETL

**Nota**: Las configuraciones ETL deben estar presentes en MongoDB antes de ejecutar el servicio. El servicio asume que las configuraciones ya existen en la base de datos `etl_config`.

Para verificar o crear configuraciones manualmente:

```bash
# Conectar a MongoDB
docker exec -it mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin

# Cambiar a base de datos de configuración
use etl_config;

# Verificar configuraciones existentes
db.etl_configurations.find().pretty();
```

### 4. Construir y levantar el servicio ETL

```bash
# Construir la imagen del extractor
docker-compose build extractor

# Levantar el servicio ETL
docker-compose up -d extractor

# Verificar logs del servicio
docker-compose logs -f extractor
```

## 📊 Verificación del Funcionamiento

### Health Checks

```bash
# Verificar salud de la aplicación
curl http://localhost:8080/actuator/health

# Verificar métricas
curl http://localhost:8080/actuator/metrics
```

### Verificar Conexiones

```bash
# Verificar conexión a Elasticsearch
curl http://localhost:9200/_cat/health

# Verificar conexión a MongoDB
docker exec mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin --eval "db.adminCommand('ping')"
```

### Verificar Configuraciones ETL

```bash
# Conectar a MongoDB y verificar configuraciones
docker exec -it mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin

# Dentro de mongosh:
use etl_config;
db.etl_configurations.find().pretty();
```

### Verificar Datos Procesados

```bash
# Verificar datos procesados en MongoDB target
docker exec -it mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin

# Dentro de mongosh:
use etl_target;
db.sample_logs_analysis.find().limit(5).pretty();
db.etl_execution_logs.find().sort({startTime: -1}).limit(5).pretty();
```

## 🛠️ Comandos Útiles

### Manejo de Servicios

```bash
# Detener todos los servicios
docker-compose down

# Detener y eliminar volúmenes (¡CUIDADO! Elimina todos los datos)
docker-compose down -v

# Reconstruir imagen del extractor
docker-compose build --no-cache extractor

# Ver logs en tiempo real
docker-compose logs -f extractor

# Reiniciar solo el servicio extractor
docker-compose restart extractor
```

### Debugging

```bash
# Ejecutar bash dentro del contenedor extractor
docker-compose exec extractor /bin/bash

# Ver variables de entorno del contenedor
docker-compose exec extractor env

# Verificar archivos de configuración
docker-compose exec extractor cat /app/application-docker.properties
```

### Monitoreo

```bash
# Ver recursos utilizados por los contenedores
docker stats

# Ver logs específicos con timestamp
docker-compose logs -f --timestamps extractor

# Ver solo errores en los logs
docker-compose logs extractor | grep ERROR
```

## 🔧 Configuración Personalizada

### Modificar Configuraciones ETL

1. **Conectar a MongoDB**:
   ```bash
   docker exec -it mongodb mongosh --username admin --password 1q2w3E* --authenticationDatabase admin
   ```

2. **Agregar nueva configuración**:
   ```javascript
   use etl_config;
   db.etl_configurations.insertOne({
     "jobName": "custom_job",
     "mode": "streaming",
     "elasticsearchIndex": "kibana_sample_data_logs",
     "elasticsearchQuery": { "match": { "response": "200" } },
     "timeWindow": "5m",
     "frequencyMinutes": 5,
     "targetCollection": "success_responses",
     "enabled": true,
     "description": "Monitoreo de respuestas exitosas",
     "createdAt": new Date(),
     "updatedAt": new Date()
   });
   ```

3. **Reiniciar el servicio para cargar nueva configuración**:
   ```bash
   docker-compose restart extractor
   ```

## 🐛 Troubleshooting

### Problemas Comunes

1. **Error de conexión a MongoDB**:
   ```bash
   # Verificar que MongoDB esté ejecutándose
   docker-compose ps mongodb
   
   # Verificar logs de MongoDB
   docker-compose logs mongodb
   ```

2. **Error de conexión a Elasticsearch**:
   ```bash
   # Verificar que Elasticsearch esté ejecutándose
   docker-compose ps elasticsearch-dataset
   
   # Verificar salud de Elasticsearch
   curl http://localhost:9200/_cluster/health
   ```

3. **Aplicación no inicia**:
   ```bash
   # Verificar logs detallados
   docker-compose logs -f extractor
   
   # Verificar variables de entorno
   docker-compose exec extractor env | grep -E "(MONGO|ELASTIC)"
   ```

4. **Sin datos de ejemplo**:
   ```bash
   # Reinstalar datos de ejemplo manualmente
   curl -XPOST "http://localhost:5601/api/sample_data/logs" -H "kbn-xsrf: true"
   ```

## 📈 Escalabilidad

Para entornos de producción, considera:

1. **Separar servicios en diferentes hosts**
2. **Usar MongoDB replica set**
3. **Configurar Elasticsearch cluster**
4. **Implementar load balancer para múltiples instancias del extractor**
5. **Configurar persistent volumes para datos críticos**

## 🔒 Seguridad

En producción, asegúrate de:

1. **Cambiar credenciales por defecto de MongoDB**
2. **Habilitar autenticación en Elasticsearch**
3. **Usar variables de entorno o secrets para credenciales**
4. **Configurar redes Docker privadas**
5. **Implementar TLS/SSL para conexiones**
