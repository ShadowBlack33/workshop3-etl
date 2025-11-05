
import os, time, json
from pathlib import Path
import pandas as pd
from kafka import KafkaProducer

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "happiness_topic")
DELAY_SEC = float(os.getenv("STREAM_DELAY", "0.5"))

base = Path(__file__).resolve().parents[1]
stream_csv = base / "data" / "processed" / "features_to_stream.csv"
df = pd.read_csv(stream_csv)

producer = KafkaProducer(bootstrap_servers=BOOTSTRAP)

for _, row in df.iterrows():
    message = row.to_dict()
    producer.send(TOPIC, json.dumps(message).encode("utf-8"))
    print(f"Sent -> {message.get('Country','?')} {message.get('Year','?')}: y={message.get('Happiness Score')}")
    time.sleep(DELAY_SEC)

producer.flush()
producer.close()
print("Producer finished.")
