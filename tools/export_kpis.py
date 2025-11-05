"""
tools/export_kpis.py
Exporta a CSV todas las VISTAS de db/predictions.db para cargarlas rápido en Power BI (Quick Create)

Uso:
  python tools/export_kpis.py

Genera archivos en data/export/:
  - kpis_globales.csv
  - kpis_por_anio.csv (si tu vista tiene tilde, también intenta kpis_por_año)
  - predictions_enriched.csv
  - top10_peores_errores.csv
  - scatter_ready.csv
"""
import sqlite3
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / "db" / "predictions.db"
OUT_DIR = BASE / "data" / "export"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Lista de vistas a exportar (incluye ambas variantes por el tema de la ñ/tilde)
VIEWS = [
    "kpis_globales",
    "kpis_por_año",
    "kpis_por_anio",
    "predictions_enriched",
    "top10_peores_errores",
    "scatter_ready",
]

def export_view(con, view_name: str) -> bool:
    try:
        df = pd.read_sql_query(f"SELECT * FROM {view_name}", con)
    except Exception:
        return False
    # Normaliza nombre de archivo (sin tildes/ñ)
    safe = (view_name
            .replace("ñ", "n").replace("Ñ", "N")
            .replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u"))
    out = OUT_DIR / f"{safe}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"[ok] {view_name} -> {out}")
    return True

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No existe la DB: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as con:
        exported_any = False
        for v in VIEWS:
            exported_any |= export_view(con, v)
        if not exported_any:
            raise RuntimeError(
                "No pude exportar ninguna vista. "
                "¿Ya corriste kafka/consumer.py para crearlas y poblar datos?"
            )

if __name__ == "__main__":
    main()
