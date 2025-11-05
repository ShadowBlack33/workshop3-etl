from pathlib import Path
import sqlite3
import pandas as pd

DB_PATH = Path("db/predictions.db")

qs = [
    ("Total filas en predictions", "SELECT COUNT(*) AS n FROM predictions"),
    ("KPIs globales", "SELECT * FROM kpis_globales"),
    ("KPIs por año", "SELECT * FROM kpis_por_año"),
    ("Top10 peores errores", "SELECT * FROM top10_peores_errores"),
    ("Muestras con mayor error", """
        SELECT country, year, actual_happiness, predicted_happiness, 
               (actual_happiness - predicted_happiness) AS error,
               ABS(actual_happiness - predicted_happiness) AS abs_error
        FROM predictions_enriched
        ORDER BY abs_error DESC
        LIMIT 5
    """)
]

if not DB_PATH.exists():
    raise SystemExit(f"No existe {DB_PATH}. Corre consumer + producer primero.")

with sqlite3.connect(DB_PATH) as conn:
    for title, q in qs:
        print("\n=== ", title, " ===")
        try:
            df = pd.read_sql_query(q, conn)
            print(df)
        except Exception as e:
            print("Error en consulta:", e)
