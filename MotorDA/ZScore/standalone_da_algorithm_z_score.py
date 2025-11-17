import numpy as np
import pandas as pd

# === UTILS ===================================================================
def add_workday_flag(df: pd.DataFrame) -> pd.DataFrame:
    # Add a boolean column 'is_workday' based on the weekday of each timestamp.
    # Monday–Friday = True, Saturday–Sunday = False.

    df["is_workday"] = df["timestamp"].dt.dayofweek < 5
    return df

# TODO: this might get resource intensive if time_window is small and df_train is too big.

# === TRAIN BASELINE ==========================================================
def train_baseline(kb_id: str, dimension: str, df_train: pd.DataFrame, field: str, time_window: int = 3600, percentile: float = 99.5, workday_separation: bool = True):
    """Compute mean, std, and dynamic threshold from training data."""

    df_train = add_workday_flag(df_train)

    # Ensure timestamp is datetime
    df_train["timestamp"] = pd.to_datetime(df_train["timestamp"])

    # Use full hour-minute-second conversion to seconds, not just seconds
    df_train["train_window"] = (
                                       (df_train["timestamp"].dt.hour * 3600)
                                       + (df_train["timestamp"].dt.minute * 60)
                                       + df_train["timestamp"].dt.second
                               ) // time_window

    if(workday_separation):

        # Initialize buckets for both workday types
        buckets = {"workday": {}, "non_workday": {}}

        # Global fallback
        global_mean = np.mean(df_train[field])
        global_std = np.std(df_train[field]) if np.std(df_train[field]) > 0 else 1e-6

        # Group by is_workday (True/False)
        grouped_by_workday = df_train.groupby("is_workday")

        for is_workday, data in grouped_by_workday:
            grouped_by_time_window = data.groupby("train_window")

            for window_time_window, data_time_window in grouped_by_time_window:
                vals_time_window = data_time_window[field].astype(float).values

                # Calculate mean/std logic
                if len(vals_time_window) < 3:
                    print("\033[93m ------------------------------------------------------------------------- \033[0m")
                    print("\033[93m TRAINING Z SCORE WORKDAYFUL WITH GLOBAL DISTRIBUTION DUE TO LACK OF DATA \033[0m")
                    print("\033[93m ------------------------------------------------------------------------- \033[0m")
                    mean = global_mean
                    std = global_std
                else:
                    print("\033[92m ------------------------------------------------------------------------- \033[0m")
                    print(f"\033[92m TRAINING Z SCORE WORKDAYFUL WITH BUCKETS \033[0m")
                    print("\033[92m ------------------------------------------------------------------------- \033[0m")
                    mean = np.mean(vals_time_window)
                    std = np.std(vals_time_window) if np.std(vals_time_window) > 0 else 1e-6

                z_scores = np.abs((vals_time_window - mean) / std)
                threshold = np.percentile(z_scores, percentile)

                label = "workday" if is_workday else "non_workday"
                window_key = str(int(window_time_window))  # force string key for MongoDB

                buckets[label][window_key] = {
                    "mean": mean,
                    "std": std,
                    "threshold": threshold,
                    #"timestamp_mean": data_time_window["timestamp"].isoformat(),
                    "is_workday": bool(is_workday),
                    "data_points": len(vals_time_window),
                    "sufficient_data": len(vals_time_window) >= 3
                }

        # Convert all keys to strings (for MongoDB safety)
        def stringify_keys(d):
            if isinstance(d, dict):
                return {str(k): stringify_keys(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [stringify_keys(i) for i in d]
            return d

        baselines_str_keys = stringify_keys(buckets)

        return {
            "kb_id": kb_id,
            "dimension": dimension,
            "time_window": time_window,
            "work_day_enabled?": True,
            "buckets": baselines_str_keys,
        }
    else:
        return train_baseline_workdayless(kb_id,dimension,df_train,field,time_window,percentile)

# === ANOMALY DETECTION ======================================================
def anomaly_detection_workdayful(df: pd.DataFrame, baseline: dict, ventana_minutos: int, bucket_number: int):
    """Detect anomalies using statistical baseline."""
    if df.empty:
        return []

    # TODO: check if the logic behind change stream of mongo is gonna change, because right now each call brings a singular value,
    #  it's not designed to receive a dataframe with more than just one value
    if df["is_workday"].iloc[0]:  # THIS WILL ONLY WORK IF THE df I AM RECEIVING HAS ONLY ONE VALUE, RIGHT NOW THAT?S THE CASE BUT IT MIGHT CHANGE

        field = "value"  # this is harcoded as all the dataframe's have "value" as the name of the observed_value
        mean = baseline["buckets"]["workday"][str(bucket_number)]["mean"]
        std = baseline["buckets"]["workday"][str(bucket_number)]["std"]
        threshold = baseline["buckets"]["workday"][str(bucket_number)]["threshold"]

    else:

        field = "value"  # this is harcoded as all the dataframe's have "value" as the name of the observed_value
        mean = baseline["buckets"]["non_workday"][str(bucket_number)]["mean"]
        std = baseline["buckets"]["non_workday"][str(bucket_number)]["std"]
        threshold = baseline["buckets"]["non_workday"][str(bucket_number)]["threshold"]


    # all this sorting thingamabober is just so we can eliminate duplicates and put the timestamp in order
    # print("I am inside standalone z score, and I am printing df: ")
    # print(df)

    df = df.sort_values("timestamp").set_index("timestamp")
    df_resample = df.resample(f"{ventana_minutos}min").sum()

    #  print("I am inside standalone z score, and I am printing RESAMPLED df: ")
    #  print(df_resample)

    anomalies = []
    for ts, fila in df_resample.iterrows():
        val = fila.get(field, 0)

        # acá ocurre la magia, comparamos el valor del df, con el promedio y dividimos por el estándar de los datos pre-entrenados
        z_score = (val - mean) / std
        is_anomaly = abs(z_score) > threshold
        anomalies.append({
            "timestamp": ts.isoformat(),
            "value": float(val),
            "z_score": float(z_score),
            "is_anomaly": bool(is_anomaly),
        })
    return anomalies

def anomaly_detection_workdayless(df: pd.DataFrame, baseline: dict, ventana_minutos: int, bucket_number: int):
    """Detect anomalies using statistical baseline."""
    if df.empty:
        return []

    print("I am about to print baseline:")
    print(baseline)

    field = "value"  # this is harcoded as all the dataframe's have "value" as the name of the observed_value
    mean = baseline["buckets"][str(bucket_number)]["mean"]
    std = baseline["buckets"][str(bucket_number)]["std"]
    threshold = baseline["buckets"][str(bucket_number)]["threshold"]

    # all this sorting thingamabober is just so we can eliminate duplicates and put the timestamp in order
    # print("I am inside standalone z score, and I am printing df: ")
    # print(df)

    df = df.sort_values("timestamp").set_index("timestamp")
    df_resample = df.resample(f"{ventana_minutos}min").sum()

    #  print("I am inside standalone z score, and I am printing RESAMPLED df: ")
    #  print(df_resample)

    anomalies = []
    for ts, fila in df_resample.iterrows():
        val = fila.get(field, 0)

        # acá ocurre la magia, comparamos el valor del df, con el promedio y dividimos por el estándar de los datos pre-entrenados
        z_score = (val - mean) / std
        is_anomaly = abs(z_score) > threshold
        anomalies.append({
            "timestamp": ts.isoformat(),
            "value": float(val),
            "z_score": float(z_score),
            "is_anomaly": bool(is_anomaly),
        })
    return anomalies


def train_baseline_workdayless(
    kb_id: str,
    dimension: str,
    df_train: pd.DataFrame,
    field: str,
    time_window: int,
    percentile: float = 99.5,
    min_points: int = 10
    ):
    """
    Train statistical baselines per (is_workday, time_bucket) pair.
    """
    # Ensure timestamp is datetime
    #df_train["timestamp"] = pd.to_datetime(df_train["timestamp"])

    # Use full hour-minute-second conversion to seconds, not just seconds
    df_train["train_window"] = (
                                       (df_train["timestamp"].dt.hour * 3600)
                                       + (df_train["timestamp"].dt.minute * 60)
                                       + df_train["timestamp"].dt.second
                               ) // time_window


    # Initialize buckets for both workday types
    buckets = {}

    # Global fallback
    global_mean = np.mean(df_train[field])
    global_std = np.std(df_train[field]) if np.std(df_train[field]) > 0 else 1e-6

    grouped_by_time_window = df_train.groupby("train_window")

    for train_window_bucket, data in grouped_by_time_window:

        vals_time_window = data[field].astype(float).values

        # Calculate mean/std logic
        if len(vals_time_window) < 3:
            print("\033[93m ------------------------------------------------------------------------- \033[0m")
            print("\033[93m TRAINING Z SCORE WORKDAYLESS WITH GLOBAL DISTRIBUTION DUE TO LACK OF DATA \033[0m")
            print("\033[93m ------------------------------------------------------------------------- \033[0m")

            mean = global_mean
            std = global_std
        else:
            print("\033[92m ------------------------------------------------------------------------- \033[0m")
            print(f"\033[92m TRAINING Z SCORE WORKDAYLESS WITH BUCKETS \033[0m")
            print("\033[92m ------------------------------------------------------------------------- \033[0m")
            mean = np.mean(vals_time_window)
            std = np.std(vals_time_window) if np.std(vals_time_window) > 0 else 1e-6

        z_scores = np.abs((vals_time_window - mean) / std)
        threshold = np.percentile(z_scores, percentile)

        window_key = str(int(train_window_bucket))  # force string key for MongoDB

        buckets[window_key] = {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "is_workday": False,
            "data_points": len(vals_time_window),
            "sufficient_data": len(vals_time_window) >= 3
        }

    # Convert all keys to strings (for MongoDB safety)
    def stringify_keys(d):
        if isinstance(d, dict):
            return {str(k): stringify_keys(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [stringify_keys(i) for i in d]
        return d

    baselines_str_keys = stringify_keys(buckets)

    return {
        "kb_id": kb_id,
        "dimension": dimension,
        "time_window": time_window,
        "work_day_enabled?": False,
        "buckets": baselines_str_keys,
    }



def get_closest_bucket(df: pd.DataFrame, baseline: dict, time_window: int) -> int:
    """
    Given a DataFrame with a single timestamp and a baseline with buckets,
    return the bucket number whose start time is closest to that timestamp.
    """
    if df.empty:
        raise ValueError("DataFrame is empty — cannot determine bucket.")
    if "timestamp" not in df.columns:
        raise KeyError("DataFrame must have a 'timestamp' column.")

    # Extract the single timestamp from df
    ts = df["timestamp"].iloc[0]
    if not isinstance(ts, pd.Timestamp):
        ts = pd.to_datetime(ts)

    # Convert timestamp to seconds since start of day
    seconds_since_midnight = ts.hour * 3600 + ts.minute * 60 + ts.second

    if baseline["work_day_enabled?"]:

        # TODO: check if the logic behind change stream of mongo is gonna change, because right now each call brings a singular value,
        #  it's not designed to receive a dataframe with more than just one value

        if df["is_workday"].iloc[0]: # THIS WILL ONLY WORK IF THE df I AM RECEIVING HAS ONLY ONE VALUE, RIGHT NOW THAT?S THE CASE BUT IT MIGHT CHANGE
            # Extract bucket keys (in seconds) from baseline
            try:
                bucket_seconds = [int(k) * time_window for k in baseline["buckets"]["workday"].keys()]
            except Exception:
                # If your keys are already in seconds, not bucket numbers, remove "* time_window"
                bucket_seconds = [int(k) for k in baseline["buckets"]["workday"].keys()]

        else:
            # Extract bucket keys (in seconds) from baseline
            try:
                bucket_seconds = [int(k) * time_window for k in baseline["buckets"]["non_workday"].keys()]
            except Exception:
                # If your keys are already in seconds, not bucket numbers, remove "* time_window"
                bucket_seconds = [int(k) for k in baseline["buckets"]["non_workday"].keys()]

    else:
        # Extract bucket keys (in seconds) from baseline
        try:
            bucket_seconds = [int(k) * time_window for k in baseline["buckets"].keys()]
        except Exception:
            # If your keys are already in seconds, not bucket numbers, remove "* time_window"
            bucket_seconds = [int(k) for k in baseline["buckets"].keys()]

    # Find which bucket start is closest to the timestamp
    closest_bucket_seconds = min(bucket_seconds, key=lambda b: abs(b - seconds_since_midnight))

    # Compute the corresponding bucket number
    bucket_number = closest_bucket_seconds // time_window

    print(
        f"[get_closest_bucket] timestamp={ts}, seconds={seconds_since_midnight}, "
        f"closest_bucket_start={closest_bucket_seconds}, bucket_number={bucket_number}"
    )

    return bucket_number