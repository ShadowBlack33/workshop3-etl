# kafka/consumer_pg.py
# ---------------------------------------------------------------
# - Lee mensajes de Kafka (happiness_features)
# - Usa el modelo entrenado (model/happiness_model.pkl)
# - UPSERT en PostgreSQL (tabla predictions)
# - Mantiene is_train / is_test / y_true / y_pred
# - Sin vistas: KPIs se hacen en Power BI
# ---------------------------------------------------------------

from __future__ import annotations

import os
import sys
import json
import warnings
from pathlib import Path

import pandas as pd
from kafka import KafkaConsumer
import psycopg2
from psycopg2.extras import execute_batch
import pickle

# Permitir imports relativos si hace falta
sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except Exception:
    pass
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# ------------------- Paths & modelo -------------------
BASE = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE / "model" / "happiness_model.pkl"

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

# ------------------- Config Kafka -------------------
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC     = os.getenv("KAFKA_TOPIC", "happiness_features")
GROUP_ID  = os.getenv("KAFKA_GROUP", "workshop3-consumer-pg")
BATCH     = int(os.getenv("BATCH_SIZE", "200"))

# ------------------- Config Postgres -------------------
PG_HOST  = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT  = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB    = os.getenv("POSTGRES_DB", "workshop3")
PG_USER  = os.getenv("POSTGRES_USER", "workshop")
PG_PASS  = os.getenv("POSTGRES_PASSWORD", "workshop")
PG_TABLE = os.getenv("POSTGRES_TABLE", "predictions")

FEATURES = [
    "GDP per capita",
    "Social support",
    "Healthy life expectancy",
    "Freedom",
    "Perceptions of corruption",
]

# ------------------- Conexión PG -------------------
def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )

# ------------------- Schema en Postgres -------------------
DDL = f"""
CREATE TABLE IF NOT EXISTS {PG_TABLE} (
    country   TEXT    NOT NULL,
    year      INTEGER NOT NULL,
    gdp       REAL,
    social    REAL,
    health    REAL,
    freedom   REAL,
    corrupt   REAL,
    y_true    REAL,
    is_train  INTEGER,
    is_test   INTEGER,
    y_pred    REAL,
    UNIQUE(country, year, is_train, is_test)
);
"""

UPSERT_SQL = f"""
INSERT INTO {PG_TABLE}
(country, year, gdp, social, health, freedom, corrupt, y_true, is_train, is_test, y_pred)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (country, year, is_train, is_test) DO UPDATE SET
    gdp     = EXCLUDED.gdp,
    social  = EXCLUDED.social,
    health  = EXCLUDED.health,
    freedom = EXCLUDED.freedom,
    corrupt = EXCLUDED.corrupt,
    y_true  = EXCLUDED.y_true,
    y_pred  = EXCLUDED.y_pred;
"""

def init_db():
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()
    cur.close()
    conn.close()

def to_float(x):
    try:
        return float(x)
    except Exception:
        return None

# Métricas rolling por país (para mostrar algo bonito en logs)
class CountryStats:
    __slots__ = ("n", "mean_y", "M2", "ss_res", "sum_abs")

    def __init__(self):
        self.n = 0
        self.mean_y = 0.0
        self.M2 = 0.0
        self.ss_res = 0.0
        self.sum_abs = 0.0

    def update(self, y, y_hat):
        err = y - y_hat
        self.ss_res += err * err
        self.sum_abs += abs(err)
        self.n += 1
        delta = y - self.mean_y
        self.mean_y += delta / self.n
        delta2 = y - self.mean_y
        self.M2 += delta * delta2

    def r2(self):
        if self.n < 2 or self.M2 == 0:
            return None
        return 1.0 - (self.ss_res / self.M2)

    def mae(self):
        if self.n == 0:
            return None
        return self.sum_abs / self.n

def box(title: str, lines: list[str], width: int = 70) -> str:
    title = f" {title} "
    top = "┌" + "─" * width + "┐"
    mid = "├" + "─" * width + "┤"
    bot = "└" + "─" * width + "┘"
    head = f"│{title[:width].ljust(width)}│"
    body = "\n".join(f"│{ln[:width].ljust(width)}│" for ln in lines)
    return f"{top}\n{head}\n{mid}\n{body}\n{bot}"

def predict_from_msg(d: dict) -> float:
    row = {f: to_float(d.get(f)) for f in FEATURES}
    X = pd.DataFrame([row])
    return float(model.predict(X)[0])

def flush_buffer(buf, total):
    if not buf:
        return total

    rows = [
        (
            r["country"], r["year"], r["gdp"], r["social"], r["health"],
            r["freedom"], r["corrupt"], r["y_true"], r["is_train"], r["is_test"],
            r["y_pred"]
        )
        for r in buf
    ]

    conn = get_pg_conn()
    cur = conn.cursor()
    execute_batch(cur, UPSERT_SQL, rows, page_size=100)
    conn.commit()
    cur.close()
    conn.close()

    total += len(rows)
    print(f"✓ upsert batch={len(rows)}  total={total}")
    return total

def main():
    init_db()

    print(
        "\n[consumer-pg] ready\n"
        f"  • topic:      {TOPIC}\n"
        f"  • bootstrap:  {BOOTSTRAP}\n"
        f"  • group_id:   {GROUP_ID}\n"
        f"  • model:      {MODEL_PATH}\n"
        f"  • postgres:   {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}\n"
        f"  • table:      {PG_TABLE}\n"
        f"  • features:   {', '.join(FEATURES)}\n"
        "--------------------------------------------------------------"
    )

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    buffer = []
    total = 0
    stats_by_country: dict[str, CountryStats] = {}

    try:
        for msg in consumer:
            d = msg.value

            try:
                y_hat = predict_from_msg(d)
            except Exception as e:
                print(f"✗ predict error: {e}")
                continue

            country = d.get("Country") or "?"
            year    = d.get("Year")
            y_true  = to_float(d.get("Happiness Score"))

            row = {
                "country": country,
                "year": int(year) if year is not None else None,
                "gdp": to_float(d.get("GDP per capita")),
                "social": to_float(d.get("Social support")),
                "health": to_float(d.get("Healthy life expectancy")),
                "freedom": to_float(d.get("Freedom")),
                "corrupt": to_float(d.get("Perceptions of corruption")),
                "y_true": y_true,
                "is_train": int(d.get("is_train") or 0),
                "is_test":  int(d.get("is_test")  or 0),
                "y_pred": y_hat,
            }
            buffer.append(row)

            # métricas por país
            if y_true is not None:
                st = stats_by_country.setdefault(country, CountryStats())
                st.update(y_true, y_hat)
                r2  = st.r2()
                mae = st.mae()
                r2_str  = f"{r2:.3f}" if r2 is not None else "N/A"
                mae_str = f"{mae:.3f}" if mae is not None else "N/A"
            else:
                r2_str, mae_str = "N/A", "N/A"

            lines = [
                f"R²: {r2_str}    MAE: {mae_str}",
                f"y_true: {y_true if y_true is not None else 'NA'}    y_pred: {y_hat:.3f}",
                f"train: {row['is_train']}    test: {row['is_test']}",
            ]
            print(box(f"{country} ({row['year']})", lines))

            if len(buffer) >= BATCH:
                total = flush_buffer(buffer, total)
                buffer.clear()

    except KeyboardInterrupt:
        pass
    finally:
        total = flush_buffer(buffer, total)
        print(f"✔ finished. total_upserted={total}")

if __name__ == "__main__":
    main()
