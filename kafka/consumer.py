# kafka/consumer.py — SQLite + KPIs (vistas sin ventanas) + batch + logs
import os
import json
import pickle
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
from kafka import KafkaConsumer

# --- Paths base ---
BASE = Path(__file__).resolve().parents[1]
DB_DIR = BASE / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "predictions.db"
MODEL_PATH = BASE / "model" / "happiness_model.pkl"

# --- Kafka (usa .env si existe) ---
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "happiness_topic")
GROUP_ID = os.getenv("KAFKA_GROUP", "happiness_group")
BATCH = int(os.getenv("BATCH_SIZE", "200"))

# --- Orden de features esperadas por el modelo ---
FEATURES = [
    "GDP per capita",
    "Social support",
    "Healthy life expectancy",
    "Freedom",
    "Perceptions of corruption",
]

# --- Carga modelo entrenado ---
with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

# --- Tabla destino (dejamos generosity como la tienes) ---
DDL = """
CREATE TABLE IF NOT EXISTS predictions (
    country TEXT,
    year INTEGER,
    gdp REAL,
    social_support REAL,
    healthy_life_expectancy REAL,
    freedom REAL,
    generosity REAL,
    corruption REAL,
    actual_happiness REAL,
    predicted_happiness REAL
);
"""

# --- VISTAS (sin window functions) ---
VIEWS_SQL = """
DROP VIEW IF EXISTS predictions_enriched;
CREATE VIEW predictions_enriched AS
SELECT
  country, year,
  gdp, social_support, healthy_life_expectancy, freedom, generosity, corruption,
  actual_happiness, predicted_happiness,
  (actual_happiness - predicted_happiness) AS error,
  ABS(actual_happiness - predicted_happiness) AS abs_error,
  (actual_happiness - predicted_happiness)*(actual_happiness - predicted_happiness) AS squared_error
FROM predictions;

DROP VIEW IF EXISTS kpis_globales;
CREATE VIEW kpis_globales AS
WITH m AS (
  SELECT
    COUNT(*) AS n,
    AVG(ABS(actual_happiness - predicted_happiness)) AS mae,
    AVG((actual_happiness - predicted_happiness)*(actual_happiness - predicted_happiness)) AS mse
  FROM predictions
),
rm AS (
  SELECT n, mae, sqrt(mse) AS rmse FROM m
),
mean_actual AS (
  SELECT AVG(actual_happiness) AS mu FROM predictions
),
ss AS (
  SELECT
    (SELECT SUM((actual_happiness - predicted_happiness)*(actual_happiness - predicted_happiness)) FROM predictions) AS ss_res,
    (SELECT SUM((actual_happiness - mu)*(actual_happiness - mu)) FROM predictions, mean_actual) AS ss_tot
)
SELECT
  (SELECT n  FROM rm)   AS n,
  (SELECT mae FROM rm)  AS mae,
  (SELECT rmse FROM rm) AS rmse,
  CASE WHEN ss_tot IS NULL OR ss_tot = 0 THEN NULL ELSE 1.0 - (ss_res/ss_tot) END AS r2
FROM ss;

-- Versión ASCII (sin 'ñ') y sin ventanas
DROP VIEW IF EXISTS kpis_por_anio;
CREATE VIEW kpis_por_anio AS
WITH base AS (
  SELECT
    year,
    ABS(actual_happiness - predicted_happiness) AS abs_error,
    (actual_happiness - predicted_happiness)*(actual_happiness - predicted_happiness) AS squared_error,
    actual_happiness
  FROM predictions
),
mean_year AS (
  SELECT year, AVG(actual_happiness) AS mean_actual
  FROM predictions
  GROUP BY year
),
agg AS (
  SELECT
    b.year,
    COUNT(*)                   AS n,
    AVG(b.abs_error)           AS mae,
    sqrt(AVG(b.squared_error)) AS rmse,
    SUM(b.squared_error)       AS ss_res,
    SUM( (b.actual_happiness - my.mean_actual)*(b.actual_happiness - my.mean_actual) ) AS ss_tot
  FROM base b
  JOIN mean_year my ON my.year = b.year
  GROUP BY b.year
)
SELECT
  year, n, mae, rmse,
  CASE WHEN ss_tot IS NULL OR ss_tot = 0 THEN NULL ELSE 1.0 - (ss_res/ss_tot) END AS r2
FROM agg
ORDER BY year;

DROP VIEW IF EXISTS top10_peores_errores;
CREATE VIEW top10_peores_errores AS
WITH agg AS (
  SELECT
    country,
    year,
    MAX(ABS(actual_happiness - predicted_happiness)) AS abs_error,
    MAX(actual_happiness)    AS actual_happiness,
    MAX(predicted_happiness) AS predicted_happiness
  FROM predictions
  GROUP BY country, year
)
SELECT *
FROM agg
ORDER BY abs_error DESC
LIMIT 10;

DROP VIEW IF EXISTS scatter_ready;
CREATE VIEW scatter_ready AS
SELECT actual_happiness AS y, predicted_happiness AS y_hat
FROM predictions;
"""

def init_db_and_views() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(DDL)
    con.commit()
    con.executescript(VIEWS_SQL)
    con.commit()
    con.close()

def to_float(x):
    try:
        return float(x)
    except Exception:
        return None

def flush_buffer(buffer):
    """Inserta batch en SQLite y refresca vistas."""
    if not buffer:
        return
    df = pd.DataFrame(buffer)
    with sqlite3.connect(DB_PATH) as c:
        df.to_sql("predictions", c, if_exists="append", index=False)
        c.executescript(VIEWS_SQL)  # refresca vistas después del insert
    print(f"Inserted batch: {len(buffer)} rows -> {DB_PATH.resolve()}")

def main():
    # 1) DB lista + vistas creadas/recreadas
    init_db_and_views()

    # 2) Kafka consumer
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    print(f"[consumer] listening on {BOOTSTRAP} topic={TOPIC}")
    parts = consumer.partitions_for_topic(TOPIC)
    print(f"[consumer] topic partitions: {parts}")

    buffer = []
    try:
        for msg in consumer:
            data = msg.value  # ya viene json->dict por value_deserializer

            # X como DataFrame con nombres de columna para evitar warnings
            X_df = pd.DataFrame([[to_float(data.get(f)) for f in FEATURES]],
                                columns=FEATURES)
            y_hat = float(model.predict(X_df)[0])

            row = {
                "country": data.get("Country"),
                "year": int(data.get("Year")) if data.get("Year") is not None else None,
                "gdp": to_float(data.get("GDP per capita")),
                "social_support": to_float(data.get("Social support")),
                "healthy_life_expectancy": to_float(data.get("Healthy life expectancy")),
                "freedom": to_float(data.get("Freedom")),
                "generosity": to_float(data.get("Generosity")),
                "corruption": to_float(data.get("Perceptions of corruption")),
                "actual_happiness": to_float(data.get("Happiness Score")),
                "predicted_happiness": y_hat,
            }
            buffer.append(row)

            print(
                f"Saved -> {row['country']} {row['year']}: "
                f"actual={row['actual_happiness']} pred={row['predicted_happiness']:.3f}"
            )

            if len(buffer) >= BATCH:
                flush_buffer(buffer)
                buffer.clear()
    except KeyboardInterrupt:
        pass
    finally:
        flush_buffer(buffer)
        print("[consumer] finished.")

if __name__ == "__main__":
    main()
