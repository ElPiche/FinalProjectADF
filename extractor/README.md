# ETL Logs Service

Servicio Spring Boot que extrae datos de logs desde Elasticsearch, los transforma y los carga en MongoDB. Opera en dos modos: Batch (ejecución única) y Streaming (ejecución periódica continua), ambos configurados vía MongoDB.

## 🎯 Propósito

Automatizar la extracción y agregación de logs desde Elasticsearch para generar reportes procesados y métricas almacenadas en MongoDB para análisis y monitoreo.

## 🏗️ Arquitectura

### Componentes Principales

#### Fuentes de Datos
- **MongoDB Config DB**: Almacena configuraciones de jobs ETL
- **Elasticsearch**: Fuente de datos de logs raw

#### Motor ETL (Spring Boot)
- **ConfigReader**: Lee configuraciones de jobs desde Config DB al inicio
- **Scheduler**: Maneja ejecución periódica para modo streaming usando @Scheduled
- **Extractor**: Se conecta a Elasticsearch y ejecuta consultas configuradas
- **Transformer**: Aplica transformaciones de datos (agrupación, filtrado, normalización)
- **Loader**: Inserta/actualiza datos procesados en MongoDB Target

#### Almacenamiento Destino
- **MongoDB Target DB**: Base de datos destino para logs procesados y agregaciones

## 🚀 Modos de Ejecución

### Modo Batch
- Ejecuta una vez cuando la aplicación inicia
- Lee su configuración específica desde Config DB
- Extrae datos para una ventana de tiempo definida (ej: "último mes")
- **Ejemplo de uso**: Generar reporte mensual de errores agrupados por código

### Modo Streaming
- Ejecuta continuamente basado en frecuencia configurada
- Lee su configuración específica desde Config DB
- Ejecuta periódicamente (ej: cada 30 minutos)
- Extrae datos para ventanas de tiempo recientes (ej: "última hora")
- **Ejemplo de uso**: Monitoreo en tiempo real de tiempos de respuesta de API

## 📋 Requisitos

- Java 17+
- Spring Boot 3.x
- MongoDB (Config y Target)
- Elasticsearch

## ⚙️ Configuración

### application.properties

```properties
# MongoDB Config Database
spring.data.mongodb.uri=mongodb://localhost:27017/etl_config
spring.data.mongodb.database=etl_config

# MongoDB Target Database
app.mongodb.target.uri=mongodb://localhost:27017/etl_target
app.mongodb.target.database=etl_target

# Elasticsearch
app.elasticsearch.host=localhost
app.elasticsearch.port=9200
app.elasticsearch.protocol=http
```

### Estructura de Configuración (MongoDB)

Cada documento de configuración en Config DB define los parámetros del job ETL:

```json
{
  "jobName": "monthly_error_report",
  "mode": "batch",
  "elasticsearchIndex": "application-logs-*",
  "elasticsearchQuery": {
    "match": {
      "level": "ERROR"
    }
  },
  "timeWindow": "1M",
  "targetCollection": "error_reports",
  "enabled": true,
  "description": "Reporte mensual de errores agrupados por código"
}
```

## 🔄 Flujo de Trabajo

### Inicio de Aplicación
1. ConfigReader carga todas las configuraciones desde Config DB
2. Jobs batch se ejecutan inmediatamente (una sola vez)
3. Jobs streaming se registran con Scheduler

### Ejecución Batch
1. Extraer → Transformar → Cargar (una vez)
2. Registrar metadatos de ejecución

### Ejecución Streaming
1. Scheduler activa extracción cada N minutos
2. Extraer → Transformar → Cargar (continuo)
3. Registrar cada ejecución de metadatos

## 📊 Monitoreo

- Todas las ejecuciones se registran en consola/archivo
- Metadatos almacenados en Target DB para auditoría
- Endpoints de Actuator disponibles para salud del servicio

## 🎯 Casos de Uso

- ✅ Agregar logs de error por hora/día/mes
- ✅ Monitorear métricas de rendimiento de API en tiempo real
- ✅ Generar reportes de cumplimiento desde logs de auditoría
- ✅ Rastrear patrones de actividad de usuarios
- ✅ Analizar métricas de salud del sistema

## 🚀 Deployment

1. **Aplicación única Spring Boot**
2. **Lee configuraciones automáticamente al inicio**
3. **No requiere API REST para operación básica**
4. **Completamente autónomo después de configuración inicial en MongoDB**

## 📁 Estructura del Proyecto

```
src/main/java/com/da/extractor/
├── ExtractorApplication.java          # Aplicación principal
├── config/
│   ├── ElasticsearchConfig.java      # Configuración Elasticsearch
│   ├── MongoConfig.java              # Configuración MongoDB
│   └── SchedulingConfig.java         # Configuración Scheduling
├── model/
│   ├── EtlConfiguration.java         # Modelo configuración ETL
│   └── EtlExecutionLog.java          # Modelo log de ejecución
├── repository/
│   ├── EtlConfigurationRepository.java # Repositorio configuraciones
│   └── EtlExecutionLogRepository.java  # Repositorio logs ejecución
└── service/
    ├── ConfigReader.java             # Lector configuraciones
    ├── BatchProcessor.java           # Procesador modo batch
    ├── StreamingScheduler.java       # Scheduler modo streaming
    ├── ElasticsearchExtractor.java   # Extractor Elasticsearch
    ├── DataTransformer.java          # Transformador datos
    └── DataLoader.java               # Cargador datos MongoDB
```

## 🛠️ Desarrollo

Para agregar nuevos tipos de transformación, modificar `DataTransformer.java` y agregar el case correspondiente en el método `transformData()`.

Para nuevos patrones de extracción, extender `ElasticsearchExtractor.java` con métodos específicos para el tipo de consulta requerida.
