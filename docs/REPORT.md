# Workshop 3 – Model Evaluation & Reporting

**Dataset:** World Happiness (2015–2019).  
**Streaming:** Kafka → Consumer → SQLite (`db/predictions.db`) con *views* para KPIs.  
**Modelo:** Linear Regression (train 70% / test 30%), features seleccionadas:
- GDP per capita
- Social support
- Healthy life expectancy
- Freedom
- Perceptions of corruption
- (Generosity solo como contexto/EDA)

---

## 1. EDA (resumen breve)
- Unificación de columnas por año (estandarización de nombres).
- Conversión a numérico y manejo de valores faltantes.
- **Outliers:** inspección de distribuciones; winsorización leve (p1–p99) durante EDA para comparar robustez (sin alterar los CSV originales de entrenamiento).
- Correlaciones: las 5 features anteriores muestran relación con la variable objetivo (*Happiness Score*), especialmente GDP, Social support y Life expectancy.

> Nota: El EDA completo está en el notebook del proyecto.

---

## 2. Entrenamiento
- Split: **70% train / 30% test** (random_state=42).
- Modelo: **Linear Regression**.
- Guardado: `model/happiness_model.pkl`.
- Producer/Consumer: consumen/guardan registros con predicción en `predictions` (SQLite) y calculan *views* de KPIs.

---

## 3. Evaluación – KPIs globales (SQLite view: `kpis_globales`)
| n | mae | rmse | r2 |
| --- | --- | --- | --- |
| 3105 | 0.515 | 0.665 | 0.645 |

- **Interpretación:** Con **MAE=0.515** y **RMSE=0.665**, el error medio y la raíz del error cuadrático medio son moderados.  
  El **R²=0.645** indica la proporción de varianza explicada por el modelo (más cerca a 1, mejor).

---

## 4. Evaluación por año (SQLite view: `kpis_por_anio`)
| year | n | mae | rmse | r2 |
| --- | --- | --- | --- | --- |
| 2015 | 649 | 0.420 | 0.536 | 0.724 |
| 2016 | 636 | 0.551 | 0.685 | 0.618 |
| 2017 | 609 | 0.726 | 0.899 | 0.337 |
| 2018 | 615 | 0.441 | 0.576 | 0.746 |
| 2019 | 596 | 0.442 | 0.567 | 0.771 |

- **Lectura:** Permite ver si el desempeño mejora o empeora en ciertos años. Útil para detectar *drift* temporal o cambios de distribución.

---

## 5. Errores más altos
### 5.1 Vista resumida (SQLite view: `top10_peores_errores`)
| country | year | abs_error | actual_happiness | predicted_happiness |
| --- | --- | --- | --- | --- |
| Rwanda | 2017 | 2.196 | 3.471 | 5.667 |
| Botswana | 2018 | 2.164 | 3.590 | 5.754 |
| Tanzania | 2017 | 2.065 | 3.349 | 5.414 |
| Botswana | 2017 | 1.992 | 3.766 | 5.758 |
| Rwanda | 2019 | 1.847 | 3.334 | 5.181 |
| Cambodia | 2017 | 1.697 | 4.168 | 5.865 |
| Liberia | 2017 | 1.665 | 3.533 | 5.198 |
| Syria | 2015 | 1.515 | 3.006 | 4.521 |
| Israel | 2016 | 1.511 | 7.267 | 5.910 |
| Tanzania | 2018 | 1.498 | 3.303 | 4.801 |

### 5.2 Detalle (Top 15 por `abs_error` desde `predictions_enriched`)
| country | year | actual_happiness | predicted_happiness | abs_error |
| --- | --- | --- | --- | --- |
| Rwanda | 2017 | 3.471 | 5.667 | 2.196 |
| Rwanda | 2017 | 3.471 | 5.667 | 2.196 |
| Rwanda | 2017 | 3.471 | 5.667 | 2.196 |
| Rwanda | 2017 | 3.471 | 5.667 | 2.196 |
| Rwanda | 2017 | 3.471 | 5.653 | 2.182 |
| Rwanda | 2017 | 3.471 | 5.653 | 2.182 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Rwanda | 2017 | 3.471 | 5.648 | 2.177 |
| Botswana | 2018 | 3.590 | 5.754 | 2.164 |

- **Lectura:** Países/años con error alto pueden indicar:
  - Regiones con dinámica distinta (no capturada por el modelo).
  - Falta de variables explicativas (ej. shocks específicos del año).
  - Necesidad de modelos con interacciones o no lineales.

---

## 6. Streaming & Persistencia
- **Flujo:** Producer → Kafka → Consumer → predicción con `.pkl` → inserción en `predictions` (SQLite) → *views* para KPIs:
  - `predictions_enriched`, `kpis_globales`, `kpis_por_anio`, `top10_peores_errores`, `scatter_ready`.
- **Ventajas:** Plataforma (Power BI/Tableau/Looker) puede leer directamente la DB o los CSV exportados.

---

## 7. Limitaciones & Próximos pasos
- Modelo lineal base: explorar **Regularized Linear** (Ridge/Lasso) o **Tree-based** (RandomForest/XGBoost).
- Feature engineering: interacciones y transformaciones (log GDP, escalado).
- Validación: **k-fold** con *time-aware split* si hay dependencia temporal.
- Data drift: monitorear métricas por año y reentrenar periódicamente.
- Dashboard: integrar páginas (Overview, Trends, Model Fit) con filtros `year/country`.

---

**Generado automáticamente** por `src/generate_report.py` a partir de SQLite/CSVs.
