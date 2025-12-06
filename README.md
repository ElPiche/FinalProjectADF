# Detector de Anomalías 

Proyecto final tecnólogo en informática Framework de detección de anomalías

[Parking Lot](https://docs.google.com/document/d/1zOSzxRsrPZe7DSr-DHhbfsDFXiPR3SI07RYdtVkiDpQ/edit?tab=t.0#heading=h.yzf6b27f5gn7)

[Diagrama](https://app.diagrams.net/#G1OnaDn2s1fRY0rvP8RLPCqJ3RhfiUmgje#%7B%22pageId%22%3A%2234t6jlsbtPh1E6wETkqf%22%7D)

[Jira](https://braian-granero.atlassian.net/jira/software/projects/KAN/boards/1)

## Características

- **Arquitectura Modular de Algoritmos**: Agregar nuevos algoritmos con un solo decorador
- **Algoritmos Soportados**: Z-Score, IQR
- **Notificaciones por Email**: Alertas de anomalías con límite de tasa
- **Perfiles de Bucket**: Detección consciente del contexto temporal (horario laboral, feriados)
- **Observabilidad Completa**: Detalles del algoritmo preservados en Elasticsearch

Ver [Doc/Modular_Algorithm_Architecture.md](Doc/Modular_Algorithm_Architecture.md) para detalles técnicos.

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

Una vez completado estos pasos solo bastaria con empezar a conversar con Claude. Se recomienda utilizar el modelo de Sonnet en sus versiones 4.1 o 4.5.

En caso de que falle a la hora de conectarse con los MCP's, cerrar Claude Desktop, volverlo a abrir y reintentar.

## Ejemplo Rápido

1. Iniciar la infraestructura:
```bash
docker-compose up -d --build
# Opcional con generacion de Logs (para Testing):
docker-compose --profile generate-logs up -d --build
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

- [Arquitectura Modular de Algoritmos](Doc/Modular_Algorithm_Architecture.md)
- [Reporte E2E Test Diciembre 2025](Doc/E2E_Test_Report_December_2025.md)
- [Guía de Replicación Fire Test](Doc/Fire_Test_Replication_Guide.md)