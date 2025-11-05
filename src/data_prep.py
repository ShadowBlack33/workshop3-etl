
import os
from pathlib import Path
import pandas as pd
import numpy as np

# Column standardization mapping (by substrings)
STD_COLS = {
    "Happiness Score": ["happiness score", "score", "happiness.score"],
    "GDP per capita": ["economy (gdp per capita)", "gdp per capita", "logged gdp per capita"],
    "Social support": ["family", "social support"],
    "Healthy life expectancy": ["health (life expectancy)", "healthy life expectancy"],
    "Freedom": ["freedom", "freedom to make life choices"],
    "Generosity": ["generosity"],
    "Perceptions of corruption": ["trust (government corruption)", "perceptions of corruption", "perception of corruption"]
}
COUNTRY_ALIASES = ["country", "country or region", "country.region"]
REGION_ALIASES = ["region"]

def normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", " ").replace("-", " ")

def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {}
    cols_norm = {c: normalize_name(c) for c in df.columns}
    # Country
    for c, n in cols_norm.items():
        if n in COUNTRY_ALIASES:
            colmap[c] = "Country"
        if n in REGION_ALIASES and "Country" not in colmap.values():
            # keep Region if exists
            colmap[c] = "Region"
    # Standards
    for std, aliases in STD_COLS.items():
        for c, n in cols_norm.items():
            for alias in aliases:
                if alias in n and std not in colmap.values():
                    colmap[c] = std
    # Year sometimes exists; if present keep
    for c, n in cols_norm.items():
        if n == "year":
            colmap[c] = "Year"
    # Apply rename
    df2 = df.rename(columns=colmap).copy()
    return df2

def load_and_unify(data_dir: Path) -> pd.DataFrame:
    frames = []
    for csv_path in sorted(data_dir.glob("*.csv")):
        try:
            year = int(''.join(ch for ch in csv_path.stem if ch.isdigit()))
        except:
            year = None
        df = pd.read_csv(csv_path)
        df = map_columns(df)
        # Ensure Year
        if "Year" not in df.columns and year is not None:
            df["Year"] = year
        # Keep only relevant columns if present
        wanted = ["Country","Year","Happiness Score","GDP per capita","Social support",
                  "Healthy life expectancy","Freedom","Generosity","Perceptions of corruption"]
        keep = [c for c in wanted if c in df.columns]
        df = df[keep]
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    # Basic cleaning: drop rows without target or country
    all_df = all_df.dropna(subset=["Happiness Score","Country"])
    # Fill numeric NaNs with column median
    num_cols = [c for c in all_df.columns if c not in ["Country","Year"]]
    for c in num_cols:
        if all_df[c].dtype.kind in "iufc":
            all_df[c] = all_df[c].fillna(all_df[c].median())
    # Deduplicate
    all_df = all_df.drop_duplicates()
    return all_df

def select_features(df: pd.DataFrame):
    features = ["GDP per capita","Social support","Healthy life expectancy","Freedom","Generosity","Perceptions of corruption"]
    features = [f for f in features if f in df.columns]
    X = df[features].copy()
    y = df["Happiness Score"].copy()
    meta = df[["Country","Year"]].copy() if "Year" in df.columns else df[["Country"]].copy()
    return X, y, meta, features

def main():
    base = Path(__file__).resolve().parents[1]
    data_dir = base / "data"
    out_dir = base / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_unify(data_dir)
    df.to_csv(out_dir / "combined_clean.csv", index=False)

    X, y, meta, features = select_features(df)
    full = pd.concat([meta, X, y.rename("Happiness Score")], axis=1)
    full.to_csv(out_dir / "features_full.csv", index=False)

    print("Rows:", len(df))
    print("Features used:", features)

if __name__ == "__main__":
    main()
