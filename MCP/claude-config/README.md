# Claude Desktop Configuration

Esta carpeta contiene la configuración local de Claude Desktop para el proyecto FinalProjectADF.

## Uso

Para usar esta configuración local en lugar de la configuración global:

1. Copia el archivo `claude_desktop_config.json` a `%APPDATA%\Claude\claude_desktop_config.json`
2. O configura Claude Desktop para usar este archivo directamente

## Servidores MCP configurados

- **elasticsearch**: Conecta con Elasticsearch corriendo en Docker
- **structured-output**: Servidor MCP personalizado que incluye herramientas para:
  - Formateo de salida estructurada (JSON, XML, YAML)
  - Creación de configuraciones DA (Data Analytics)

## Volúmenes

El servidor `structured-output` monta la carpeta `./KB-MCP` del proyecto como `/app/config` dentro del contenedor, permitiendo que los archivos generados se guarden persistentemente en el proyecto.

## Archivos generados

Los archivos de configuración DA se guardan en `../KB-MCP/da-config.json`