import json
import os
import yaml
from pathlib import Path
import docker

#pip install pyyaml

#Esta configuración puede venir desde la KB o algún env
PROJECT_ROOT = Path(__file__).parent.parent
KB_DIR = PROJECT_ROOT / "pipeline"
MotorDA_folder_path = PROJECT_ROOT / "MotorDA" / "MotorDAConfig"
folder_path = PROJECT_ROOT / "KB"

ElasticURL = "http://elasticsearch-dataset:9200/"
MongoUrl = "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin"
MongoDatabase = "logsdb"
MongoCollection = "grouped_response_code_v2"

# Docker configuration
CONTAINER_IMAGE = 'adf-stack-logstash'
NETWORK_NAME = 'adf-stack_default'
docker_client = docker.from_env()

# Update ElasticURL for container networking
ElasticURL = "http://elasticsearch-dataset:9200/"

logstashTemplate=r'''
    input {
        elasticsearch {
            id => "{{ id }}"
            hosts => [ "{{ es_host }}" ]
            query_type => "esql"
            query => '{{ query }}'{{ SCHEDULE_LINE }}
            ecs_compatibility => disabled
        }
    }

    filter {
        mutate {
            add_field => { "kb_id" => "{{ id }}" }
        }
    }

    output {
        mongodb {
            uri => "{{ Url }}"
            database => "{{ Database }}"
            collection => "{{ Collection }}"
            isodate => true
        }
        stdout { codec => rubydebug }
    }
    '''.strip()

daconfigTemplate = r'''{
    "Connection_Config": {
        "Url": "{{ Url }}",
        "Database": "{{ Database }}",
        "Collection": "{{ Collection }}"
    },
    "Scheduling": {
        "TrainingPeriod": {
            "from": "{{ TrainingFrom }}",
            "to": "{{ TrainingTo }}"
        },
        "Detection": {
            "frequency": "{{ FrequencySeconds }}",
            "start": "{{ DetectionStart }}"
        }
    },
    "DA_Config": {
        "DA_Alg_Parameters": {{ DA_Alg_Parameters }}
    },
    "Meta": {
        "Id": "{{ Id }}",
        "Description": "{{ Description }}"
    }
}'''.strip()


#Helpers###


#Prepare query for logstash config
def prepare_esql_query(s: str) -> str:
    # Convert ES|QL single quotes to double quotes (ES|QL uses double quotes for strings)
    return s.replace("'", '"')

#Escapar comillas
def escape_for_ls_double_quotes(s: str) -> str:
    return s.replace('"', r'\"')

#Validar existencia de directorios
def ensure_dirs():
    KB_DIR.mkdir(parents=True, exist_ok=True)
    MotorDA_folder_path.mkdir(parents=True, exist_ok=True)
    # Create pipeline configs directory
    pipeline_dir = PROJECT_ROOT / "pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)

#Get collection name based on KB ID
def get_collection_name(kb_id: str) -> str:
    return kb_id

#Parsear frecuencia
def parse_frequency_to_seconds(freq: str) -> int:
    """
    Convierte expresiones tipo '5m', '2h30m', '1d' o 'PT5M' en segundos.
    Si ya viene como número, lo devuelve tal cual.
    Ejemplo:
        '5m'  -> 300
        'PT1H' -> 3600
        '2h15m' -> 8100
        '600' -> 600
    """
    if not freq:
        return 60  # valor por defecto 1 min

    s = str(freq).strip().lower()

    # Si es puramente numérico
    if s.isdigit():
        return int(s)

    # ISO8601 tipo PT5M, PT1H, P1DT10M
    import re
    iso = re.match(r"p(?:(?P<d>\d+)d)?t?(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?", s, re.IGNORECASE)
    if iso:
        d = int(iso.group("d") or 0)
        h = int(iso.group("h") or 0)
        m = int(iso.group("m") or 0)
        sec = int(iso.group("s") or 0)
        return d*86400 + h*3600 + m*60 + sec

    # Compacto (5m, 2h30m, 1d2h etc.)
    pattern = re.findall(r"(\d+)([smhd])", s)
    total = 0
    for val, unit in pattern:
        v = int(val)
        if unit == "s":
            total += v
        elif unit == "m":
            total += v * 60
        elif unit == "h":
            total += v * 3600
        elif unit == "d":
            total += v * 86400
    if total > 0:
        return total

    raise ValueError(f"No pude interpretar la frecuencia: {freq}")

#segundos a CRON
def seconds_to_cron(total_seconds: int) -> str:
    """
    Convierte segundos a una expresión cron compatible con el input 'elasticsearch'
    (resolución de minuto). Redondea hacia arriba si no es múltiplo exacto.
    Casos:
      - <60s  -> "* * * * *" (cada minuto)
      - N min -> "*/N * * * *"
      - N h   -> "0 */N * * *"
      - N d   -> "0 0 */N * *"
      - Mixed -> redondea a minutos: "*/M * * * *"
    """
    if total_seconds <= 0:
        return "* * * * *"  # safe default: cada minuto

    # Menos de un minuto: subí a 1 min
    if total_seconds < 60:
        return "* * * * *"

    # Redondeo a minuto hacia arriba
    from math import ceil
    minutes = ceil(total_seconds / 60)

    # Días exactos
    if minutes % (60 * 24) == 0:
        days = minutes // (60 * 24)
        return "0 0 * * *" if days == 1 else f"0 0 */{days} * *"

    # Horas exactas
    if minutes % 60 == 0:
        hours = minutes // 60
        return "0 * * * *" if hours == 1 else f"0 */{hours} * * *"

    # Minutos genérico
    return "* * * * *" if minutes == 1 else f"*/{minutes} * * * *"

####

# Docker container management functions
def get_existing_containers():
    """Get all KB-related containers"""
    try:
        containers = docker_client.containers.list(all=True, filters={'label': 'type=anomaly-series'})
        return {c.labels.get('kb_id'): c for c in containers if c.labels.get('kb_id')}
    except Exception as e:
        print(f"Error getting containers: {e}")
        return {}

def launch_container(kb_id: str, config_str: str):
    """Launch container with config"""
    try:
        # Create config file path
        config_dir = PROJECT_ROOT / "pipeline"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / f"{kb_id}.conf"

        # Write config to file
        config_file.write_text(config_str, encoding="utf-8")

        container = docker_client.containers.run(
            CONTAINER_IMAGE,
            name=f'logstash-kb-{kb_id}',
            network=NETWORK_NAME,
            environment={
                'ELASTICSEARCH_HOSTS': 'elasticsearch-dataset:9200',
                'MONGO_URL': MongoUrl
            },
            labels={
                'kb_id': kb_id,
                'type': 'anomaly-series'
            },
            volumes={
                str(config_file): {'bind': '/usr/share/logstash/pipeline/config.conf', 'mode': 'ro'}
            },
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        print(f"Launched container for KB {kb_id}: {container.id}")
        return container
    except Exception as e:
        print(f"Error launching container for KB {kb_id}: {e}")
        return None

def stop_container(container):
    """Gracefully stop and remove container"""
    try:
        container.stop(timeout=30)
        container.remove()
        print(f"Stopped and removed container: {container.name}")
    except Exception as e:
        print(f"Error stopping container {container.name}: {e}")

def sync_containers_with_configs():
    """Synchronize containers with KB configs"""
    print("Loading KB configurations...")
    kb_configs = {}
    if folder_path.exists():
        for file in folder_path.iterdir():
            if file.suffix.lower() == ".json":
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    kb_id = data.get("KB_Config", {}).get("Id")
                    if kb_id:
                        kb_configs[kb_id] = data
                except Exception as e:
                    print(f"Error loading KB config {file.name}: {e}")

    print(f"Found {len(kb_configs)} KB configurations")

    print("Getting existing containers...")
    existing_containers = get_existing_containers()
    print(f"Found {len(existing_containers)} existing containers")

    # Launch new containers
    for kb_id, config in kb_configs.items():
        if kb_id not in existing_containers:
            print(f"Launching container for KB {kb_id}")
            ls_config = build_logstash_conf(config)
            if ls_config:
                launch_container(kb_id, ls_config)
        else:
            print(f"Container for KB {kb_id} already exists")

    # Remove obsolete containers
    for kb_id, container in existing_containers.items():
        if kb_id not in kb_configs:
            print(f"Removing obsolete container for KB {kb_id}")
            stop_container(container)

#Armar config de logstash
def build_logstash_conf(data: dict) -> str | None:
    kb = data.get("KB_Config", {})
    q = kb.get("Query_Elastic", {})
    query_str = q.get("query")
    if not query_str:
        print("Warning: 'KB_Config.Query_Elastic.query' not found. Skipping Logstash for this file.")
        return None

    job_id = str(kb.get("Id") or "job_" + os.urandom(3).hex())
    collection = get_collection_name(job_id)

    det = (kb.get("Scheduling", {}) or {}).get("Detection", {}) or {}
    one_shot = bool(det.get("one_shot", False))

    freq_raw = det.get("frequency", "1m")

    try:
        freq_seconds = parse_frequency_to_seconds(freq_raw)
    except Exception as e:
        print(f"Advertencia: Frecuencia inválida '{freq_raw}': {e}. Uso 60s por defecto.")
        freq_seconds = 60

    #Convertir segundos a cron
    schedule_line = ""
    if not one_shot:
        cron = seconds_to_cron(freq_seconds)
        schedule_line = f'\n            schedule => "{cron}"'

    conf = logstashTemplate
    conf = conf.replace('{{ id }}', job_id)
    conf = conf.replace('{{ query }}', prepare_esql_query(query_str))
    conf = conf.replace('{{ Url }}', escape_for_ls_double_quotes(MongoUrl))
    conf = conf.replace('{{ Database }}', escape_for_ls_double_quotes(MongoDatabase))
    conf = conf.replace('{{ Collection }}', escape_for_ls_double_quotes(collection))
    conf = conf.replace('{{ es_host }}', escape_for_ls_double_quotes(ElasticURL))
    conf = conf.replace('{{ SCHEDULE_LINE }}', schedule_line)
    return conf

#Armar config de DA
def build_da_conf_str(data: dict) -> dict | None:

    kb = data.get("KB_Config", {})
    scheduling = kb.get("Scheduling", {})
    training = scheduling.get("TrainingPeriod", {})
    detection = scheduling.get("Detection", {})
    alg_params = kb.get("DA_Alg_Parameters", [])

    missing = []
    if not training or not training.get("from") or not training.get("to"):
        missing.append("Scheduling.TrainingPeriod.{from,to}")
    if not detection or not detection.get("frequency") or not detection.get("start"):
        missing.append("Scheduling.Detection.{frequency,start}")
    if not isinstance(alg_params, list) or len(alg_params) == 0:
        missing.append("DA_Alg_Parameters")

    if missing:
        print(f"Warning: Missing sections for DA: {', '.join(missing)}. Skipping DA for this file.")
        return None

    freq_raw = detection.get("frequency", "1m")
    try:
        freq_seconds = parse_frequency_to_seconds(freq_raw)
    except Exception as e:
        print(f"Warning: Invalid frequency '{freq_raw}': {e}. Using 60s by default.")
        freq_seconds = 60

    collection = get_collection_name(str(kb.get("Id", "")))

    # Use localhost for DA configs since MotorDA runs on host machine
    da_mongo_url = "mongodb://admin:1q2w3E*@localhost:27017/?authSource=admin"

    # Reemplazos config DA
    conf = daconfigTemplate
    conf = conf.replace('{{ Url }}', escape_for_ls_double_quotes(da_mongo_url))
    conf = conf.replace('{{ Database }}', escape_for_ls_double_quotes(MongoDatabase))
    conf = conf.replace('{{ Collection }}', escape_for_ls_double_quotes(collection))
    conf = conf.replace('{{ TrainingFrom }}', training.get("from", ""))
    conf = conf.replace('{{ TrainingTo }}', training.get("to", ""))
    conf = conf.replace('{{ DetectionStart }}', detection.get("start", ""))
    conf = conf.replace('{{ FrequencySeconds }}', str(freq_seconds))
    conf = conf.replace('{{ Id }}', str(kb.get("Id", "")))
    conf = conf.replace('{{ Description }}', escape_for_ls_double_quotes(kb.get("Description", "")))

    # DA_Alg_Parameters es una lista, la serializamos como JSON
    conf = conf.replace('{{ DA_Alg_Parameters }}', json.dumps(alg_params, ensure_ascii=False, indent=4))

    return conf

def main():
    ensure_dirs()

    if not folder_path.exists():
        print(f"Error: La carpeta de KB {folder_path} no existe.")
        return

    # ===== CONTAINER SYNCHRONIZATION =====
    print("Synchronizing containers with KB configurations...")
    sync_containers_with_configs()

    # ===== CONFIG FILE GENERATION =====
    for file in folder_path.iterdir():
        if file.suffix.lower() != ".json":
            continue

        print(f"\nLeyendo archivo: {file.name}")
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ===== MOTOR DA (.da.json) =====
            da_conf_str = build_da_conf_str(data)
            if da_conf_str:
                kb_id = (data.get("KB_Config", {}) or {}).get("Id")
                da_name = (kb_id or file.stem)
                out_da_path = MotorDA_folder_path / f"{da_name}_da.json"
                out_da_path.write_text(da_conf_str, encoding="utf-8")
                print(f"Generado configuración de Motor DA: {out_da_path}")

        except Exception as e:
            print(f"Error al procesar {file.name}: {e}")

    print("Deployer execution completed.")


if __name__ == "__main__":
    main()