# Detector de Anomalías 

El siguiente es un framework orientado a la detección de anomalías en servidores de aplicaciones potenciado por IA como asistente. El objetivo de este proyecto es aprovechar el poder de un LLM para agilizar el analisis de logs y la configuracion de un pipeline de detección de anomalias automatizado.

## Características

- **Arquitectura Modular de Algoritmos**: Agregar nuevos algoritmos con un solo decorador
- **Algoritmos Soportados**: Z-Score, IQR
- **Notificaciones por Email**: Alertas de anomalías con límite de tasa
- **Perfiles de Bucket**: Detección consciente del contexto temporal (horario laboral, feriados)
- **Observabilidad Completa**: Detalles del algoritmo preservados en Elasticsearch

Ver [documents/dispatcher/specifications/Modular_Algorithm_Architecture.md](documents/dispatcher/specifications/Modular_Algorithm_Architecture.md) para detalles técnicos.

## Setup 

### Configuración servicio de correos
Dentro de la siguiente ubicación: `anomalies-insights-module\src\main\resources` crear un archivo de nombre application-secrtets.properties, el mismo 
funciona como archivo de configuracion que contiene la clave del correo que utiliza el sistema, con este archivo se evita exponerla de manera pública.

Dentro del archivo colocar el siguiente contenido: spring.mail.password=<MAIL_PASSWORD> colocar dentro de <> la contraseña del correo proporcionada.

### Infraestructura principal
Utilizando Docker: En la raiz del proyecto ejecutar: `docker-compose up -d --build`

### Configuración de MCP's para Claude Desktop
El framework funciona mediante conversaciones con un modelo LLM que tenga capacidades 
de utilizar MCP's.
Recomendamos utilizar Claude Desktop para este proposito que puede ser descargado desde su 
[pagina oficial](https://www.claude.com/download).
Una vez instalado Claude Desktop y levantada la infraestructura principal deberemos dirigimos al archivo `claude_desktop_config.json` al cual accedemos desde Claude Dekstop yendo a Ajustes > Desarrollador > Editar configuración.

En Windows tipicamente este archivo se encuentra en `C:\Users\<USUARIO>\AppData\Roaming\Claude`.

Una vez alli agregamos la siguiente configuración:
```json
{
  "mcpServers": {
    "elasticsearch-logs-exploration": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "ES_URL",
        "mcp/elasticsearch",
        "stdio"
      ],
      "env": {
        "ES_URL": "http://host.docker.internal:9200"
      }
    },
    "kb-mcp": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "kb-mcp",
        "python",
        "kb-mcp.py",
        "--server"
      ],
      "env": {},
      "alwaysAllow": [
        "create_da_config",
        "elasticsearch_sql",
        "list_available_algorithms",
        "modify_kb_config",
        "list_kb_configurations",
        "describe_mcp_server"
      ]
    },
    "elasticsearch-anomalies-results": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm", "-e", "ES_URL",
        "mcp/elasticsearch", "stdio"
      ],
      "env": {
        "ES_URL": "http://host.docker.internal:9201"
      }
    }
  }
}
```
En caso que se cuente ya con un servidor propio de Elasticsearch con logs se puede reemplazar el contenido de `elasticsearch-logs-exploration` por algo como:
```json
"elasticsearch-logs-exploration": {
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "-e",
    "ES_URL",
    "-e",
    "ES_API_KEY",
    "-e",
    "ES_VERIFY_SSL",
    "mcp/elasticsearch",
    "stdio"
  ],
  "env": {
    "ES_URL": "{URL_ELASTIC}",
    "ES_API_KEY": "BASE64(ID:API_KEY)", // Authorization: ApiKey <BASE64(ID:API_KEY)>
    "ES_VERIFY_SSL": "true"
  }
},
```
si tienes configurada una Api Key en tu servidor.
Para una conexión via usuario y contraseña:
```json
{
  "mcpServers": {
    "elasticsearch-logs-exploration": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "ES_URL",
        "-e",
        "ES_USERNAME",
        "-e",
        "ES_PASSWORD",
        "mcp/elasticsearch",
        "stdio"
      ],
      "env": {
        "ES_URL": "{URL_ELASTIC}",
        "ES_USERNAME": "{USERNAME}",
        "ES_PASSWORD": "{PASSWORD}"
      }
    }
  }
}
```


Una vez completado estos pasos solo bastaria con empezar a conversar con Claude. Se recomienda utilizar el modelo de Sonnet en sus versiones 4.1 o 4.5.

En caso de que falle a la hora de conectarse con los MCP's, cerrar Claude Desktop, volverlo a abrir y reintentar.

## Ejemplo Rápido

1. Iniciar la infraestructura:
```bash
docker-compose up -d --build
# Opcional con generacion de Logs (para Testing):
docker-compose --profile generate-logs up -d --build
```

Nota: `docker-compose up -d` no activa por defecto la generación de logs. Para ejecutar tests de estrés o pruebas que generan tráfico sintético, utilice `--profile generate-logs` o `--profile stress`. Use estos perfiles sólo cuando desee generar carga intencionalmente.
```

2. En Claude Desktop, usar las herramientas de KB-MCP:
```
Listar algoritmos disponibles:
→ list_available_algorithms

Crear una configuración de detección de anomalías:
→ create_da_config con:
  - name: "mi-config"
  - algorithm: {"name": "iqr", "parameters": [{"dimension": "error_count"}]}
  - anomaly_config: {"user_emails": ["tu@email.com"]}
```

3. Monitorear anomalías:
```bash
# Ver logs del dispatcher
docker logs da-dispatcher --tail 50

# Consultar anomalías
curl "http://localhost:9201/*_anomalies/_search?pretty"
```

## Documentación

- [Arquitectura Modular de Algoritmos](documents/dispatcher/specifications/Modular_Algorithm_Architecture.md)
- [Reporte E2E Test Diciembre 2025](documents/general/reports/E2E_Test_Report_December_2025.md)
- [Guía de Replicación Fire Test](documents/general/guides/Fire_Test_Replication_Guide.md)