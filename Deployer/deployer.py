#Script de deployer encargado de obtener datos desde la KB.
#Partirlo en dos configuraciones logstash y DA.

#1. Obtener configuración desde carpetaKB
#2. Leer archivo
#3. Partir archivo en dos configuraciones
#4. Crear configuración de logstash
#5. Crear configuración motor DA

#import argparse
import json
#import logging
import os
#import re
from pathlib import Path
#from typing import Optional, Tuple


KB_DIR = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\pipeline")

folder_path = Path(r"C:\Users\Usuario\Desktop\ProyectoFinalRepo\FinalProjectADF\KB")

Logstash_Pipeline_DIR = Path("./pipeline")

#Esta configuración puede venir desde la KB o algún env
ElasticURL = "http://elasticsearch-dataset:9200/"
MongoUrl = "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin"
MongoDatabase = "logsdb"
MongoCollection = "grouped_response_code_v2"


logstashTemplate=r'''
input {
  elasticsearch {
    id => hourly_cron_job
    hosts => [ "{{ es_host }}" ]
    query_type => "esql"
    query => "{{ query }}"
    schedule => "{{ cron }}"
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

daconfigTempalte=r'''{
    "Connection_Config":{
        "Url": "{{ Url }}",
        "Database":"{{ Database }}",
        "Collection": "{{ Collection }}"
    },
    "DA_Config":{
        "DA_Alg_Parameters": [
            {
                "Algorithm": "ZScore",
                "Parameters": {
                "threshold": 3.0,
                "window_size": 100
                }
            },
            {
                "Algorithm": "ARMA",
                "Parameters": {
                "n_estimators": 200,
                "contamination": 0.05
                }
            },
            {
                "Algorithm": "K-means",
                "Parameters": {
                "n_estimators": 200,
                "contamination": 0.05
                }
            }
        ]
    }
}'''


def escape_for_ls_double_quotes(s: str) -> str:
    return s.replace('"', r'\"')

if not folder_path.exists():
    print(f"La carpeta {folder_path} no existe.")
else:
    # Recorremos los archivos de la carpeta
    for file in folder_path.iterdir():
        # Solo procesamos archivos con extensión .json
        if file.suffix.lower() == ".json":
            print(f"\n📄 Leyendo archivo: {file.name}")
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    query_elastic = data.get("KB_Config", {}).get("Query_Elastic")

                    if not query_elastic:
                        print("⚠️ No se encontró el fragmento 'Query_Elastic' en este archivo. Salteando.")
                        continue
                    
                    query_str = query_elastic.get("query")
                    
                    if not query_str:
                        print("⚠️ No se encontró el campo 'query' dentro de 'Query_Elastic'. Salteando.")
                        continue

                    conf_content = logstashTemplate
                    conf_content = conf_content.replace('{{ query }}',     escape_for_ls_double_quotes(query_str))
                    conf_content = conf_content.replace('{{ Url }}',       escape_for_ls_double_quotes(MongoUrl))
                    conf_content = conf_content.replace('{{ Database }}',  escape_for_ls_double_quotes(MongoDatabase))
                    conf_content = conf_content.replace('{{ Collection }}',escape_for_ls_double_quotes(MongoCollection))
                    conf_content = conf_content.replace('{{ es_host }}',   escape_for_ls_double_quotes(ElasticURL))
                    conf_content = conf_content.replace('{{ cron }}',      escape_for_ls_double_quotes("* * * * *"))

                    # Nombre de salida: mismo nombre que el JSON, pero .conf en ./KB
                    out_path = KB_DIR / f"{file.stem}.conf"
                    out_path.write_text(conf_content, encoding="utf-8")

                    print(f"✅ Generado: {out_path}")

            except Exception as e:
                print(f"⚠️ Error al leer {file.name}: {e}")