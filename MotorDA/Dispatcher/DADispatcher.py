import pymongo
import json
from MongoClass import MongoKBConnection
from typing import Dict, Any, List, Optional, Tuple


#Dispatcher: Tiene como objetivo recibir el documento de configuración desde MongoDB y despachar la ejecución del algoritmo correspondiente.
#Tiene que en base al documento de configuración, identificar qué algoritmo se debe ejecutar y llamar a la función correspondiente,
#pasándole los parámetros necesarios. Y guardar los resultados en ElasticSearch.
#En la versión actual también consultaría el mongoDB que contiene la data de documentación para leer la metadata y saber si esta entrenando o no jeje.

#conexión a MongoDB KB
MongoKBURL = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
KBDBName = "logsdb"
KBCollectionName = "testLogsKB"

#conexión a MongoDB MotorDA pendiente
MongoURL_MotorDA = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DBName_MotorDA = "logsDB"
CollectionName_MotorDA = "testLogsMotorDA"

#conexión a elasticSearch
ES_HOST = "http://localhost:9200"
ES_INDEX = "test_logs"

KEYS = ("zscore", "arma", "kmeans", "iforest")

##### Lector de json
def get_kb_block(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve siempre el bloque kbConfig sin importar si viene en camelCase o PascalCase."""
    return doc.get("kbConfig") or doc.get("KB_Config") or {}

def get_kb_id(doc: Dict[str, Any]) -> Optional[str]:
    kb = get_kb_block(doc)
    return kb.get("id") or kb.get("Id")

def get_selected_algorithms(doc: Dict[str, Any]) -> List[str]:
    """
    Devuelve la lista de algoritmos que el usuario 'eligió' (tienen parámetros cargados).
    """
    kb = get_kb_block(doc)
    params = kb.get("daAlgParameters", {}) or kb.get("DA_Alg_Parameters", {}) or {}
    selected = []
    for k in ALGO_KEYS:
        arr = params.get(k)
        if isinstance(arr, list) and len(arr) > 0:
            selected.append(k)
    return selected

def choose_algorithm(doc: Dict[str, Any], priority: Tuple[str, ...] = ALGO_KEYS) -> Optional[str]:
    """
    Elige UN algoritmo. Si hay varios definidos, aplica prioridad.
    Si no hay ninguno, devuelve None.
    Si el JSON tuviera kbConfig.selectedAlgorithm, lo respeta si está definido.
    """
    kb = get_kb_block(doc)
    explicit = kb.get("selectedAlgorithm")
    if explicit:
        return explicit if explicit in ALGO_KEYS else None

    selected = set(get_selected_algorithms(doc))
    for p in priority:
        if p in selected:
            return p
    return None


### Correr algoritmos (placeholders)
def run_zscore(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("zscore", [])
    for p in params:
        print(f"▶ ZSCORE threshold={p.get('threshold')} observedValue={p.get('observedValue')}")
    # acá va tu implementación real...

def run_arma(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("arma", [])
    for p in params:
        print(f"▶ ARMA p={p.get('p')} d={p.get('d')} q={p.get('q')} observedValue={p.get('observedValue')}")
    # implementación...

def run_kmeans(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("kmeans", [])
    for p in params:
        print(f"▶ KMEANS nClusters={p.get('nClusters')} observedValue={p.get('observedValue')}")
    # implementación...

def run_iforest(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("iforest", [])
    for p in params:
        print(f"▶ IFOREST nEstimators={p.get('nEstimators')} contamination={p.get('contamination')} observedValue={p.get('observedValue')}")
    # implementación...


##Map por si sirve
ALGORITHM_HANDLERS = {
    "zscore": run_zscore,
    "arma": run_arma,
    "kmeans": run_kmeans,
    "iforest": run_iforest,
}

def main():
    dispatcher = MongoKBConnection(MongoKBURL, KBDBName, KBCollectionName) #Esto arma la conexión a MongoDB

    print("Documento por id:")

    doc = dispatcher.get_record_by_id("8fbb07a4-f8f0-46ed-9eae-b8d4789c570c")
    
    #aca iria un switch o map para llamar al algoritmo correspondiente
    


if __name__ == "__main__":
    main()