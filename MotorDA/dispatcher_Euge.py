COLLECTION="startup_v2"
CONNECTION = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DEFAULT_DATABASE = "logsdb"
OUTPUT_FILE = "anomalies_output.json"

TRAIN_FROM="2025-10-01T00:00:00Z"
TRAIN_TO="2025-10-09T23:59:59Z"
DETECT_FROM="2025-10-10T00:00:00Z"
DETECT_TO="2025-10-31T23:59:59Z"
OBSERVED_FIELD="status_code_5xx_counter"

from standalone_da_algorithm_z_score import (
    fetch_logs_from_mongo,
    train_baseline,
    detectar_anomalias_df,
    save_anomalies_json
)

df_train = fetch_logs_from_mongo(CONNECTION, DEFAULT_DATABASE, COLLECTION, TRAIN_FROM, TRAIN_TO, [OBSERVED_FIELD])
baseline = train_baseline(df_train, OBSERVED_FIELD)

df_detect = fetch_logs_from_mongo(CONNECTION, DEFAULT_DATABASE, COLLECTION, DETECT_FROM, DETECT_TO, [OBSERVED_FIELD])
anomalies = detectar_anomalias_df(df_detect, baseline)
save_anomalies_json(anomalies, baseline, OUTPUT_FILE)
