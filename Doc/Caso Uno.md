# Caso Uno
Para el prototipo 0, el primer caso abarca solamente las tecnologías individuales que constituyen la mayoría de la lógica de negocios, siendo estas:

- ElasticSearch v8.19.3 -> Para el guardado de logs sin procesar
- Kibana v8.19.3 -> Para el cargado de datos preliminares y visualización de los mismos
- MongoDB v8.0 -> Para el guardado de series y resultados de detecciones
- Motor DA  -> Para operar sobre los datos de MongoDB, y posibilitar el análisis de datos
- LogStash 8.19.4 -> Para la extracción de datos desde Elastic

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

El resultado de esta consulta sería:
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

Tras esto, utilizaremos LogStash para extraer y limpiar estos datos que conseguimos con la consulta ESQL haciendo uso de la [configuración de LogStash](https://github.com/ElPiche/FinalProjectADF/blob/main/pipeline/logstash.conf), dentro de la misma de forma tentativa tenemos la siguiente consulta:

```POSTGRESQL
"query": "FROM .ds-kibana_sample_data_logs-* | STATS count = COUNT(*), first_occurrence = MIN(@timestamp), last_occurrence = MAX(@timestamp) BY response | SORT response"
```
Que por el momento es un conteo de los códigos HTTP y los intervalos en que aparecen que se actualiza cada 60 segundos
```
request_timeout => 60
    schedule => { every => "60s" }
    codec => "json"
 ```
pero se busca conseguir que nos devuelva las series ya armadas para guardarlas.

La configuración actual también cuenta con un filtro, débido a que el [plugin que utilizamos](https://www.elastic.co/docs/reference/logstash/plugins/plugins-inputs-elasticsearch#:~:text=The%20ES,being%20preceded%20by%20deprecation%20warnings) para consultar a Elastic a través de ESQL nos devuelve los headers del GET, para ello hacemos uso de la siguiente línea de configuración:
```JSON
# Eliminar todo lo que no sea los campos finales deseados
  mutate {
    remove_field => [
      "values",
      "columns",
      "http_poller_metadata",
      "host",
      "@version",
      "event",
      "agent"
    ]
```
Este archivo de configuración además, cuenta con hot reload, permitiendo así una fácil integración con el eventual MCP, en donde el asistente ayudará a generar queries y filtros que se inyectarán en tiempo real para extraer series específicas a Mongo.

Dentro del mismo, podemos describir a donde queremos que los datos extraidos vayan, actualmente tenemos la siguiente línea para conectarlo a nuestra instancia de MongoDB:
```JSON
output {

  mongodb {
    uri => "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin"
    database => "logsdb"
    collection => "grouped_response_code"
    isodate => true
    id => "%{response}"
  }
```

Por el momento, el motor ofrece 3 ventanas de tiempo a elegir: 5, 15 y 60 minutos (configurables) en donde se calcula la distribución normal de códigos HTTP en esos interválos de tiempo.
Con estas distribuciones, se consigue la desviación estándar con la cual luego se aplica Z Score (también configurable) para detectar anomalías.

Eventualmente se creará un sistema de alarmas que utilizara el Z Score de estos intervalos de tiempo.

También se espera ser capaz de ofrecer un mínimo de 3 diferentes algorítmos de detección de anomalías incluyendo el Z score.

### Incidencias
A desarrollar (o encontrar).

### Tentativas
- Resolver cómo vamos a cargar logs reales a Elastic
	- ¿Proceso ETL? -> Por el momento tenemos un pequeño script que aplica un ReGeX a logs "sucios" para poder extraer los conteos de http code en formato de series. truncando los intervalos de tiempo para poder ofrecer series regulares con el siguiente formato:
		```JSON
		{
	    "timestamp": "2025-08-27T13:28:00.000",
	    "status_code_200": 4,
	    "status_code_500": 0
	  },
	  {
	    "timestamp": "2025-08-27T13:29:00.000",
	    "status_code_200": 4,
	    "status_code_500": 0
	  },
	  {
	    "timestamp": "2025-08-27T13:30:00.000",
	    "status_code_200": 1,
	    "status_code_500": 0
	  },
		```
	
	- ¿Pre-filtrado de datos?
- ¿Como va el motor de DA a extraer los datos desde InfluxDB? 
	- ¿Vale la pena guardar las queries de influx en una carpeta aparte para que las consuma el motor DA?
	- ¿O el motor consulta contra Influx directamente?

 - Reemplazo de Influx
 	- ¿Sería mejor una 2nda instancia de Elastic?
	- ¿O una de MongoDB?
