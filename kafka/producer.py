# kafka/producer.py
# ---------------------------------------------------------------
# - Lee 5 CSVs y hace ETL (sin usar unificado previo)
# - Split 70/30 -> columnas is_train / is_test
# - Envía CADA FILA al tópico Kafka como JSON
# - Imprime en pantalla CADA MENSAJE (caja + JSON completo)
# ---------------------------------------------------------------

from __future__ import annotations
import os, sys, json, time
from pathlib import Path
import pandas as pd
from kafka import KafkaProducer
from sklearn.model_selection import train_test_split

# Asegura import de src.* cuando ejecutas: python kafka\producer.py
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.etl import load_unified, FEATURES, TARGET, ID_COLS  # usa tus constantes

BASE      = Path(__file__).resolve().parents[1]
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC     = os.getenv("KAFKA_TOPIC", "happiness_features")
SLEEP_MS  = int(os.getenv("PRODUCER_SLEEP_MS", "3"))  # throttling leve para leer lo impreso

def box(title: str, lines: list[str], width: int = 70) -> str:
    """Caja ascii para logs bonitos."""
    title = f" {title} "
    top = "┌" + "─" * width + "┐"
    mid = "├" + "─" * width + "┤"
    bot = "└" + "─" * width + "┘"
    head = f"│{title[:width].ljust(width)}│"
    body = "\n".join(f"│{ln[:width].ljust(width)}│" for ln in lines)
    return f"{top}\n{head}\n{mid}\n{body}\n{bot}"

def message_preview(i: int, msg: dict) -> str:
    """Construye la caja + JSON pretty de lo que se envía."""
    country = msg.get("Country")
    year    = msg.get("Year")
    y_true  = msg.get("Happiness Score")
    is_tr   = msg.get("is_train")
    is_te   = msg.get("is_test")
    gdp     = msg.get("GDP per capita")
    soc     = msg.get("Social support")
    hlth    = msg.get("Healthy life expectancy")
    fr      = msg.get("Freedom")
    corr    = msg.get("Perceptions of corruption")

    lines = [
        f"Country: {country}   Year: {year}",
        f"Flags  : train={is_tr}   test={is_te}",
        f"y_true : {y_true}",
        f"feat   : gdp={gdp}  social={soc}  health={hlth}",
        f"         freedom={fr}  corrupt={corr}",
    ]
    bx = box(f"SENDING [{i:04d}] → {country} ({year})", lines, width=78)
    pretty_json = json.dumps(msg, indent=2, ensure_ascii=False)
    return f"{bx}\n{pretty_json}\n"

def main():
    # 1) ETL desde los 5 CSV (NO lee un archivo unificado guardado)
    df = load_unified()

    # 2) Selección columnas y split 70/30 (igual al training)
    data = df[ID_COLS + FEATURES + [TARGET]].dropna()
    X = data[FEATURES].astype(float)
    y = data[TARGET].astype(float)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.30, random_state=42)

    data = data.copy()
    data["is_train"] = 0
    data["is_test"]  = 0
    data.loc[X_tr.index, "is_train"] = 1
    data.loc[X_te.index, "is_test"]  = 1
    data["y_true"] = data[TARGET]

    # 3) Kafka Producer
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    print(
        "\n[producer] ready\n"
        f"  • topic:     {TOPIC}\n"
        f"  • bootstrap: {BOOTSTRAP}\n"
        f"  • rows:      {len(data)}\n"
        "--------------------------------------------------------------"
    )

    sent = 0
    for i, (_, r) in enumerate(data.iterrows(), start=1):
        msg = {
            "Country": r["Country"],
            "Year": int(r["Year"]),
            "GDP per capita": float(r["GDP per capita"]),
            "Social support": float(r["Social support"]),
            "Healthy life expectancy": float(r["Healthy life expectancy"]),
            "Freedom": float(r["Freedom"]),
            "Perceptions of corruption": float(r["Perceptions of corruption"]),
            "Happiness Score": float(r["y_true"]),
            "is_train": int(r["is_train"]),
            "is_test": int(r["is_test"]),
        }

        # ENVÍO del mensaje
        producer.send(TOPIC, msg)
        sent += 1

        # LOG: imprimir CADA MENSAJE (caja + JSON)
        print(message_preview(i, msg))

        # Pequeña pausa para que la terminal sea legible
        if SLEEP_MS > 0:
            time.sleep(SLEEP_MS / 100000.0)

    producer.flush()
    print(f"✔ done. sent={sent} → topic={TOPIC} @ {BOOTSTRAP}")

if __name__ == "__main__":
    main()
