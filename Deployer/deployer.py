import json
import os
import yaml
from pathlib import Path

#pip install pyyaml

#Esta configuración puede venir desde la KB o algún env
KB_DIR = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\pipeline")
MotorDA_folder_path = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\MotorDA/MotorDAConfig")
folder_path = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\KB")
PIPELINES_FILE = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\pipelines.yml")

ElasticURL = "http://elasticsearch-dataset:9200/"
MongoUrl = "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin"
MongoDatabase = "logsdb"
MongoCollection = "grouped_response_code_v2"

logstashTemplate=r'''
    input {
        elasticsearch {
            id => "{{ id }}"
            hosts => [ "{{ es_host }}" ]
            query_type => "esql"
            query => "{{ query }}"{{ SCHEDULE_LINE }}
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

#Actualizar pipelines.yml
def update_pipelines_yml(conf_path: Path):
    """
    Agrega una entrada al pipelines.yml si no existe.
    """
    pipeline_id = conf_path.stem  # ej: query_001
    entry = {
        "pipeline.id": pipeline_id,
        "path.config": str(conf_path).replace("\\", "/"),  # usa / para compatibilidad
        "pipeline.workers": 1,
        "queue.type": "memory"
    }

    # Cargar YAML actual
    if PIPELINES_FILE.exists():
        with open(PIPELINES_FILE, "r", encoding="utf-8") as f:
            try:
                pipelines = yaml.safe_load(f) or []
            except Exception:
                pipelines = []
    else:
        pipelines = []

    # Verificar si ya existe
    if any(p.get("pipeline.id") == pipeline_id for p in pipelines):
        print(f"ℹ️ Pipeline '{pipeline_id}' ya existe en pipelines.yml, no se duplica.")
    else:
        pipelines.append(entry)
        with open(PIPELINES_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(pipelines, f, sort_keys=False)
        print(f"✅ Agregado pipeline '{pipeline_id}' al pipelines.yml")

#Escapar comillas
def escape_for_ls_double_quotes(s: str) -> str:
    return s.replace('"', r'\"')

#Validar existencia de directorios
def ensure_dirs():
    KB_DIR.mkdir(parents=True, exist_ok=True)
    MotorDA_folder_path.mkdir(parents=True, exist_ok=True)

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

#Armar config de logstash
def build_logstash_conf(data: dict) -> str | None:
    kb = data.get("KB_Config", {})
    q = kb.get("Query_Elastic", {})
    query_str = q.get("query")
    if not query_str:
        print("⚠️ No se encontró 'KB_Config.Query_Elastic.query'. Salteando Logstash para este archivo.")
        return None

    job_id = str(kb.get("Id") or "job_" + os.urandom(3).hex())

    det = (kb.get("Scheduling", {}) or {}).get("Detection", {}) or {}
    one_shot = bool(det.get("one_shot", False))
    
    freq_raw = det.get("frequency", "1m")

    try:
        freq_seconds = parse_frequency_to_seconds(freq_raw)
    except Exception as e:
        print(f"⚠️ Frecuencia inválida '{freq_raw}': {e}. Uso 60s por defecto.")
        freq_seconds = 60
    
    #Convertir segundos a cron
    schedule_line = ""
    if not one_shot:
        cron = seconds_to_cron(freq_seconds)
        schedule_line = f'\n            schedule => "{cron}"'

    conf = logstashTemplate
    conf = conf.replace('{{ id }}', job_id)
    conf = conf.replace('{{ query }}', escape_for_ls_double_quotes(query_str))
    conf = conf.replace('{{ Url }}', escape_for_ls_double_quotes(MongoUrl))
    conf = conf.replace('{{ Database }}', escape_for_ls_double_quotes(MongoDatabase))
    conf = conf.replace('{{ Collection }}', escape_for_ls_double_quotes(MongoCollection))
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
        print(f"⚠️ Faltan secciones para DA: {', '.join(missing)}. Salteando DA para este archivo.")
        return None

    freq_raw = detection.get("frequency", "1m")
    try:
        freq_seconds = parse_frequency_to_seconds(freq_raw)
    except Exception as e:
        print(f"⚠️ Frecuencia inválida '{freq_raw}': {e}. Uso 60s por defecto.")
        freq_seconds = 60

    # Reemplazos config DA
    conf = daconfigTemplate
    conf = conf.replace('{{ Url }}', escape_for_ls_double_quotes(MongoUrl))
    conf = conf.replace('{{ Database }}', escape_for_ls_double_quotes(MongoDatabase))
    conf = conf.replace('{{ Collection }}', escape_for_ls_double_quotes(MongoCollection))
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
        print(f"❌ La carpeta de KB {folder_path} no existe.")
        return

    for file in folder_path.iterdir():
        if file.suffix.lower() != ".json":
            continue

        print(f"\n📄 Leyendo archivo: {file.name}")
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ===== LOGSTASH (.conf) =====
            ls_conf = build_logstash_conf(data)
            if ls_conf:
                kb_id = (data.get("KB_Config", {}) or {}).get("Id")
                ls_name = (kb_id or file.stem)
                out_conf_path = KB_DIR / f"{ls_name}.conf"
                out_conf_path.write_text(ls_conf, encoding="utf-8")
                print(f"✅ Generado configuración de Logstash: {out_conf_path}")

                #Actualizando pipeline.yml
                update_pipelines_yml(out_conf_path)
                print(f"✅ Actualizando pipeline.yml: {out_conf_path}")

            # ===== MOTOR DA (.da.json) =====
            da_conf_str = build_da_conf_str(data)
            if da_conf_str:
                kb_id = (data.get("KB_Config", {}) or {}).get("Id")
                da_name = (kb_id or file.stem)
                out_da_path = MotorDA_folder_path / f"{da_name}_da.json"
                out_da_path.write_text(da_conf_str, encoding="utf-8")
                print(f"✅ Generado configuración de Motor DA: {out_da_path}")

        except Exception as e:
            print(f"⚠️ Error al procesar {file.name}: {e}")


if __name__ == "__main__":
    main()