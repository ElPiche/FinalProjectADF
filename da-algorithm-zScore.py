import json
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Parámetros de simulación
### Tomando un caso en el que el horario laboral es de 9 a 17
CANTIDAD_REGISTROS = 300        # 300 registros va desde las 8 de la mañana hasta las 13
PROBABILIDAD_ANOMALIA = 0.05

MEDIA_HTTP_200_LABORAL = 100
MEDIA_HTTP_200_NO_LABORAL = 15

BINOMIAL_INTENTOS_HTTP_500 = 5
PROBABILIDAD_HTTP_500_LABORAL = 0.01
PROBABILIDAD_HTTP_500_NO_LABORAL = 0.02

VENTANAS_MINUTOS = [60]     # [5, 15, 60] minutos

# Umbral de detección de anomalías
UMBRAL_Z_SCORE = 3          # |z| > 3 se considera anómalo

### Generador de Logs ###
def generar_http_logs():
    inicio_simulacion = datetime(2025, 9, 1, 8, 0, 0)
    lista_logs = []
    timestamp_actual = inicio_simulacion

    for _ in range(CANTIDAD_REGISTROS):
        es_horario_laboral = (9 <= timestamp_actual.hour < 17) and (timestamp_actual.weekday() < 5)

        if es_horario_laboral:
            cantidad_http_200 = np.random.poisson(MEDIA_HTTP_200_LABORAL)
            cantidad_http_500 = np.random.binomial(BINOMIAL_INTENTOS_HTTP_500, PROBABILIDAD_HTTP_500_LABORAL)
        else:
            cantidad_http_200 = np.random.poisson(MEDIA_HTTP_200_NO_LABORAL)
            cantidad_http_500 = np.random.binomial(BINOMIAL_INTENTOS_HTTP_500, PROBABILIDAD_HTTP_500_NO_LABORAL)

        # Esto es para añadir ruido extra (aleatorio mas menos 20%)
        cantidad_http_200 = int(cantidad_http_200 * random.uniform(0.8, 1.2))
        cantidad_http_500 = int(cantidad_http_500 * random.uniform(0.8, 1.5))

        # Posibilidad de un pico anómalo
        if random.random() < PROBABILIDAD_ANOMALIA:
            cantidad_http_200 = 0
            cantidad_http_500 += random.randint(10, 50)

        lista_logs.append({
            "timestamp": timestamp_actual.isoformat(),
            "status_code_200": cantidad_http_200,
            "status_code_500": cantidad_http_500
        })

        timestamp_actual += timedelta(minutes=1)

    with open("http_logs.json", "w") as archivo_json:
        json.dump(lista_logs, archivo_json, indent=2)

    print("✅ Archivo http_logs.json generado con datos aleatorios.")
    return lista_logs

#Veo datos del pasado y los comparo con la varianza/promedio que veo hoy en dia
### Detector de anomalías ###
def detectar_anomalias(lista_logs):
    df = pd.DataFrame(lista_logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    for ventana_minutos in VENTANAS_MINUTOS:
        print(f"\n🔎 Analizando ventana de {ventana_minutos} minutos...")

        df_resample = df.resample(f"{ventana_minutos}min").sum()

        for timestamp_inicio, fila in df_resample.iterrows():
            timestamp_fin = timestamp_inicio + timedelta(minutes=ventana_minutos - 1)

            print(f"\n📌 Observación {timestamp_inicio} → {timestamp_fin}")
            for columna_codigo_http in ["status_code_200", "status_code_500"]:
                media = df_resample[columna_codigo_http].mean()
                desviacion = df_resample[columna_codigo_http].std()
                valor_observado = fila[columna_codigo_http]

                if desviacion == 0:
                    desviacion = 1  # evita división por 0

                z_score = (valor_observado - media) / desviacion

                print(f"  {columna_codigo_http}: {valor_observado} "
                      f"(media={media:.2f}, desv={desviacion:.2f}, z={z_score:.2f})")

                if abs(z_score) > UMBRAL_Z_SCORE:
                    print(f"⚠️ Anomalía en {columna_codigo_http} (z={z_score:.2f})")


logs = generar_http_logs()
detectar_anomalias(logs)
