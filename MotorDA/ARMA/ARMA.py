import json
from pymongo import MongoClient
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA

uri = "mongodb://admin:1q2w3E*@localhost:27017/"
client = MongoClient(uri)
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

# print(f"this is df before dropping duplicates: {df}")
# Drop duplicate timestamps (keep the first)
df = df.drop_duplicates(subset="es_timestamp", keep="first")
# print(f"this is df AFTER dropping duplicates: {df}")

# Drop unnecesary values
cols_to_drop = ["_id", "@timestamp", "@version"]
df = df.drop(columns=[col for col in cols_to_drop if col in df.columns])
print(f"this is df after dropping unnecesary columns: {df}")

# Create a complete hour range
full_range = pd.date_range(start=df["es_timestamp"].min(
), end=df["es_timestamp"].max(), freq="60min")

# print(f"this is the length of DF: {len(df)}")
# print(f"this is the length of full_range: {len(full_range)}")

# Find missing timestamps and fill with zeros
missing_range = [
    timestamp for timestamp in full_range if timestamp not in df["es_timestamp"].values]
missing_df = pd.DataFrame({"es_timestamp": missing_range,
                          "status_code_200_counter": np.zeros(len(missing_range)),
                           "status_code_5xx_counter": np.zeros(len(missing_range))})

print(f"Found {len(missing_range)} missing time intervals")

# Handle missing values properly
if 'status_code_200_counter' not in df.columns:
    df['status_code_200_counter'] = 0
if 'status_code_5xx_counter' not in df.columns:
    df['status_code_5xx_counter'] = 0

# Fill NaN values with 0 for counters
df['status_code_200_counter'] = df['status_code_200_counter'].fillna(0)
df['status_code_5xx_counter'] = df['status_code_5xx_counter'].fillna(0)

# Convert to numeric types
df['status_code_200_counter'] = pd.to_numeric(
    df['status_code_200_counter'], errors='coerce').fillna(0)
df['status_code_5xx_counter'] = pd.to_numeric(
    df['status_code_5xx_counter'], errors='coerce').fillna(0)

# print(f"this is the missing range BEFORE concatenating: {missing_range}")

df = pd.concat([df, missing_df])

# magic operation
# df["es_timestamp"] = [timestamp[0] for timestamp in df["es_timestamp"]]

# print(f"es_timestamp is: : {df['es_timestamp'][0]}")
# print(f"status_code_200_counter is: : {df['status_code_200_counter']}")
filled_data = df.to_dict(orient="records")
# print()
with open("Datos filtrados desde Mongo.json", "w", encoding="utf-8") as f:
    json.dump(filled_data, f, indent=2, default=str)
# Sort dataframe by timestamp for time series analysis
df = df.sort_values("es_timestamp").reset_index(drop=True)

# Set timestamp as index for time series with explicit frequency
df.set_index("es_timestamp", inplace=True)
df.index.freq = 'H'  # Explicitly set hourly frequency

# Basic statistics
summed_df: int = sum(df["status_code_200_counter"])
print(f"this is the sum of DF: {summed_df}")

# ARMA Model Implementation


def fit_arma_model(data, column_name):
    """Fit ARMA model and return results"""
    series = data[column_name].dropna()

    if len(series) < 10:
        print(f"Not enough data points for {column_name}")
        return None

    # Test for stationarity
    from statsmodels.tsa.stattools import adfuller
    adf_result = adfuller(series)
    print(f"\nADF Test for {column_name}:")
    print(f"ADF Statistic: {adf_result[0]:.6f}")
    print(f"p-value: {adf_result[1]:.6f}")

    # If not stationary, difference the series
    if adf_result[1] < 0.05:
        series_diff = series.diff().dropna()
        print("Series is not stationary, using differenced data")
        series_to_use = series_diff
        # print(f"this is series to use: {series_to_use}")
        # print(series_to_use["status_code_200_counter"])
        plt.subplot(2, 2, 1)
        plt.plot(series_to_use.index, series_to_use, color='magenta',
                 marker='o', mfc='pink', markersize=3)
        plt.title('Differentiated HTTP 200 Status Codes Over Time')
        plt.xlabel('Timestamp')
        plt.ylabel('Count')
        plt.xticks(rotation=45)
    else:
        series_to_use = series

    # Auto ARIMA to find best parameters
    try:
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.stats.diagnostic import acorr_ljungbox

        # Try different ARMA parameters with better model fitting
        best_aic = float('inf')
        best_model = None
        best_params = None

        # Try different ARMA parameters (reduced range for stability)
        for p in range(0, 4):  # Reduced from 6 to 4
            for q in range(0, 4):  # Reduced from 6 to 4
                try:
                    # Skip computationally expensive combinations
                    if p + q > 4:
                        continue

                    model = ARIMA(series_to_use, order=(p, 1, q))

                    # Try different fitting methods based on model complexity
                    if p + q <= 2:
                        fitted_model = model.fit(
                            method='lbfgs', cov_type='robust')
                    else:
                        fitted_model = model.fit(
                            method='mle', cov_type='robust')

                    if fitted_model.aic < best_aic:
                        best_aic = fitted_model.aic
                        best_model = fitted_model
                        best_params = (p, q)

                except Exception as e:
                    # More specific error handling
                    error_msg = str(e).lower()
                    if "singular matrix" not in error_msg and "convergence" not in error_msg:
                        print(
                            f"Warning: ARMA({p},{q}) failed: {str(e)[:50]}...")
                    continue

        if best_model:
            print(
                f"\nBest ARMA({best_params[0]}, {best_params[1]}) model for {column_name}:")
            print(f"AIC: {best_model.aic:.2f}")
            print(best_model.summary())

            # Enhanced residual analysis
            residuals = best_model.resid
            ljung_box = acorr_ljungbox(residuals, lags=min(
                10, len(residuals)//5), return_df=True)
            lb_pvalue = ljung_box['lb_pvalue'].iloc[-1]

            print(f"\nResidual Diagnostics:")
            print(f"Ljung-Box Test p-value: {lb_pvalue:.4f}")

            if lb_pvalue < 0.05:
                print(
                    "⚠️  WARNING: Residuals show autocorrelation - model may be inadequate")
                print(
                    "   Consider: Higher order ARMA, seasonal terms, or different model")

                # Try ARIMA with differencing if pure ARMA fails
                try:
                    print("   Attempting ARIMA(p,1,q) with differencing...")
                    # Use simpler parameters for ARIMA fallback
                    p_arima = min(best_params[0], 2)
                    q_arima = min(best_params[1], 2)

                    arima_model = ARIMA(series, order=(p_arima, 1, q_arima))
                    arima_fitted = arima_model.fit(
                        method='lbfgs', cov_type='robust')

                    arima_residuals = arima_fitted.resid
                    arima_ljung = acorr_ljungbox(arima_residuals, lags=min(
                        10, len(arima_residuals)//5), return_df=True)
                    arima_lb_pvalue = arima_ljung['lb_pvalue'].iloc[-1]

                    if arima_lb_pvalue > lb_pvalue:
                        print(
                            f"   ARIMA({p_arima},1,{q_arima}) model performs better: p-value = {arima_lb_pvalue:.4f}")
                        if arima_lb_pvalue > 0.05:
                            print("   ✅ ARIMA residuals pass Ljung-Box test")
                            return arima_fitted, (p_arima, 1, q_arima)

                except Exception as e:
                    print(f"   ARIMA attempt failed: {str(e)[:60]}...")
            else:
                print("✅ Residuals pass Ljung-Box test - good model fit")

            # Additional diagnostic
            from scipy.stats import jarque_bera
            jb_stat, jb_pvalue = jarque_bera(residuals)
            print(f"Jarque-Bera normality test p-value: {jb_pvalue:.4f}")
            if jb_pvalue < 0.05:
                print("⚠️  Residuals are not normally distributed")

            return best_model, best_params
        else:
            print(f"No suitable ARMA model found for {column_name}")
            print("Trying simple AR(1) model as fallback...")
            try:
                simple_model = ARIMA(series_to_use, order=(1, 0, 0))
                simple_fitted = simple_model.fit(method='lbfgs')
                return simple_fitted, (1, 0)
            except:
                print("Even simple AR(1) model failed")
                return None

    except Exception as e:
        print(f"Error fitting ARMA model for {column_name}: {e}")

        # Suggest alternative approaches
        print(f"\n💡 Suggestions for {column_name}:")
        print("   1. Try seasonal ARIMA (SARIMA) if data has daily/weekly patterns")
        print("   2. Consider external variables (ARIMAX)")
        print("   3. Try exponential smoothing models")
        print("   4. Check for outliers or structural breaks")

        return None

# Add diagnostic plotting function


def plot_residual_diagnostics(model, title):
    """Plot comprehensive residual diagnostics"""
    if model is None:
        return

    residuals = model.resid

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f'Residual Diagnostics - {title}')

    # 1. Residuals over time
    axes[0, 0].plot(residuals)
    axes[0, 0].set_title('Residuals Over Time')
    axes[0, 0].set_ylabel('Residuals')

    # 2. Residuals histogram
    axes[0, 1].hist(residuals, bins=20, density=True, alpha=0.7)
    axes[0, 1].set_title('Residuals Distribution')
    axes[0, 1].set_ylabel('Density')

    # 3. Q-Q plot
    stats.probplot(residuals, dist="norm", plot=axes[1, 0])
    axes[1, 0].set_title('Q-Q Plot')

    # 4. ACF of residuals
    from statsmodels.graphics.tsaplots import plot_acf
    plot_acf(residuals, lags=20, ax=axes[1, 1])
    axes[1, 1].set_title('ACF of Residuals')

    plt.tight_layout()
    plt.show()


# Fit ARMA models for both metrics
print("=== ARMA Model Analysis ===")
result_200 = fit_arma_model(df, "status_code_200_counter")
result_5xx = fit_arma_model(df, "status_code_5xx_counter")

# Handle None results safely
if result_200:
    model_200, params_200 = result_200
else:
    model_200, params_200 = None, None

if result_5xx:
    model_5xx, params_5xx = result_5xx
else:
    model_5xx, params_5xx = None, None

# Show residual diagnostics
if model_200:
    plot_residual_diagnostics(model_200, "200 Status Codes")
if model_5xx:
    plot_residual_diagnostics(model_5xx, "5xx Status Codes")

# Forecasting


def forecast_arma(model, steps=60):  # 60 minutes ahead
    """Generate forecasts from ARMA model"""
    if model:
        forecast = model.forecast(steps=steps)
        conf_int = model.get_forecast(steps=steps).conf_int()
        return forecast, conf_int
    return None, None


# Generate forecasts
if model_200:
    forecast_200, conf_int_200 = forecast_arma(model_200)
    print(f"\nNext hour forecast for 200 status codes: {forecast_200[:10]}")

if model_5xx:
    forecast_5xx, conf_int_5xx = forecast_arma(model_5xx)
    print(f"\nNext hour forecast for 5xx status codes: {forecast_5xx[:10]}")

# Enhanced visualization
plt.figure(figsize=(15, 10))

# Plot 1: 200 status codes
plt.subplot(2, 2, 1)
plt.plot(df.index, df["status_code_200_counter"],
         color='magenta', marker='o', mfc='pink', markersize=3)
plt.title('HTTP 200 Status Codes Over Time')
plt.xlabel('Timestamp')
plt.ylabel('Count')
plt.xticks(rotation=45)

# Plot 2: 5xx status codes
plt.subplot(2, 2, 2)
plt.plot(df.index, df["status_code_5xx_counter"],
         color='red', marker='o', mfc='orange', markersize=3)
plt.title('HTTP 5xx Status Codes Over Time')
plt.xlabel('Timestamp')
plt.ylabel('Count')
plt.xticks(rotation=45)

# Plot 3: ACF and PACF for 200 codes
if len(df["status_code_200_counter"].dropna()) > 10:
    plt.subplot(2, 2, 3)
    from statsmodels.graphics.tsaplots import plot_acf
    plot_acf(df["status_code_200_counter"].dropna(), lags=20, ax=plt.gca())
    plt.title('ACF - 200 Status Codes')
    plt.xlabel('Lag')
    plt.ylabel('Autocorrelation')

# Plot 4: ACF and PACF for 5xx codes
if len(df["status_code_5xx_counter"].dropna()) > 10:
    plt.subplot(2, 2, 4)
    from statsmodels.graphics.tsaplots import plot_acf
    plot_acf(df["status_code_5xx_counter"].dropna(), lags=20, ax=plt.gca())

    plt.title('ACF - 5xx Status Codes')
    plt.xlabel('Lag')
    plt.ylabel('Autocorrelation')

plt.tight_layout()
plt.show()

# Additional Analysis Functions


def calculate_error_metrics(actual, predicted):
    """Calculate common forecasting error metrics"""
    mse = np.mean((actual - predicted) ** 2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(actual - predicted))
    mape = np.mean(np.abs((actual - predicted) / actual)) * 100

    return {
        'MSE': mse,
        'RMSE': rmse,
        'MAE': mae,
        'MAPE': mape
    }


def detect_anomalies(data, column, window=60, threshold=3):
    """Detect anomalies using rolling statistics"""
    series = data[column]
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()

    # Z-score based anomaly detection
    z_scores = np.abs((series - rolling_mean) / rolling_std)
    anomalies = z_scores > threshold

    print(f"\nAnomalies detected in {column}: {anomalies.sum()} points")
    return anomalies


def correlation_analysis(df):
    """Analyze correlation between status codes"""
    correlation = df[['status_code_200_counter',
                      'status_code_5xx_counter']].corr()
    print("\nCorrelation Matrix:")
    print(correlation)

    # Plot correlation
    plt.figure(figsize=(8, 6))
    plt.scatter(df['status_code_200_counter'],
                df['status_code_5xx_counter'], alpha=0.6)
    plt.xlabel('200 Status Codes')
    plt.ylabel('5xx Status Codes')
    plt.title('Correlation between 200 and 5xx Status Codes')
    plt.show()

    return correlation


# Perform additional analyses
print("\n=== Anomaly Detection ===")
anomalies_200 = detect_anomalies(df, 'status_code_200_counter')
anomalies_5xx = detect_anomalies(df, 'status_code_5xx_counter')

print("\n=== Correlation Analysis ===")
correlation_matrix = correlation_analysis(df)

# Model validation with train/test split


def validate_model(data, column, test_size=0.2):
    """Validate ARMA model with train/test split"""
    series = data[column].dropna()
    split_point = int(len(series) * (1 - test_size))

    train_data = series[:split_point]
    test_data = series[split_point:]

    if len(train_data) < 10 or len(test_data) < 5:
        print(f"Not enough data for validation of {column}")
        return None

    # Fit model on training data
    try:
        # Simple ARMA(1,1), adding arima works worse it seems
        model = ARIMA(train_data, order=(2, 0, 2))
        fitted_model = model.fit()

        # Forecast test period
        forecast = fitted_model.forecast(steps=len(test_data))

        # Calculate metrics
        metrics = calculate_error_metrics(test_data.values, forecast)

        print(f"\nValidation Results for {column}:")
        for metric, value in metrics.items():
            print(f"{metric}: {value:.4f}")

        return fitted_model, metrics

    except Exception as e:
        print(f"Validation error for {column}: {e}")
        return None, None


print("\n=== Model Validation ===")
val_model_200, metrics_200 = validate_model(df, 'status_code_200_counter')
val_model_5xx, metrics_5xx = validate_model(df, 'status_code_5xx_counter')

# Save results to file
results = {
    'timestamp': pd.Timestamp.now().isoformat(),
    'data_points': len(df),
    'models': {
        'status_200': {
            'parameters': params_200 if 'params_200' in locals() else None,
            'validation_metrics': metrics_200
        },
        'status_5xx': {
            'parameters': params_5xx if 'params_5xx' in locals() else None,
            'validation_metrics': metrics_5xx
        }
    },
    'anomalies': {
        'status_200_count': int(anomalies_200.sum()) if 'anomalies_200' in locals() else 0,
        'status_5xx_count': int(anomalies_5xx.sum()) if 'anomalies_5xx' in locals() else 0
    },
    'correlation': correlation_matrix.to_dict() if 'correlation_matrix' in locals() else None
}

with open("arma_analysis_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nAnalysis complete! Results saved to arma_analysis_results.json")

client.close()
