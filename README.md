````markdown
# Workshop 3 — World Happiness (2015–2019) 🌍  
**Streaming + ETL + ML + Data Warehouse + Power BI**

Proyecto completo de punta a punta basado en el World Happiness Report:

1. ✅ Unificación y limpieza de los 5 CSV (2015–2019).
2. ✅ EDA sólido para entender las variables clave.
3. ✅ Entrenamiento de un modelo de regresión lineal múltiple.
4. ✅ Data Streaming con Kafka: producer envía registros limpios + flags train/test.
5. ✅ Consumer aplica el modelo y carga resultados en un Data Warehouse PostgreSQL.
6. ✅ Tabla única `predictions` lista para analítica y dashboard en Power BI.

Todo orquestado con: 🐍 **Python**, 🐳 **Docker**, 🐘 **PostgreSQL**, 🔁 **Kafka**, 📊 **Power BI** y 🧩 **VS Code**.

---

## 1. Tecnologías usadas

- 🐍 **Python 3**
- 📓 **Jupyter Notebooks** (`notebooks/EDA.ipynb`, `notebooks/ModelTraining.ipynb`)
- 🔁 **Apache Kafka**
- 🐘 **PostgreSQL** (Data Warehouse)
- 🐳 **Docker / docker-compose**
- 🧩 **VS Code** + extensiones:
  - Python
  - Jupyter
  - SQLTools + SQLTools PostgreSQL Driver
- 📊 **Power BI Desktop**
- 📦 **scikit-learn**

---

## 2. Estructura del proyecto

```text
.
├─ data/
│  ├─ 2015.csv ... 2019.csv          # Datos crudos originales
├─ db/
│  └─ pgdata/                        # Data de Postgres (montado por Docker)
├─ docs/
│  └─ REPORT.md                      # Reporte del proyecto
├─ kafka/
│  ├─ producer.py                    # Producer de Kafka (stream de features)
│  └─ consumer.py                    # Consumer Kafka -> PostgreSQL
├─ model/
│  └─ happiness_model.pkl            # Modelo entrenado (LinearRegression)
├─ notebooks/
│  ├─ EDA.ipynb                      # Limpieza + análisis + unificación
│  └─ ModelTraining.ipynb            # Experimentos de modelo
├─ src/
│  ├─ __init__.py
│  ├─ etl.py                         # Lógica de ETL reutilizable
│  ├─ train_model.py                 # Entrenamiento final y guardado del modelo
│  └─ evaluate.py (opcional)
├─ docker-compose.yml
├─ requirements.txt
├─ .env
└─ README.md
````

---

## 3. Flujo general 🧠

### 3.1 ETL + EDA (`notebooks/EDA.ipynb` + `src/etl.py`)

**Objetivo**
Unificar los 5 CSV, limpiar nombres de columnas, asegurar tipos numéricos y dejar las features listas para entrenamiento y streaming.

Pasos clave:

* Lectura de `2015.csv`–`2019.csv` desde `data/`.

* Normalización de columnas:

  * `Country` / `Country or region` → `Country`
  * `Score` / `Happiness Score` → `Happiness Score`
  * `Economy (GDP per Capita)` / `GDP per capita` → `GDP per capita`
  * `Health (Life Expectancy)` / `Healthy life expectancy` → `Healthy life expectancy`
  * Unificación de columnas de apoyo social, libertad y corrupción.

* Construcción del dataframe unificado con:

  ```text
  Country, Year, Happiness Score,
  GDP per capita, Social support,
  Healthy life expectancy, Freedom,
  Perceptions of corruption
  ```

* Análisis exploratorio:

  * Distribuciones y estadísticas descriptivas.
  * Matriz de correlación entre features y felicidad.
  * Visualizaciones para comportamiento por año y país.

* No se aplica tratamiento agresivo de outliers (no aporta mejora clara); la decisión se documenta.

🔎 **Rol del EDA**

* Justifica la selección de variables finales.
* Garantiza consistencia entre años.
* Define la lógica de ETL centralizada en `src/etl.py`, usada tanto en entrenamiento como en streaming (sin “trampas” con datasets distintos).

---

### 3.2 Entrenamiento del modelo (`src/train_model.py`)

**Modelo**: `LinearRegression` (regresión lineal múltiple)

**Features finales**:

```python
FEATURES = [
    "GDP per capita",
    "Social support",
    "Healthy life expectancy",
    "Freedom",
    "Perceptions of corruption",
]
TARGET = "Happiness Score"
```

**Lógica**:

1. Usa `load_unified()` de `src/etl.py`.
2. Filtra filas completas en `FEATURES + TARGET`.
3. Split 70/30 (`random_state=42`):

   * 70% → train
   * 30% → test
4. Entrena `LinearRegression` con el set de entrenamiento.
5. Evalúa sobre el **test set**:

   * R²
   * MAE
   * RMSE
6. Guarda el modelo en `model/happiness_model.pkl`.

**Salida esperada (ejemplo)**:

```text
================ Model Training ================
Samples:
  Train: 329
  Test : 141

Performance on TEST set:
  R²   : 0.804
  MAE  : 0.401
  RMSE : 0.532

Coefficients:
  GDP per capita            : 0.9160
  Social support            : 0.6781
  Healthy life expectancy   : 1.2863
  Freedom                   : 1.5349
  Perceptions of corruption : 0.9633

Model saved to: model/happiness_model.pkl
================================================
```

Demuestra que el modelo se entrena bien y se evalúa solo con datos no vistos.

---

## 4. Streaming con Kafka 🔁

### 4.1 Producer (`kafka/producer.py`)

**Responsabilidades**

* Leer los 5 CSV originales desde `data/`.
* Aplicar el **mismo ETL** que el EDA (`src/etl.py`).
* Reconstruir el split 70/30 con la misma lógica:

  * `is_train = 1`, `is_test = 0` para filas de entrenamiento.
  * `is_train = 0`, `is_test = 1` para filas de prueba.
* Agregar `y_true` (`Happiness Score`).
* Enviar cada registro al topic Kafka `happiness_features` como JSON.

Ejemplo de mensaje:

```json
{
  "Country": "France",
  "Year": 2018,
  "GDP per capita": 1.324,
  "Social support": 1.472,
  "Healthy life expectancy": 0.996,
  "Freedom": 0.450,
  "Perceptions of corruption": 0.183,
  "Happiness Score": 6.489,
  "is_train": 1,
  "is_test": 0
}
```

**Salida típica**

```text
[producer] using topic=happiness_features @ localhost:9092
[producer] sending records...

→ (France, 2018, y_true=6.489, train=1, test=0)
→ (Brazil, 2019, y_true=6.300, train=0, test=1)
...

[producer] done. sent=781 → topic=happiness_features @ localhost:9092
```

---

### 4.2 Consumer (`kafka/consumer.py`) → PostgreSQL 🐘

**Responsabilidades**

* Escuchar el topic `happiness_features`.
* Para cada mensaje:

  * Construir el vector de features.
  * Cargar `happiness_model.pkl`.
  * Calcular `y_pred`.
  * Hacer **UPSERT** en la tabla `predictions` en PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS predictions (
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
```

* La constraint `UNIQUE` evita duplicados si se corre el pipeline varias veces.
* Se conserva:

  * Datos originales.
  * Flags de uso (`is_train`, `is_test`).
  * Valor real (`y_true`).
  * Predicción (`y_pred`).

**Ejemplo de salida**

```text
[consumer] ready
  • topic:      happiness_features
  • bootstrap:  localhost:9092
  • group_id:   workshop3-consumer
  • model:      model/happiness_model.pkl
  • postgres:   workshop@localhost:5432/workshop3
  • table:      predictions
  • features:   GDP per capita, Social support, Healthy life expectancy, Freedom, Perceptions of corruption
--------------------------------------------------------------

┌──────────────────────────────────────────────────────────────┐
│ France (2018)                                               │
├──────────────────────────────────────────────────────────────┤
│R²: 0.812    MAE: 0.320                                      │
│y_true: 6.489    y_pred: 6.402                               │
│train: 1    test: 0                                          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Brazil (2019)                                               │
├──────────────────────────────────────────────────────────────┤
│R²: 0.790    MAE: 0.410                                      │
│y_true: 6.300    y_pred: 6.052                               │
│train: 0    test: 1                                          │
└──────────────────────────────────────────────────────────────┘

✓ upsert batch=200  total=200
✔ finished. total_upserted=781
```

La tabla `predictions` queda lista para construir KPIs y visualizaciones en Power BI.

---

## 5. Notas de uso rápido 🧩

* Crear entorno virtual e instalar dependencias:

  ```bash
  python -m venv .venv
  .\.venv\Scripts\activate
  pip install -r requirements.txt
  ```

* Levantar servicios (Kafka, ZooKeeper, PostgreSQL) con `docker-compose.yml`.

* Usar **VS Code + SQLTools** para explorar la base:

  * Configurar conexión PostgreSQL (`localhost:5432`, db `workshop3`, user `workshop`).
  * Consultar:

    ```sql
    SELECT COUNT(*) FROM predictions;
    SELECT * FROM predictions LIMIT 10;
    ```

* Power BI se conecta directamente a PostgreSQL sobre la tabla `predictions` para construir el dashboard de KPIs y performance del modelo.