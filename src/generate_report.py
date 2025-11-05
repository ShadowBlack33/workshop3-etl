# src/generate_report.py
# Genera docs/REPORT.md usando datos reales de SQLite o CSVs exportados.
from pathlib import Path
import sqlite3
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / "db" / "predictions.db"
DOCS = BASE / "docs"
DOCS.mkdir(parents=True, exist_ok=True)

def read_view(view_name: str) -> pd.DataFrame:
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as con:
            return pd.read_sql_query(f"SELECT * FROM {view_name}", con)
    # fallback CSVs
    exp = BASE / "data" / "export"
    alt = {
        "kpis_por_año": "kpis_por_anio.csv",
        "kpis_por_anio": "kpis_por_anio.csv",
        "kpis_globales": "kpis_globales.csv",
        "predictions_enriched": "predictions_enriched.csv",
        "top10_peores_errores": "top10_peores_errores.csv",
    }
    f = exp / alt.get(view_name, f"{view_name}.csv")
    return pd.read_csv(f)

def fmt3(x):
    try:
        return f"{float(x):.3f}"
    except Exception:
        return str(x)

def to_md_table(df: pd.DataFrame, max_rows=15):
    d = df.copy()
    if len(d) > max_rows:
        d = d.head(max_rows)
    # formateo ligero
    for c in d.columns:
        if d[c].dtype.kind in "fc":
            d[c] = d[c].map(fmt3)
    # construir tabla MD
    header = "| " + " | ".join(d.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(d.columns)) + " |"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in d.itertuples(index=False, name=None)]
    return "\n".join([header, sep] + rows)

def main():
    # Cargar datos
    kglob = read_view("kpis_globales")
    try:
        kyear = read_view("kpis_por_año")
    except Exception:
        kyear = read_view("kpis_por_anio")
    enriched = read_view("predictions_enriched")
    try:
        topbad = read_view("top10_peores_errores")
    except Exception:
        topbad = pd.DataFrame()

    # KPIs globales
    g = kglob.iloc[0].to_dict() if not kglob.empty else {"n": 0, "mae": None, "rmse": None, "r2": None}

    # Tablas formateadas
    md_kglob = to_md_table(kglob.astype({"n": "int"}), max_rows=1) if not kglob.empty else "_No data_"
    md_kyear = to_md_table(kyear.sort_values("year"), max_rows=20) if not kyear.empty else "_No data_"

    # Top errores (detalle y vista)
    md_topbad = to_md_table(topbad, max_rows=10) if not topbad.empty else "_No data_"
    top_det = (enriched.sort_values("abs_error", ascending=False)
                        .loc[:, ["country","year","actual_happiness","predicted_happiness","abs_error"]]
                        .reset_index(drop=True))
    md_top_det = to_md_table(top_det, max_rows=15)

    # Reporte
    md = f"""# Workshop 3 – Model Evaluation & Reporting

**Dataset:** World Happiness (2015–2019).  
**Streaming:** Kafka → Consumer → SQLite (`db/predictions.db`) con *views* para KPIs.  
**Modelo:** Linear Regression (train 70% / test 30%), features seleccionadas:
- GDP per capita
- Social support
- Healthy life expectancy
- Freedom
- Perceptions of corruption
- (Generosity solo como contexto/EDA)

---

## 1. EDA (resumen breve)
- Unificación de columnas por año (estandarización de nombres).
- Conversión a numérico y manejo de valores faltantes.
- **Outliers:** inspección de distribuciones; winsorización leve (p1–p99) durante EDA para comparar robustez (sin alterar los CSV originales de entrenamiento).
- Correlaciones: las 5 features anteriores muestran relación con la variable objetivo (*Happiness Score*), especialmente GDP, Social support y Life expectancy.

> Nota: El EDA completo está en el notebook del proyecto.

---

## 2. Entrenamiento
- Split: **70% train / 30% test** (random_state=42).
- Modelo: **Linear Regression**.
- Guardado: `model/happiness_model.pkl`.
- Producer/Consumer: consumen/guardan registros con predicción en `predictions` (SQLite) y calculan *views* de KPIs.

---

## 3. Evaluación – KPIs globales (SQLite view: `kpis_globales`)
{md_kglob}

- **Interpretación:** Con **MAE={fmt3(g.get('mae'))}** y **RMSE={fmt3(g.get('rmse'))}**, el error medio y la raíz del error cuadrático medio son moderados.  
  El **R²={fmt3(g.get('r2'))}** indica la proporción de varianza explicada por el modelo (más cerca a 1, mejor).

---

## 4. Evaluación por año (SQLite view: `kpis_por_anio`)
{md_kyear}

- **Lectura:** Permite ver si el desempeño mejora o empeora en ciertos años. Útil para detectar *drift* temporal o cambios de distribución.

---

## 5. Errores más altos
### 5.1 Vista resumida (SQLite view: `top10_peores_errores`)
{md_topbad}

### 5.2 Detalle (Top 15 por `abs_error` desde `predictions_enriched`)
{md_top_det}

- **Lectura:** Países/años con error alto pueden indicar:
  - Regiones con dinámica distinta (no capturada por el modelo).
  - Falta de variables explicativas (ej. shocks específicos del año).
  - Necesidad de modelos con interacciones o no lineales.

---

## 6. Streaming & Persistencia
- **Flujo:** Producer → Kafka → Consumer → predicción con `.pkl` → inserción en `predictions` (SQLite) → *views* para KPIs:
  - `predictions_enriched`, `kpis_globales`, `kpis_por_anio`, `top10_peores_errores`, `scatter_ready`.
- **Ventajas:** Plataforma (Power BI/Tableau/Looker) puede leer directamente la DB o los CSV exportados.

---

## 7. Limitaciones & Próximos pasos
- Modelo lineal base: explorar **Regularized Linear** (Ridge/Lasso) o **Tree-based** (RandomForest/XGBoost).
- Feature engineering: interacciones y transformaciones (log GDP, escalado).
- Validación: **k-fold** con *time-aware split* si hay dependencia temporal.
- Data drift: monitorear métricas por año y reentrenar periódicamente.
- Dashboard: integrar páginas (Overview, Trends, Model Fit) con filtros `year/country`.

---

**Generado automáticamente** por `src/generate_report.py` a partir de SQLite/CSVs.
"""

    out = DOCS / "REPORT.md"
    out.write_text(md, encoding="utf-8")
    print(f"[ok] Reporte generado: {out}")

if __name__ == "__main__":
    main()
