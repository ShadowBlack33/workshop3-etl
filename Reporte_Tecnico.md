# Workshop 3 – End-to-End Architecture & Model Evaluation 📊

**Caso de uso:** Predicción y análisis del `Happiness Score` (World Happiness Report 2015–2019) usando un pipeline completo:

**ETL → EDA → Entrenamiento de modelo → Kafka Streaming → Consumer con modelo → Data Warehouse en PostgreSQL → Dashboard en Power BI**

Este documento describe en detalle:

- Los datasets utilizados.
- La lógica de ETL y el análisis exploratorio.
- El modelo seleccionado y cómo se entrena.
- La arquitectura de streaming con Kafka.
- La estructura del Data Warehouse (`predictions` en PostgreSQL).
- Cómo todo se integra para evaluación y visualización.

---

## 1. Tecnologías y herramientas ⚙️

Este proyecto está diseñado como un mini ecosistema de datos moderno:

- 🐍 **Python 3**  
  Lenguaje principal para ETL, entrenamiento, streaming y conexión a la base de datos.

- 📓 **Jupyter Notebooks**
  - `notebooks/EDA.ipynb`: análisis exploratorio de datos.
  - `notebooks/ModelTraining.ipynb`: experimentos con el modelo antes de consolidar en scripts.

- 🔁 **Apache Kafka**
  - Canal de streaming para enviar fila por fila los registros ya transformados.
  - Topic principal: `happiness_features`.

- 🐘 **PostgreSQL**
  - Se usa como **Data Warehouse**.
  - Guarda la tabla final `predictions` con:
    - Features
    - Valor real (`y_true`)
    - Predicción (`y_pred`)
    - Flags de si fue train/test

- 🐳 **Docker / docker-compose**
  - Orquesta servicios de:
    - Kafka
    - Zookeeper
    - PostgreSQL

- 🧩 **Visual Studio Code**
  - Editor principal del proyecto.
  - Extensiones clave:
    - Python
    - Jupyter
    - SQLTools + SQLTools PostgreSQL Driver (para inspeccionar la base desde VS Code).

- 📊 **Power BI Desktop**
  - Herramienta de visualización para construir el dashboard final consumiendo directamente de PostgreSQL.

- 📦 **scikit-learn**
  - Librería usada para entrenar el modelo de regresión lineal.

---

## 2. Estructura del repositorio 📁

La estructura está pensada para separar claramente responsabilidades:

```text
.
├─ data/
│  ├─ 2015.csv
│  ├─ 2016.csv
│  ├─ 2017.csv
│  ├─ 2018.csv
│  └─ 2019.csv
│     # Archivos originales del World Happiness Report.
│
├─ db/
│  └─ pgdata/
│     # Volumen de datos de PostgreSQL (montado por Docker).
│
├─ docs/
│  ├─ REPORT.md
│     # Este documento técnico.
│
├─ kafka/
│  ├─ producer.py
│  │   # Lee los CSV, aplica ETL, marca train/test, envía registros a Kafka.
│  └─ consumer.py
│      # Lee desde Kafka, aplica modelo, guarda en PostgreSQL (tabla predictions).
│
├─ model/
│  └─ happiness_model.pkl
│     # Modelo entrenado (LinearRegression) serializado.
│
├─ notebooks/
│  ├─ EDA.ipynb
│  │   # Exploración, unificación de columnas, análisis estadístico y visualizaciones.
│  └─ ModelTraining.ipynb
│      # Pruebas de modelos, comparación, soporte para definir la versión final.
│
├─ src/
│  ├─ __init__.py
│  ├─ etl.py
│  │   # Funciones reutilizables:
│  │   #   - Carga y limpieza de los 5 CSV.
│  │   #   - Normalización de columnas.
│  │   #   - Construcción del dataset unificado.
│  ├─ train_model.py
│  │   # Script de entrenamiento final:
│  │   #   - Usa etl.load_unified()
│  │   #   - Aplica split 70/30
│  │   #   - Entrena LinearRegression
│  │   #   - Calcula métricas
│  │   #   - Guarda happiness_model.pkl
│  └─ evaluate.py (opcional)
│      # Helpers para cálculo de métricas fuera de línea (si se requiere).
│
├─ docker-compose.yml
│   # Define servicios de Kafka, Zookeeper y PostgreSQL.
│
├─ requirements.txt
│   # Dependencias del entorno Python.
│
├─ .env
│   # Configuración de conexión (Kafka, Postgres, etc.).
│
└─ README.md
    # Guía rápida de uso del proyecto.
````

---

## 3. Diseño de datos y ETL 🧹

### 3.1. Problema inicial

Los archivos de 2015–2019 no tienen el mismo esquema:

* Cambian nombres de columnas.
* Algunas columnas existen solo en ciertos años.
* Hay variaciones en cómo se llama al país, score, etc.

Ejemplos:

* `Country` vs `Country or region`
* `Happiness Score` vs `Score`
* `Economy (GDP per Capita)` vs `GDP per capita`
* `Health (Life Expectancy)` vs `Healthy life expectancy`
* `Trust (Government Corruption)` vs `Perceptions of corruption`

### 3.2. Solución en `src/etl.py`

`etl.py` concentra TODA la lógica de limpieza.
Esto es clave porque:

* El **EDA**, el **entrenamiento** y el **producer** usan exactamente la misma lógica.
* Evita “trampa” de usar datasets distintos en training vs producción.

Pasos principales del ETL:

1. **Lectura por año**:

   * Para cada archivo (`2015.csv`…`2019.csv`) se aplica un mapeo específico a nombres estándar.

2. **Estandarización de columnas clave**:

   * Se construye un esquema común con las columnas:

     ```text
     Country
     Year
     Happiness Score
     GDP per capita
     Social support
     Healthy life expectancy
     Freedom
     Perceptions of corruption
     ```

3. **Tipos de datos**:

   * Conversión a `float` para features numéricas.
   * Conversión de `Year` a entero.
   * Filtrado de filas con nulos en las columnas clave (para el modelo).

4. **Dataset final**:

   * Se genera un DataFrame unificado `df_all` que combina 2015–2019 con esquema consistente.
   * Este es la base para:

     * EDA
     * Entrenamiento
     * Streaming

### 3.3. EDA (`notebooks/EDA.ipynb`)

Dentro del notebook se hace:

* Descriptivos generales (media, min, max, etc.).
* Distribuciones por feature.
* Correlación entre:

  * `Happiness Score` y cada feature.
* Comparación por años para ver estabilidad del comportamiento.

**Decisión importante:**

* No se implementa winsorización ni tratamiento fuerte de outliers en el pipeline final.
* Se analizan outliers en el EDA (para entenderlos), pero no se alteran los datos productivos:

  * Esto mantiene interpretabilidad.
  * Evita modificar artificialmente regiones extremas.

---

## 4. Entrenamiento del modelo 🎯

### 4.1. Script: `src/train_model.py`

Responsabilidades:

1. Llama a `load_unified()` de `etl.py`.

2. Selecciona solo columnas completas en `FEATURES + TARGET`.

3. Define:

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

4. Aplica `train_test_split`:

   * `test_size=0.30`
   * `random_state=42` (misma semilla usada luego en el producer para marcar train/test).

5. Entrena `LinearRegression`.

6. Calcula métricas en el **test set** (solo test, nada de mezclar train):

   * R²
   * MAE
   * RMSE

7. Muestra resultados en consola con formato claro.

8. Guarda el modelo entrenado en:

   ```text
   model/happiness_model.pkl
   ```

### 4.2. Justificación del modelo

* La relación entre las variables seleccionadas y `Happiness Score` es casi lineal o monótona.
* Linear Regression:

  * Es interpretable.
  * Permite ver el peso de cada feature.
  * Es suficiente para el alcance del workshop.

---

## 5. Arquitectura de Streaming ☁️

Aquí conectamos todo: ETL + modelo + Kafka + Postgres.

### 5.1. Diagrama general (High-level)

```mermaid
flowchart LR
  subgraph RAW[CSV: 2015–2019]
    A2015[2015.csv]
    A2016[2016.csv]
    A2017[2017.csv]
    A2018[2018.csv]
    A2019[2019.csv]
  end

  RAW --> B[ETL unificado<br/>(src/etl.py)]
  B --> C[Entrenamiento<br/>(src/train_model.py)]
  C --> M[Modelo .pkl<br/>(happiness_model.pkl)]

  B --> P[Producer<br/>(kafka/producer.py)]
  M -. usado por .-> CO[Consumer<br/>(kafka/consumer.py)]

  P -- mensajes JSON --> K[(Kafka<br/>topic: happiness_features)]
  K --> CO
  CO --> DW[(PostgreSQL<br/>tabla: predictions)]

  DW --> BI[Power BI<br/>Dashboard]
```

---

## 6. Producer – `kafka/producer.py` 📤

### 6.1. Rol

El producer **simula** el flujo de datos hacia Kafka, pero respetando el mismo pipeline lógico que usamos para entrenar.

Pasos:

1. Llama `load_unified()` para construir el dataset limpio.
2. Repite internamente el `train_test_split` con la misma semilla (42) para saber:

   * Qué filas son **train**.
   * Qué filas son **test**.
3. Crea las columnas:

   * `is_train` (1/0)
   * `is_test` (1/0)
   * `y_true` (`Happiness Score` original).
4. Construye un JSON por fila con:

   * Identidad: `Country`, `Year`
   * Features: `GDP per capita`, `Social support`, `Healthy life expectancy`, `Freedom`, `Perceptions of corruption`
   * Metadata: `y_true`, `is_train`, `is_test`
5. Envía cada mensaje al topic `happiness_features`.

### 6.2. Output esperado (ejemplo)

```text
[producer] using topic=happiness_features @ localhost:9092
[producer] sending records...

→ (France, 2018, y_true=6.489, train=1, test=0)
→ (Brazil, 2019, y_true=6.300, train=0, test=1)
→ (India, 2017, y_true=4.315, train=1, test=0)
...

[producer] done. sent=781 → topic=happiness_features @ localhost:9092
```

Puntos clave:

* No lee un dataset “ya unido” externo: él mismo ejecuta el ETL.
* Respeta el split original para que el análisis en el DW sea coherente.

---

## 7. Consumer – `kafka/consumer.py` 📥

### 7.1. Rol

El consumer es quien convierte el stream en algo útil:

1. Escucha el topic `happiness_features`.
2. Por cada mensaje:

   * Extrae las features.
   * Carga el modelo `happiness_model.pkl` (al inicio).
   * Calcula `y_pred` usando las mismas columnas que en el entrenamiento.
3. Inserta el registro en PostgreSQL en la tabla `predictions` usando:

   * `INSERT ... ON CONFLICT ... DO UPDATE`
     (para no duplicar cuando se reenvían los mismos datos).

### 7.2. Esquema de la tabla `predictions` en PostgreSQL

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

* La clave única garantiza:

  * Si se vuelve a correr el pipeline, no se duplican filas.
  * Cada combinación país-año-split aparece una sola vez.

### 7.3. Lógica interna resumida

* Deserializa el JSON del mensaje.
* Ordena las features correctamente.
* `model.predict(X)` → `y_pred`.
* Construye un `INSERT` con UPSERT.
* Muestra en consola un resumen legible (país, año, flags, valores).

Ejemplo de log:

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
│y_true: 6.489    y_pred: 6.402                               │
│train: 1    test: 0                                          │
└──────────────────────────────────────────────────────────────┘
...
✔ finished. total_upserted=781
```

---

## 8. Evaluación del modelo desde el Data Warehouse 📈

Con todo en `predictions`, podemos evaluar el modelo **directamente en PostgreSQL** o desde Power BI filtrando:

* **Entrenamiento:** `is_train = 1`
* **Prueba:** `is_test = 1`

### 8.1. Ejemplos de consultas SQL (lado servidor)

**Métricas globales en test:**

```sql
SELECT
    COUNT(*)                           AS n,
    AVG(ABS(y_true - y_pred))          AS mae,
    SQRT(AVG(POWER(y_true - y_pred,2))) AS rmse
FROM predictions
WHERE is_test = 1;
```

**R² global en test:**

```sql
WITH stats AS (
    SELECT
        AVG(y_true) AS y_mean
    FROM predictions
    WHERE is_test = 1
),
errs AS (
    SELECT
        (y_true - y_pred)               AS err,
        (y_true - (SELECT y_mean FROM stats)) AS dev
    FROM predictions
    WHERE is_test = 1
)
SELECT
    1 - SUM(POWER(err,2)) / NULLIF(SUM(POWER(dev,2)),0) AS r2
FROM errs;
```

**KPIs por año (solo test):**

```sql
WITH base AS (
    SELECT
        year,
        y_true,
        y_pred
    FROM predictions
    WHERE is_test = 1
)
SELECT
    year,
    COUNT(*)                                 AS n,
    AVG(ABS(y_true - y_pred))                AS mae,
    SQRT(AVG(POWER(y_true - y_pred,2)))      AS rmse
FROM base
GROUP BY year
ORDER BY year;
```

**Top 10 errores (solo test):**

```sql
SELECT
    country,
    year,
    y_true,
    y_pred,
    ABS(y_true - y_pred) AS abs_error
FROM predictions
WHERE is_test = 1
ORDER BY abs_error DESC
LIMIT 10;
```

Estos resultados alimentan directamente el análisis y el dashboard.

---

## 9. Dashboard (Power BI) – Vista conceptual 🎨

El dashboard se construye sobre la tabla `predictions` en PostgreSQL.

### Página 1 – Entrenamiento & Datos

* Card: `Total registros`
* Card: `Registros train`
* Card: `Registros test`
* Bar chart:

  * Eje X: `year`
  * Valores: cantidad train/test
* Scatter:

  * X: `GDP per capita`
  * Y: `y_true`
  * Filtro: `is_train = 1`
  * Objetivo: mostrar con qué datos se entrenó el modelo.

### Página 2 – Performance del Modelo (Test)

* Cards:

  * `R² test`, `MAE test`, `RMSE test`
* Scatter:

  * X: `y_pred`
  * Y: `y_true`
  * Filtro: `is_test = 1`
  * Para ver qué tan cerca estamos de la diagonal perfecta.
* Tabla o bar chart:

  * Top países con mayor error absoluto (solo test).

Con esto el profesor ve:

* Que el modelo se entrenó correctamente.
* Que la evaluación usa únicamente datos de prueba.
* Que la arquitectura conecta todo: CSV → ETL → Modelo → Kafka → Postgres → BI.

---

## 10. Conclusiones ✅

* Se implementó un flujo **consistente y reproducible**:

  * Misma lógica de ETL para EDA, entrenamiento y streaming.
  * Modelo simple pero interpretable.
  * Separación clara entre datos de entrenamiento y prueba mediante flags en el DW.
* Kafka y PostgreSQL permiten simular un escenario real:

  * Streaming de datos.
  * Aplicación de modelo en línea.
  * Persistencia centralizada.
* El Data Warehouse expone una sola tabla (`predictions`) desde la cual:

  * Se pueden calcular KPIs del modelo.
  * Se construyen dashboards limpios y defendibles.

Este documento sirve como respaldo técnico del proyecto para revisión académica o profesional.