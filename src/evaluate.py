# src/evaluate.py
# Evalúa el desempeño del modelo desde SQLite (predictions.db) o CSVs exportados.
import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / "db" / "predictions.db"
OUT_DIR = BASE / "data" / "reports"
CSV_EXPORT = BASE / "data" / "export"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def read_view_sqlite(view_name: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(f"SELECT * FROM {view_name}", con)

def read_fallback_csv(name: str) -> pd.DataFrame:
    # nombre lógico -> archivo exportado
    mapping = {
        "predictions_enriched": "predictions_enriched.csv",
        "kpis_globales": "kpis_globales.csv",
        "kpis_por_año": "kpis_por_anio.csv",
        "kpis_por_anio": "kpis_por_anio.csv",
        "top10_peores_errores": "top10_peores_errores.csv",
    }
    f = CSV_EXPORT / mapping[name]
    if not f.exists():
        raise FileNotFoundError(f"CSV no encontrado: {f}")
    return pd.read_csv(f)

def load_df(name: str) -> pd.DataFrame:
    try:
        if DB_PATH.exists():
            return read_view_sqlite(name)
        return read_fallback_csv(name)
    except Exception:
        # Intento alterno para el tema de la ñ
        if name == "kpis_por_año":
            return load_df("kpis_por_anio")
        raise

def recompute_from_enriched(enriched: pd.DataFrame) -> dict:
    y = pd.to_numeric(enriched["actual_happiness"], errors="coerce")
    yhat = pd.to_numeric(enriched["predicted_happiness"], errors="coerce")
    ok = y.notna() & yhat.notna()
    y = y[ok].to_numpy()
    yhat = yhat[ok].to_numpy()
    n = y.size
    mae = float(np.mean(np.abs(y - yhat))) if n else float("nan")
    rmse = float(np.sqrt(np.mean((y - yhat) ** 2))) if n else float("nan")
    if n:
        ss_res = float(np.sum((y - yhat) ** 2))
        mean_y = float(np.mean(y))
        ss_tot = float(np.sum((y - mean_y) ** 2))
        r2 = float("nan") if ss_tot == 0 else 1.0 - ss_res / ss_tot
    else:
        r2 = float("nan")
    return {"n": n, "mae": mae, "rmse": rmse, "r2": r2}

def main():
    # Cargar fuentes
    enriched = load_df("predictions_enriched")
    kpi_glob = load_df("kpis_globales")
    try:
        kpi_year = load_df("kpis_por_año")
    except Exception:
        kpi_year = load_df("kpis_por_anio")
    try:
        top_bad = load_df("top10_peores_errores")
    except Exception:
        top_bad = pd.DataFrame()

    # Recalcular métricas para contraste
    rec = recompute_from_enriched(enriched)

    print("\n==== MODEL EVALUATION ====")
    if not kpi_glob.empty:
        g = kpi_glob.iloc[0].to_dict()
        print(f"Views -> N={int(g.get('n', 0))}  MAE={g.get('mae',0):.3f}  RMSE={g.get('rmse',0):.3f}  R2={g.get('r2',0):.3f}")
    else:
        print("kpis_globales vacío.")

    print(f"Recomputed -> N={rec['n']}  MAE={rec['mae']:.3f}  RMSE={rec['rmse']:.3f}  R2={rec['r2']:.3f}")

    # Salidas para el reporte / dash
    kpi_glob.to_csv(OUT_DIR / "kpis_globales.csv", index=False)
    (kpi_year.sort_values("year")
             .to_csv(OUT_DIR / "kpis_por_anio.csv", index=False))
    (enriched.sort_values("abs_error", ascending=False)
             .head(50)
             .to_csv(OUT_DIR / "top_errores_detalle.csv", index=False))
    if not top_bad.empty:
        top_bad.to_csv(OUT_DIR / "top10_peores_errores.csv", index=False)

    by_country = (enriched.assign(abs_error=pd.to_numeric(enriched["abs_error"], errors="coerce"))
                          .groupby("country", dropna=True)["abs_error"]
                          .mean()
                          .sort_values(ascending=False)
                          .reset_index()
                          .rename(columns={"abs_error": "mae"}))
    by_country.to_csv(OUT_DIR / "mae_por_pais.csv", index=False)

    print(f"\nCSV generados en: {OUT_DIR}")
    print(" - kpis_globales.csv, kpis_por_año.csv, top_errores_detalle.csv, top10_peores_errores.csv, mae_por_pais.csv")

if __name__ == "__main__":
    main()
