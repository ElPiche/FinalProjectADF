from pymongo import MongoClient
from patsy import dmatrices
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA
import json


uri = "mongodb://admin:1q2w3E*@localhost:27017/"
client = MongoClient(uri)

try:

    # start example code here

    # end example code here
    client.admin.command("ping")

    print("Connected successfully")

    database = client["logsdb"]
    collection = database["grouped_response_code_v2"]  # other application code

    # Pull data
    docs = list(collection.find({}))
    if not docs:
        print("No data found.")
        exit(0)

    # Convert to DataFrame
    df = pd.DataFrame(docs)

    # make sure the timestamp comes as a datetime
    df["es_timestamp"] = pd.to_datetime(df["es_timestamp"])

    # sort Chronologically
    df = df.sort_values("es_timestamp").reset_index(drop=True)

    # Drop duplicate timestamps (keep the first)
    df = df.drop_duplicates(subset="es_timestamp", keep="first")

    # Drop unnecesary values
    cols_to_drop = ["_id", "@timestamp", "@version"]
    df = df.drop(columns=[col for col in cols_to_drop if col in df.columns])

    # Create a complete minute range
    full_range = pd.date_range(start=df["es_timestamp"].min(
    ), end=df["es_timestamp"].max(), freq="60min")

    #df = df.set_index("es_timestamp").reindex(full_range)

    # Fill missing timestamps with zeros
    df["status_code_200_counter"] = df["status_code_200_counter"].fillna(0)
    df["status_code_5xx_counter"] = df["status_code_5xx_counter"].fillna(0)

    # Replace NaN rows (both counters missing) with zeros
    df.loc[
        df["status_code_200_counter"].isna(
        ) & df["status_code_5xx_counter"].isna(),
        ["status_code_200_counter", "status_code_5xx_counter"]
    ] = [0, 0]

    # Convert to integer after cleaning
    df["status_code_200_counter"] = df["status_code_200_counter"].astype(int)
    df["status_code_5xx_counter"] = df["status_code_5xx_counter"].astype(int)

 #   """
    #print("este es el DF pelado tras operar: ")
    #print(df)

    #print("este es el df ordenado deduplicado")
    #print(full_range)
    #"""

    filled_data = df.to_dict(orient="records")
    
    print()
    with open("Datos filtrados desde Mongo.json", "w", encoding="utf-8") as f:
        json.dump(filled_data, f, indent=2, default=str)

    client.close()

except Exception as e:

    raise Exception("The following error occurred: ", e)
