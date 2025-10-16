# Ejemplos de Configuraciones ETL

Este archivo contiene ejemplos de configuraciones que deben insertarse en la base de datos MongoDB Config para que el servicio ETL funcione.

## Configuraciones de Ejemplo

### 1. Job Batch - Reporte Mensual de Errores

```javascript
db.etl_configurations.insertOne({
  "jobName": "monthly_error_report",
  "mode": "batch",
  "elasticsearchIndex": "application-logs-*",
  "elasticsearchQuery": {
    "bool": {
      "must": [
        { "match": { "level": "ERROR" } }
      ]
    }
  },
  "timeWindow": "1M",
  "targetCollection": "monthly_error_reports",
  "enabled": true,
  "description": "Reporte mensual de errores agrupados por código de error",
  "createdAt": new Date(),
  "updatedAt": new Date()
});
```

### 2. Job Streaming - Monitoreo de Performance en Tiempo Real

```javascript
db.etl_configurations.insertOne({
  "jobName": "realtime_performance_monitoring",
  "mode": "streaming",
  "elasticsearchIndex": "api-logs-*",
  "elasticsearchQuery": {
    "bool": {
      "must": [
        { "exists": { "field": "response_time" } },
        { "range": { "status": { "gte": 200, "lt": 300 } } }
      ]
    }
  },
  "timeWindow": "30m",
  "frequencyMinutes": 15,
  "targetCollection": "performance_metrics",
  "enabled": true,
  "description": "Monitoreo de métricas de rendimiento cada 15 minutos",
  "createdAt": new Date(),
  "updatedAt": new Date()
});
```

### 3. Job Streaming - Actividad de Usuarios

```javascript
db.etl_configurations.insertOne({
  "jobName": "user_activity_tracking",
  "mode": "streaming",
  "elasticsearchIndex": "user-activity-*",
  "elasticsearchQuery": {
    "bool": {
      "must": [
        { "exists": { "field": "user_id" } },
        { "match": { "event_type": "user_action" } }
      ]
    }
  },
  "timeWindow": "1h",
  "frequencyMinutes": 60,
  "targetCollection": "user_activity_summary",
  "enabled": true,
  "description": "Resumen de actividad de usuarios cada hora",
  "createdAt": new Date(),
  "updatedAt": new Date()
});
```

### 4. Job Batch - Análisis de Salud del Sistema

```javascript
db.etl_configurations.insertOne({
  "jobName": "daily_system_health",
  "mode": "batch",
  "elasticsearchIndex": "system-health-*",
  "elasticsearchQuery": {
    "bool": {
      "should": [
        { "match": { "metric_type": "cpu_usage" } },
        { "match": { "metric_type": "memory_usage" } },
        { "match": { "metric_type": "disk_usage" } }
      ]
    }
  },
  "timeWindow": "1d",
  "targetCollection": "system_health_reports",
  "enabled": true,
  "description": "Análisis diario de métricas de salud del sistema",
  "createdAt": new Date(),
  "updatedAt": new Date()
});
```

### 5. Job Streaming - Alertas de Errores Críticos

```javascript
db.etl_configurations.insertOne({
  "jobName": "critical_error_alerts",
  "mode": "streaming",
  "elasticsearchIndex": "application-logs-*",
  "elasticsearchQuery": {
    "bool": {
      "must": [
        { "match": { "level": "FATAL" } }
      ],
      "should": [
        { "match": { "component": "payment_service" } },
        { "match": { "component": "user_service" } }
      ]
    }
  },
  "timeWindow": "5m",
  "frequencyMinutes": 5,
  "targetCollection": "critical_alerts",
  "enabled": true,
  "description": "Alertas de errores críticos cada 5 minutos",
  "createdAt": new Date(),
  "updatedAt": new Date()
});
```

## Comandos para Configurar Base de Datos

### Conectar a MongoDB y crear configuraciones

```bash
# Conectar a MongoDB
mongo mongodb://localhost:27017/etl_config

# Crear índices para mejor rendimiento
db.etl_configurations.createIndex({ "jobName": 1 }, { unique: true });
db.etl_configurations.createIndex({ "mode": 1, "enabled": 1 });
db.etl_configurations.createIndex({ "enabled": 1 });

# Insertar todas las configuraciones de ejemplo
# (Ejecutar cada uno de los comandos insertOne() de arriba)
```

### Verificar configuraciones creadas

```javascript
// Listar todas las configuraciones
db.etl_configurations.find().pretty();

// Listar solo configuraciones activas
db.etl_configurations.find({ "enabled": true }).pretty();

// Listar por modo
db.etl_configurations.find({ "mode": "batch" }).pretty();
db.etl_configurations.find({ "mode": "streaming" }).pretty();
```

## Notas Importantes

1. **Ventanas de Tiempo**: 
   - `m` = minutos
   - `h` = horas 
   - `d` = días
   - `w` = semanas
   - `M` = meses

2. **Frecuencia de Streaming**: Se especifica en minutos

3. **Consultas Elasticsearch**: Usar sintaxis DSL estándar de Elasticsearch

4. **Índices**: Asegurarse de que los índices especificados existan en Elasticsearch

5. **Colecciones Target**: Se crearán automáticamente en MongoDB si no existen
