# src/train_model.py
# Entrena Linear Regression con winsorize 1–99% en FEATURES
# Guarda el modelo en model/happiness_model.pkl y muestra métricas.

from pathlib import Path
import pandas as pd
import numpy as np
import pickle

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

# -----------------------
# Config
# -----------------------
BASE = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "happiness_model.pkl"

FEATURES = [
    "GDP per capita",
    "Social support",
    "Healthy life expectancy",
    "Freedom",
    "Perceptions of corruption",
]
TARGET = "Happiness Score"
ID_COLS = ["Country", "Year"]

# -----------------------
# Lectura y armonización (2015–2019)
# -----------------------
RENAME_MAP = {
    2015: {
        "Country": "Country",
        "Happiness Score": "Happiness Score",
        "Economy (GDP per Capita)": "GDP per capita",
        "Family": "Social support",
        "Health (Life Expectancy)": "Healthy life expectancy",
        "Freedom": "Freedom",
        "Trust (Government Corruption)": "Perceptions of corruption",
    },
    2016: {
        "Country": "Country",
        "Happiness Score": "Happiness Score",
        "Economy (GDP per Capita)": "GDP per capita",
        "Family": "Social support",
        "Health (Life Expectancy)": "Healthy life expectancy",
        "Freedom": "Freedom",
        "Trust (Government Corruption)": "Perceptions of corruption",
    },
    2017: {
        "Country": "Country",
        "Happiness.Score": "Happiness Score",
        "Economy..GDP.per.Capita.": "GDP per capita",
        "Family": "Social support",
        "Health..Life.Expectancy.": "Healthy life expectancy",
        "Freedom": "Freedom",
        "Trust..Government.Corruption.": "Perceptions of corruption",
    },
    2018: {
        "Country or region": "Country",
        "Score": "Happiness Score",
        "GDP per capita": "GDP per capita",
        "Social support": "Social support",
        "Healthy life expectancy": "Healthy life expectancy",
        "Freedom to make life choices": "Freedom",
        "Perceptions of corruption": "Perceptions of corruption",
    },
    2019: {
        "Country or region": "Country",
        "Score": "Happiness Score",
        "GDP per capita": "GDP per capita",
        "Social support": "Social support",
        "Healthy life expectancy": "Healthy life expectancy",
        "Freedom to make life choices": "Freedom",
        "Perceptions of corruption": "Perceptions of corruption",
    },
}

def find_file(fname):
    for base in [BASE, BASE / "data"]:
        p = base / fname
        if p.exists():
            return p
    return None

def load_all_years():
    frames = []
    for y in [2015, 2016, 2017, 2018, 2019]:
        path = find_file(f"{y}.csv")
        if path is None:
            raise FileNotFoundError(f"No encontré {y}.csv (busqué en {BASE} y {BASE/'data'})")
        df = pd.read_csv(path).rename(columns=RENAME_MAP[y]).copy()
        df["Year"] = y
        keep = ID_COLS + [TARGET] + FEATURES
        cols = [c for c in keep if c in df.columns]
        df = df[cols].copy()
        # numeric
        for c in FEATURES + [TARGET]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

# -----------------------
# Winsorize helper
# -----------------------
def winsorize_df(df, cols, lo=0.01, hi=0.99):
    d2 = df.copy()
    for c in cols:
        s = pd.to_numeric(d2[c], errors="coerce")
        lo_v, hi_v = s.quantile(lo), s.quantile(hi)
        d2[c] = s.clip(lo_v, hi_v)
    return d2

def train():
    data = load_all_years()
    data = data.dropna(subset=FEATURES + [TARGET]).copy()

    # === Tratamiento de outliers consistente con el EDA ===
    data = winsorize_df(data, FEATURES, lo=0.01, hi=0.99)

    X = data[FEATURES].astype(float)
    y = data[TARGET].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, random_state=42
    )

    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    r2  = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)   # sin 'squared' por compatibilidad
    rmse = mse ** 0.5

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    print(f"R2={r2:.3f}  MAE={mae:.3f}  RMSE={rmse:.3f}")
    print(f"Modelo guardado en: {MODEL_PATH}")

if __name__ == "__main__":
    train()
