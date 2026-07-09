# Guía GCP — Examen Final Transversal (BIY7131) · Buses RED

> **Batch + Streaming ejecutándose al mismo tiempo**, sobre el mismo Data Lake (Cloud Storage) y el mismo dataset de BigQuery (`red_santiago`).
> Contexto: **Red Metropolitana de Movilidad (buses RED de Santiago)** — congestión del transporte público.

---

## 0. Mapa contra la rúbrica del examen

| Indicador | Cómo se cubre | Dónde |
|---|---|---|
| IL 1.1–1.4 (concepto, herramientas, gobierno, arquitectura) | Informe: justificación Big Data + arquitectura GCP + gobierno/ciclo de vida | Informe secciones 1–2 |
| **IL 2.1** Carga **Batch** diversas fuentes/formatos | GPS histórico **CSV** + clima **JSON** → GCS → BigQuery | `gcp_pipeline.py` |
| **IL 2.3** Limpieza/transformación **Batch** | dedup, validación, normalización, enriquecimiento, agregación (SQL) | `gcp_pipeline.py` paso 3 |
| **IL 3.2** Limpieza/transformación **Streaming** | 4 aspectos en línea por cada ping GPS | `api_red.py` |
| **IL 3.3** Panel de control | Looker Studio (batch + streaming) | Looker |
| Anexo a–d (errores, duplicidad, registro, validación) | try/except, dedup, `proceso/api_log`, métricas de calidad | ambos |

**Ejecución en paralelo:** el streaming corre como servicio **siempre activo** (Cloud Run) mientras se lanza el **batch** con el orquestador. Los dos escriben en `red_santiago` a la vez.

---

## 1. Archivos que debes subir a Cloud Shell

| Archivo | Proceso | Rol |
|---|---|---|
| `historial_rutas_DTPM.csv` | Batch | Fuente 1: GPS histórico de buses (CSV) |
| `clima_santiago.json` | Batch | Fuente 2: clima (JSON) |
| `config.py` | Batch | Parámetros de validación |
| `gcp_config.py` | Batch | **Ajustar PROJECT_ID / BUCKET_NAME** |
| `gcp_pipeline.py` | Batch | Pipeline ETL batch |
| `api_red.py` | Streaming | API de ingesta GPS en vivo (Cloud Run) |
| `Dockerfile` | Streaming | Imagen de la API |
| `requirements.txt` | Streaming | Dependencias |
| `setup_bq_red.sql` | Streaming | Tablas + vistas streaming en BigQuery |
| `orquestador.py` | Ambos | Lanza batch + streaming en paralelo |

Súbelos con **⋮ → Upload** y verifica: `ls -1`

---

## 2. Estructura del Data Lake (lo que queda en el bucket)

```
gs://buses_red_2026/
├── datalake/raw/                 ← BATCH: datos crudos
│   ├── historial_rutas_DTPM.csv
│   └── clima_santiago.json
├── datalake/curated/             ← BATCH: capa de consumo (limpia)
│   ├── datos_enriquecidos.csv
│   └── datos_agregados.csv
└── streaming/posiciones/         ← STREAMING: pings GPS en NDJSON
    └── YYYYMMDD/<viaje_id>.json
```

El batch lo crea `gcp_pipeline.py`; la carpeta `streaming/` la escribe `api_red.py` en vivo.

---

## 3. Configurar variables

```bash
PROJECT_ID="$(gcloud config get-value project)"
REGION="europe-west1"
BUCKET_NAME="buses_red_2026"
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

Edita `gcp_config.py` y pon tu `PROJECT_ID` y `BUCKET_NAME` (o expórtalos como variables antes de correr el batch).

---

## 4. Habilitar servicios

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  bigquery.googleapis.com storage.googleapis.com
```

---

## 5. Crear Data Lake y dataset

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" --location="$REGION" \
  --uniform-bucket-level-access

bq mk --dataset --location="$REGION" red_santiago
```

---

## 6. Preparar BigQuery para streaming + log compartido

```bash
# Tablas y vistas de streaming
cat setup_bq_red.sql | bq query --nouse_legacy_sql

# Tabla de log compartida batch+streaming (registro de actividad / calidad)
bq query --use_legacy_sql=false '
CREATE TABLE IF NOT EXISTS red_santiago.proceso_log (
  proceso STRING, tipo STRING, evento STRING, estado STRING,
  registros_leidos INT64, registros_cargados INT64, nulos INT64,
  mensaje STRING, timestamp TIMESTAMP
);'
```

---

## 7. Desplegar la API de streaming (queda SIEMPRE activa)

```bash
gcloud builds submit --tag "gcr.io/$PROJECT_ID/red-gps-api"

gcloud run deploy red-gps-api \
  --image "gcr.io/$PROJECT_ID/red-gps-api" --platform managed --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=$PROJECT_ID,BQ_DATASET=red_santiago,GCS_BUCKET=$BUCKET_NAME,AUTO_INTERVAL=2,BUSES_POR_TICK=20" \
  --min-instances 1 --timeout 300

API_URL=$(gcloud run services describe red-gps-api --region "$REGION" --format="value(status.url)")
echo "$API_URL"
```

---

## 8. ▶ Ejecutar BATCH y STREAMING al mismo tiempo

```bash
python orquestador.py "$API_URL"
```

Esto arranca dos hilos concurrentes:
- **BATCH**: `gcp_pipeline.py` ingesta el CSV + JSON, limpia y agrega en BigQuery.
- **STREAMING**: enciende el generador de la API (pings GPS en vivo) y muestra métricas cada 10 s.

Mientras corre, en **otra pestaña** verifica que AMBOS llenan el dataset a la vez:

```bash
# Streaming (crece en tiempo real)
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM red_santiago.posiciones_stream;"
# Batch (tablas del histórico)
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM red_santiago.datos_enriquecidos;"
```

---

## 9. Métricas de calidad (Anexo d — rúbrica)

**Streaming** — rechazos por validación y duplicados quedan en `api_log`:
```bash
bq query --use_legacy_sql=false "
SELECT event_type, status, description, created_at
FROM red_santiago.api_log ORDER BY created_at DESC LIMIT 20;"
```

**Batch** — `gcp_pipeline.py` imprime en consola y guarda en `estado_ejecuciones_gcp.json`
las métricas de calidad del paso 3 (total registros, velocidades inválidas, duplicados,
coordenadas fuera de rango) y las estadísticas post-limpieza (registros finales = cargados).
Para dejar esas métricas persistidas en BigQuery, ejecuta este snapshot (leídos vs cargados + nulos):

```bash
bq query --use_legacy_sql=false "
INSERT INTO red_santiago.proceso_log
SELECT 'batch_gps','BATCH','calidad','EXITOSO',
  (SELECT COUNT(*) FROM red_santiago.gps_raw)          AS registros_leidos,
  (SELECT COUNT(*) FROM red_santiago.datos_enriquecidos) AS registros_cargados,
  (SELECT COUNTIF(Velocidad_kmh IS NULL) + COUNTIF(Latitud IS NULL)
   FROM red_santiago.gps_raw)                          AS nulos,
  'leidos vs cargados + nulos', CURRENT_TIMESTAMP();"
```

---

## 10. Controles obligatorios (Anexo del informe)

| Control | Batch | Streaming |
|---|---|---|
| **a) Errores** | `try/except` por paso, log FALLIDO | `try/except` en GCS/BigQuery, API no se cae |
| **b) Duplicidad** | `SELECT DISTINCT` + tabla `registros_invalidos` | dedup `bus_id\|minuto`, política SKIP |
| **c) Registro/ciclo de vida** | `estado_ejecuciones_gcp.json` + `proceso_log` + capas raw→curated | `api_log` + raw NDJSON→tabla |
| **d) Validación/calidad** | rangos velocidad/coords, leídos vs cargados, nulos | validación en línea + vistas `v_dq_*` |

---

## 11. Dashboard (IL 3.3) — Looker Studio

Conectar dos fuentes del dataset `red_santiago`:
- **Batch:** `datos_agregados` (histórico por ruta/hora).
- **Streaming:** vista `analytics_congestion_stream` (en vivo).

Gráficos: congestión por ruta, velocidad por hora, distribución de congestión, mapa de posiciones, impacto del clima. Auto-refresh 1 min.

---

## 12. Limpieza

```bash
gcloud run services delete red-gps-api --region "$REGION"
bq rm -r -f red_santiago
gcloud storage rm -r "gs://$BUCKET_NAME"
```
