# Caso Uno
Para el prototipo 0, el primer caso en compasa solamente las tecnologías individuales que constituyen la mayoría de la lógica de negocios, siendo estas:

- ElasticSearch v8.19.3 -> para el guardado de logs sin procesar
- Kibana v8.19.3 -> para el cargado de datos preliminares y visualización de los mismos
- Telegraf v1.35.4 -> para la extracción de datos alojados en Elastic
- InfluxDB v2.7.12 -> para guardar las series procesadas
- Motor DA  -> para operar sobre los datos de Influx, y posibilitar el análisis de datos

Este flujo le decidimos llamar "Operativa Vertical" dada su naturaleza lineal.

Cabe destacar que para esta iteración, ni el asistente, ni la KB, ni la Web App se verán desarrollados o interactuando con los servicios previamente dichos.

Para este caso, se busca levantar los servicios necesarios para la operativa a través de un [Docker Compose](https://github.com/ElPiche/FinalProjectADF/blob/main/docker-compose.yml) configurarlos, y ponerlos a interactuar entre ellos, siguiendo el orden establecido en la tabla de arriba.


### Flujo
En este caso uno, estáremos trayendo datos "artificiales" que nos ofrece Kibana, por el momento no tenemos definido como vamos a cargar datos a Elastic por otros medios.

Una vez traídos los datos a través de Kibana, estos podrán ser consultados de varias maneras, entre ellas existe *ESQL* que es lenguaje de query muy similar a SQL con el cual consultar los datos.

Un ejemplo de ello podría ser:

```POSTGRESQl
FROM .ds-kibana_sample_data_logs-2025.09.15-000001 | STATS count = COUNT(*), first_occurrence = MIN(@timestamp), last_occurrence = MAX(@timestamp) BY response | SORT response
```
En donde hacemos un conteo de códigos HTTP que se encuentran entre el valor mínimo del timestamp y el máximo, y por último los ordenamos basado en el número de la respuesta.

el resultado de esta consulta sería:
``` JSON
{ 
	"documents_found": 14074,
	"values_loaded": 14074,
	"took": 334,
	"is_partial": false,
	"columns":
		[
			{
				"name": "count",
				"type": "long"
			},
			{ 
				"name": "first_occurrence",
				"type": "date" 
			},
			{ 
				"name": "last_occurrence",
				"type": "date"
			},
			{ 
				"name": "response",
				"type": "text"
			}
		], 
	"values":[
		[ 
			12832, 
			"2025-09-07T00:39:02.912Z", 
			"2025-11-06T21:45:26.749Z", 
			"200" 
		], 
		[ 
			801, 
			"2025-09-07T06:22:55.923Z", 
			"2025-11-06T17:36:12.827Z", 
			"404" 
		], 
		[ 
			441, 
			"2025-09-07T03:30:25.131Z", 
			"2025-11-06T14:35:50.962Z", 
			"503" 
		] 
	] 
}
```

Tras esto, con Telegraf vamos a extraer estos datos [haciendo uso de 2 plugins]([https://docs.influxdata.com/telegraf/v1/plugins](https://docs.influxdata.com/telegraf/v1/plugins "https://docs.influxdata.com/telegraf/v1/plugins")) que se encuentran configurados en el archivo [telegraf.conf](https://github.com/ElPiche/FinalProjectADF/blob/main/telegraf.conf) y convertir esos datos a series para que puedan ser guardados en InfluxDB, de ahí el Motor DA podrá operar sobre ellos.

Por el momento, el motor ofrece 3 ventanas de tiempo a elegir: 5, 15 y 60 minutos (configurables) en donde se calcula la distribución normal de códigos HTTP en esos interválos de tiempo.
Con estas distribuciones, se consigue la desviación estándar con la cual luego se aplica Z Score (también configurable) para detectar anomalías.

Eventualmente se creará un sistema de alarmas que utilizara el Z Score de estos intervalos de tiempo.

### Incidencias
A desarrollar (o encontrar).

### Tentativas
- Resolver cómo vamos a cargar logs reales a Elastic
	- ¿Proceso ETL?
	- ¿Pre-filtrado de datos?
- ¿Como va el motor de DA a extraer los datos desde InfluxDB? 
	- ¿Vale la pena guardar las queries de influx en una carpeta aparte para que las consuma el motor DA?
	- ¿o el motor consulta contra Influx directamente?
	- ¿tener los 2 script 
