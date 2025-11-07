# Workshop 3 – Model Evaluation & Reporting

**Dataset:** World Happiness Report (2015–2019)  
**Arquitectura:** ETL + ML + Streaming con Kafka + Data Warehouse en PostgreSQL + Dashboard en Power BI  
**Modelo:** Linear Regression (70% train / 30% test)

---

## 1. Data & EDA (Exploratory Data Analysis)

### 1.1. Origen de los datos

Se utilizan los datasets oficiales del World Happiness Report para los años:

- `2015.csv`
- `2016.csv`
- `2017.csv`
- `2018.csv`
- `2019.csv`

Estos archivos se encuentran en la carpeta `data/` del proyecto.

### 1.2. Unificación y limpieza

Debido a que cada año presenta ligeras variaciones en nombres de columnas, se realiza un proceso de estandarización en `src/etl.py`, que también es reutilizado por el entrenamiento del modelo y el productor de Kafka (ETL único, consistente).

Principales transformaciones:

- Normalización de nombres:
  - `Country` / `Country or region` → `Country`
  - `Happiness Score` / `Score` → `Happiness Score`
  - `Economy (GDP per Capita)` / `GDP per capita` → `GDP per capita`
  - `Health (Life Expectancy)` / `Healthy life expectancy` → `Healthy life expectancy`
  - Columnas de soporte social, libertad y corrupción alineadas a:
    - `Social support`
    - `Freedom`
    - `Perceptions of corruption`
- Conversión a tipos numéricos para las variables relevantes.
- Inclusión explícita de la columna `Year`.

El dataset unificado final utilizado para modelado y streaming contiene:

```text
Country
Year
Happiness Score
GDP per capita
Social support
Healthy life expectancy
Freedom
Perceptions of corruption
````

### 1.3. Manejo de valores faltantes y outliers

* Se descartan filas con valores faltantes en las columnas utilizadas directamente para el modelo.
* No se aplica winsorización ni transformaciones agresivas de outliers en la versión final:

  * Durante el EDA se exploró el impacto de truncar valores extremos.
  * No se observaron mejoras significativas en el rendimiento del modelo.
  * Se documenta la decisión y se mantiene el dataset más cercano a los datos originales.

### 1.4. Hallazgos principales del EDA

* Fuerte correlación positiva entre:

  * `GDP per capita`, `Social support`, `Healthy life expectancy` y `Happiness Score`.
* `Freedom` y `Perceptions of corruption` también aportan señal relevante.
* Estos resultados justifican la selección de features para el modelo lineal.

> El detalle completo del análisis se encuentra en `notebooks/EDA.ipynb`.

---

## 2. Entrenamiento del Modelo

### 2.1. Configuración

* Modelo: **Linear Regression** (regresión lineal múltiple).
* Script: `src/train_model.py`
* Features utilizadas:

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

### 2.2. Proceso

1. Se llama a `load_unified()` en `src/etl.py` para asegurar el mismo ETL usado luego en producción.
2. Se filtran filas con datos completos en `FEATURES + TARGET`.
3. Se realiza un **split 70% / 30%** con `random_state=42`:

   * 70% → entrenamiento.
   * 30% → prueba.
4. Se entrena el modelo `LinearRegression` con los datos de entrenamiento.
5. Se evalúa el modelo usando **solo el test set**.
6. El modelo entrenado se guarda como:

```text
model/happiness_model.pkl
```

### 2.3. Métricas (sobre test set)

Ejemplo de resultados obtenidos:

* **R²:** 0.804
* **MAE:** 0.401
* **RMSE:** 0.532
* Muestra:

  * El modelo explica una buena parte de la variabilidad del `Happiness Score`.
  * El error medio es razonable para la escala (0–10 aprox).

> Las métricas exactas se generan al correr `python -m src.train_model` y se muestran en consola con un resumen formateado.

---

## 3. Arquitectura de Streaming & Data Warehouse

### 3.1. Objetivo

Implementar un flujo reproducible donde:

1. Los mismos datos y lógica de ETL usados para entrenar el modelo se utilicen en producción.
2. Cada registro tenga trazabilidad:

   * Si fue usado para entrenamiento (`is_train`).
   * Si fue usado para prueba (`is_test`).
   * Cuál fue su valor real (`y_true`).
   * Cuál fue la predicción del modelo (`y_pred`).
3. Todo quede centralizado en un **Data Warehouse PostgreSQL** para análisis y dashboard.

---

## 4. Kafka Producer

**Archivo:** `kafka/producer.py`

### 4.1. Responsabilidades

* Leer los 5 archivos crudos desde `data/`.

* Aplicar la misma lógica de ETL que el EDA/modelo (`src/etl.py`).

* Reconstruir el split 70/30 con la misma semilla utilizada en el entrenamiento.

* Agregar:

  * `is_train` = 1 si la fila pertenece al conjunto de entrenamiento; 0 en caso contrario.
  * `is_test` = 1 si la fila pertenece al conjunto de prueba; 0 en caso contrario.
  * `y_true` = `Happiness Score` original.

* Enviar **cada registro** como un mensaje JSON al topic:

```text
happiness_features
```

### 4.2. Ejemplo de mensaje enviado

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

### 4.3. Ejemplo de salida en consola

```text
[producer] using topic=happiness_features @ localhost:9092
[producer] sending records...

→ (France, 2018, y_true=6.489, train=1, test=0)
→ (Brazil, 2019, y_true=6.300, train=0, test=1)
→ (India, 2017, y_true=4.315, train=1, test=0)
...

[producer] done. sent=781 → topic=happiness_features @ localhost:9092
```

---

## 5. Kafka Consumer → PostgreSQL

**Archivo:** `kafka/consumer.py`

### 5.1. Responsabilidades

* Escuchar el topic `happiness_features`.
* Para cada mensaje:

  * Construir el vector de features con el mismo orden del entrenamiento.
  * Cargar el modelo `happiness_model.pkl`.
  * Calcular la predicción `y_pred`.
* Persistir la información en PostgreSQL en la tabla `predictions` usando **UPSERT**, evitando duplicados al reejecutar el flujo.

### 5.2. Esquema de la tabla `predictions`

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

### 5.3. Contenido

Cada fila en `predictions` contiene:

* **Datos originales**: `country`, `year`, `gdp`, `social`, `health`, `freedom`, `corrupt`
* **Etiquetas y banderas**:

  * `y_true`: felicidad real.
  * `is_train`: 1 si se usó para entrenar, 0 si no.
  * `is_test`: 1 si se usó para test, 0 si no.
* **Modelo**:

  * `y_pred`: predicción del modelo lineal.

### 5.4. Ejemplo de salida en consola

El consumer imprime un resumen amigable por registro, incluyendo si pertenece al set de entrenamiento o prueba y estadísticas acumuladas por país (R²/MAE rolling para revisión rápida):

```text
[consumer] ready
  • topic:      happiness_features
  • bootstrap:  localhost:9092
  • group_id:   workshop3-consumer
  • model:      model/happiness_model.pkl
  • postgres:   workshop@localhost:5432/workshop3
  • table:      predictions
--------------------------------------------------------------

┌──────────────────────────────────────────────────────────────┐
│ France (2018)                                               │
├──────────────────────────────────────────────────────────────┤
│R²: 0.812    MAE: 0.320                                      │
│y_true: 6.489    y_pred: 6.402                               │
│train: 1    test: 0                                          │
└──────────────────────────────────────────────────────────────┘

✓ upsert batch=200  total=200
✔ finished. total_upserted=781
```

---

## 6. Evaluación del Modelo a partir del Data Warehouse

Con la tabla `predictions` en PostgreSQL se pueden calcular los KPIs del modelo directamente (via SQL, Power BI u otra herramienta):

### 6.1. Ejemplos de KPIs recomendados

* **KPIs globales (solo test set):**

  * `R²_test`
  * `MAE_test`
  * `RMSE_test`

* **KPIs por año (solo test set):**

  * Métricas por `year` para analizar estabilidad temporal.
  * Detección de años con peor desempeño (posible drift o cambios estructurales).

* **Top errores (solo test set):**

  * Países con mayor `|y_true - y_pred|`.
  * Útil para discusión: regiones donde el modelo no captura bien la realidad.

Estos indicadores se calculan filtrando `is_test = 1` para asegurar que la evaluación del modelo se basa únicamente en datos no usados en el entrenamiento.

---

## 7. Limitaciones & Próximos Pasos

* El modelo actual es lineal: se pueden explorar alternativas:

  * Ridge/Lasso, Random Forest, Gradient Boosting, etc.
* Incluir nuevas variables:

  * Región, variables socioeconómicas adicionales, interacciones.
* Validaciones más robustas:

  * K-Fold, validación temporal, análisis de estabilidad.
* Monitoreo en producción:

  * Revisión periódica de KPIs por año/país.
  * Reentrenamiento cuando cambie la distribución de los datos.

---

Este documento resume el diseño técnico del pipeline:

**EDA → ETL unificado → Entrenamiento reproducible → Streaming con Kafka → Predicciones en PostgreSQL → Evaluación y visualización en Power BI.**