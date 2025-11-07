# src/train_model.py
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
from math import sqrt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import pickle
from src.etl import load_unified, FEATURES, TARGET, ID_COLS

BASE = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "happiness_model.pkl"

def main():
    df = load_unified()
    data = df[ID_COLS + FEATURES + [TARGET]].dropna()

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
    rmse = sqrt(mean_squared_error(y_test, y_pred))

    # Guardar
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    n_tr, n_te = len(X_train), len(X_test)
    print("\n" + "═"*64)
    print("  TRAIN SUMMARY (Linear Regression, 70/30)")
    print("─"*64)
    print(f"  Samples  •  train={n_tr:<4d}  test={n_te:<4d}")
    print(f"  Metrics  •  R2={r2:.3f}  MAE={mae:.3f}  RMSE={rmse:.3f}")
    print("  Features •  " + ", ".join(FEATURES))
    print(f"  Saved    •  {MODEL_PATH}")
    print("═"*64 + "\n")

if __name__ == "__main__":
    main()
