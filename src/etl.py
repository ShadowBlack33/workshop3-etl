# src/etl.py
# Unifica los CSV 2015–2019 desde ./data/ y normaliza nombres de columnas.
# Provee constantes compartidas por el proyecto.

from pathlib import Path
import pandas as pd

# --- Rutas base ---
BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"           # <--- SIEMPRE busca aquí 2015.csv ... 2019.csv

# --- Esquema estándar del proyecto ---
ID_COLS = ["Country", "Year"]
FEATURES = [
    "GDP per capita",
    "Social support",
    "Healthy life expectancy",
    "Freedom",
    "Perceptions of corruption",
]
TARGET = "Happiness Score"

# ---------------------------------------------------------------------
# Lectura y normalización por año
# ---------------------------------------------------------------------
def _read_year(year: int) -> pd.DataFrame:
    """
    Lee data/<year>.csv y la transforma al esquema estándar:
    Country, Year, FEATURES..., TARGET
    """
    path = DATA_DIR / f"{year}.csv"
    df = pd.read_csv(path)

    # Clonar para no modificar el original
    cur = df.copy()

    # Mapas de nombres por año
    if year in (2015, 2016):
        rename_map = {
            "Country": "Country",
            "Happiness Score": "Happiness Score",
            "Economy (GDP per Capita)": "GDP per capita",
            "Family": "Social support",
            "Health (Life Expectancy)": "Healthy life expectancy",
            "Freedom": "Freedom",
            "Trust (Government Corruption)": "Perceptions of corruption",
        }
        # En 2015/2016 no viene Year como columna; lo añadimos fijo
        cur["Year"] = year

    elif year == 2017:
        rename_map = {
            "Happiness.Score": "Happiness Score",
            "Economy..GDP.per.Capita.": "GDP per capita",
            "Family": "Social support",
            "Health..Life.Expectancy.": "Healthy life expectancy",
            "Freedom": "Freedom",
            "Trust..Government.Corruption.": "Perceptions of corruption",
            "Country": "Country",
        }
        cur["Year"] = year

    elif year in (2018, 2019):
        rename_map = {
            "Country or region": "Country",
            "Score": "Happiness Score",
            "GDP per capita": "GDP per capita",
            "Social support": "Social support",
            "Healthy life expectancy": "Healthy life expectancy",
            "Freedom to make life choices": "Freedom",
            "Perceptions of corruption": "Perceptions of corruption",
        }
        cur["Year"] = year

    else:
        raise ValueError(f"Año no soportado: {year}")

    # Renombrar columnas que existan
    available = {k: v for k, v in rename_map.items() if k in cur.columns}
    cur = cur.rename(columns=available)

    # Subconjunto al esquema esperado (las que estén disponibles)
    keep = [c for c in (ID_COLS + FEATURES + [TARGET]) if c in cur.columns]
    cur = cur[keep].copy()

    # Asegurar tipos
    cur["Country"] = cur["Country"].astype(str)
    cur["Year"] = pd.to_numeric(cur["Year"], errors="coerce").astype("Int64")

    for col in FEATURES + [TARGET]:
        if col in cur.columns:
            cur[col] = pd.to_numeric(cur[col], errors="coerce")

    return cur


def load_unified() -> pd.DataFrame:
    """
    Lee 2015..2019 de ./data/, normaliza y concatena.
    Devuelve un DataFrame con columnas:
      Country, Year, FEATURES..., Happiness Score
    """
    frames = []
    for y in (2015, 2016, 2017, 2018, 2019):
        frames.append(_read_year(y))

    df_all = pd.concat(frames, ignore_index=True)

    # Orden básico (opcional)
    cols_order = ID_COLS + FEATURES + [TARGET]
    cols_order = [c for c in cols_order if c in df_all.columns]
    df_all = df_all[cols_order]

    return df_all
