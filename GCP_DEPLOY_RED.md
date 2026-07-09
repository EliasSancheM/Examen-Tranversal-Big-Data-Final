# Guía de Despliegue en GCP — RED Santiago (Evaluación Parcial 3)

> Pipeline completo: **Batch** (CSV/JSON → GCS → BigQuery → Star Schema) + **Streaming** (API GPS en Cloud Run → GCS NDJSON → BigQuery → Looker Studio)

Esta guía adapta la arquitectura del `GCP_DEPLOY.md` (proyecto Valorant) a **nuestro trabajo de los buses RED**. Donde Valorant recibía *votos*, aquí recibimos **pings GPS de buses en tiempo real**.

---

## Mapa contra la rúbrica del Parcial 3

| Indicador de Logro | Cómo lo cubrimos | Sección |
|---|---|---|
| **IL 3.1** — Ingesta en línea con APIs | API propia en **Cloud Run** que recibe pings GPS vía HTTP POST en vivo | 10–13 |
| **IL 3.2** — Limpieza/transformación/almacenamiento streaming (4 aspectos) | **Normalización + Validación/Limpieza/Deduplicación + Enriquecimiento + Agregación** en línea | 10, 11, 14 |
| **IL 3.3** — Panel de control | Looker Studio sobre la vista `analytics_congestion_stream` con auto-refresh | 16 |
| Control de errores / duplicados / registro | `try/except`, anti-duplicado por minuto, `api_log`, vistas DQ | 10, 11, 17 |

---

## 0. Requisitos previos

- `gcloud` instalado y autenticado (o usar **Cloud Shell** de Google Skills Boost).
- Proyecto GCP con facturación habilitada.
- APIs habilitadas: `run.googleapis.com`, `cloudbuild.googleapis.com`, `bigquery.googleapis.com`, `storage.googleapis.com`.

---

## 1. Subir archivos a Cloud Shell

Desde **⋮ → Upload** en Cloud Shell, subir:

- **Streaming:** `api_red.py`, `Dockerfile`, `requirements.txt`, `setup_bq_red.sql`, `demo_stream_red.sh`
- **Batch (ya existente):** `historial_rutas_DTPM.csv`, `clima_santiago.json`

---

## 2. Configurar variables de entorno

```bash
# Reemplaza con tu Project ID real del lab
PROJECT_ID="$(gcloud config get-value project)"
REGION="us-west1"
BUCKET_NAME="buses_red_2026"

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

---

## 3. Crear bucket de Cloud Storage (Data Lake)

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" \
  --location="$REGION" \
  --uniform-bucket-level-access

# Estructura del Data Lake
echo "" | gcloud storage cp - "gs://$BUCKET_NAME/raw/.keep"
echo "" | gcloud storage cp - "gs://$BUCKET_NAME/streaming/posiciones/.keep"
```

---

## 4. (Batch) Cargar el histórico — base ya construida en el Parcial 2

> Esto es el pipeline batch del Parcial 2. Resumen para tener el dataset listo; el detalle completo está en `README_GCP.md`.

```bash
# Subir fuentes batch
gcloud storage cp historial_rutas_DTPM.csv gs://$BUCKET_NAME/raw/
gcloud storage cp clima_santiago.json      gs://$BUCKET_NAME/raw/

# Clima JSON -> NDJSON
gcloud storage cp gs://$BUCKET_NAME/raw/clima_santiago.json ./clima_santiago.json
jq -c '.[]' clima_santiago.json > clima_ndjson.json
gcloud storage cp clima_ndjson.json gs://$BUCKET_NAME/raw/

# Dataset + carga raw
bq mk --dataset --location="$REGION" red_santiago
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  red_santiago.gps_raw gs://$BUCKET_NAME/raw/historial_rutas_DTPM.csv
bq load --autodetect --source_format=NEWLINE_DELIMITED_JSON \
  red_santiago.clima_raw gs://$BUCKET_NAME/raw/clima_ndjson.json
```

El Star Schema (`dim_ruta`, `dim_bus`, `dim_fecha`, `dim_clima`, `fact_viajes`) y las tablas
`datos_enriquecidos` / `datos_agregados` se crean igual que en `README_GCP.md` (pasos 7–13).

> **Control de duplicidad entre batch y streaming:** la capa batch escribe en `gps_raw`/`fact_viajes`; la streaming escribe en `posiciones_stream`. Son tablas separadas, así que el streaming **no duplica** lo del batch. El dashboard final puede unirlas con `UNION ALL` si se desea una vista histórica + vivo.

---

## 5. (Streaming) Crear tablas y vistas en BigQuery

```bash
cat setup_bq_red.sql | bq query --nouse_legacy_sql
```

Esto crea:

| Objeto | Propósito |
|---|---|
| `posiciones_stream` | Tabla destino del streaming insert (ya normalizada + enriquecida) |
| `api_log` | Registro de actividad de la API (trazabilidad) |
| `analytics_congestion_stream` | Vista de **agregación** en vivo (ruta × hora × congestión) |
| `v_dq_duplicados` | DQ: mismo bus/ruta/minuto |
| `v_dq_velocidad_anomala` | DQ: velocidades fuera de rango |
| `v_dq_fuera_santiago` | DQ: coordenadas fuera del bounding box |

---

## 6. Habilitar servicios de Cloud Run

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

---

## 7. Buildear la imagen Docker de la API

```bash
gcloud builds submit --tag "gcr.io/$PROJECT_ID/red-gps-api"
```

---

## 8. Desplegar la API en Cloud Run

```bash
gcloud run deploy red-gps-api \
  --image "gcr.io/$PROJECT_ID/red-gps-api" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=$PROJECT_ID,BQ_DATASET=red_santiago,GCS_BUCKET=$BUCKET_NAME,AUTO_INTERVAL=2,BUSES_POR_TICK=20" \
  --min-instances 1 \
  --timeout 300
```

---

## 9. Obtener la URL de la API

```bash
API_URL=$(gcloud run services describe red-gps-api \
  --region "$REGION" --format="value(status.url)")
echo "API URL: $API_URL"
```

---

## 10. Probar la ingesta en línea (IL 3.1 + IL 3.2)

### 10.1 Ping válido

```bash
curl -s -X POST "$API_URL/api/posicion" \
  -H "Content-Type: application/json" \
  -d '{"bus_id":"BUS_1040","ruta":"502c","velocidad_kmh":12,"latitud":-33.45,"longitud":-70.66}' \
  | python3 -m json.tool
```

> Observa en la respuesta cómo la API **normaliza** `502c → 502C`, **enriquece** con `hora`, `dia_semana`, `nivel_congestion = Congestionado` y `clima_*`, y genera un `viaje_id`.

### 10.2 Ping inválido (validación/limpieza en vivo)

```bash
# Velocidad fuera de rango -> rechazado 422
curl -s -X POST "$API_URL/api/posicion" \
  -H "Content-Type: application/json" \
  -d '{"bus_id":"BUS_999","ruta":"104","velocidad_kmh":999,"latitud":-33.45,"longitud":-70.66}'
```

### 10.3 Ping duplicado (deduplicación en vivo)

```bash
# Enviar dos veces el mismo bus en el mismo minuto -> el segundo se rechaza
for n in 1 2; do
  curl -s -X POST "$API_URL/api/posicion" \
    -H "Content-Type: application/json" \
    -d '{"bus_id":"BUS_1001","ruta":"210","velocidad_kmh":40,"latitud":-33.44,"longitud":-70.65}'
  echo
done
```

---

## 11. Los 4 aspectos del IL 3.2 (dónde están en el código)

Todos se ejecutan **en línea**, por cada ping, en `api_red.py`:

| Aspecto | Función | Qué hace |
|---|---|---|
| **Normalización** | `normalizar()` | `ruta` a forma canónica (`502c→502C`), `bus_id` en mayúsculas, velocidad redondeada |
| **Validación + limpieza** | `validar()` | rango de velocidad `0–120`, coordenadas dentro de Santiago; rechaza con `422` |
| **Deduplicación** | `es_duplicado()` | un bus no puede tener 2 pings en el mismo minuto |
| **Enriquecimiento** | `enriquecer()` | agrega `hora`, `dia_semana`, `nivel_congestion`, `clima_*` |
| **Agregación** | vista SQL | `analytics_congestion_stream` agrega por ruta/hora/congestión |

---

## 12. Activar el generador automático (tráfico continuo)

```bash
# Inicia buses simulados reportando posiciones cada 2 s
curl -s -X POST "$API_URL/api/auto/start" | python3 -m json.tool

# Detener cuando quieras
# curl -s -X POST "$API_URL/api/auto/stop"
```

---

## 13. Demo de tráfico pesado para el video / defensa

```bash
chmod +x demo_stream_red.sh
./demo_stream_red.sh "$API_URL"
```

Mientras corre, revisa las métricas y el resumen en vivo:

```bash
curl -s "$API_URL/api/metricas" | python3 -m json.tool
curl -s "$API_URL/api/congestion/resumen" | python3 -m json.tool
curl -s "$API_URL/api/posiciones/recientes" | python3 -m json.tool
```

---

## 14. Verificar el almacenamiento en streaming

```bash
# BigQuery: filas que van llegando en vivo
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS pings, COUNT(DISTINCT bus_id) AS buses
   FROM red_santiago.posiciones_stream;"

# Agregación por nivel de congestión
bq query --use_legacy_sql=false \
  "SELECT nivel_congestion, COUNT(*) AS pings, ROUND(AVG(velocidad_kmh),1) AS vel
   FROM red_santiago.posiciones_stream
   GROUP BY nivel_congestion ORDER BY pings DESC;"

# Data Lake: archivos NDJSON escritos por la API
gcloud storage ls "gs://$BUCKET_NAME/streaming/posiciones/**" | head
```

---

## 15. Control de calidad y registro (control de errores/duplicados)

```bash
# Duplicados detectados
bq query --use_legacy_sql=false "SELECT * FROM red_santiago.v_dq_duplicados LIMIT 20;"

# Anomalías que se hubieran colado
bq query --use_legacy_sql=false "SELECT COUNT(*) FROM red_santiago.v_dq_velocidad_anomala;"

# Log de actividad de la API (trazabilidad)
bq query --use_legacy_sql=false \
  "SELECT event_type, status, description, created_at
   FROM red_santiago.api_log
   ORDER BY created_at DESC LIMIT 20;"
```

---

## 16. Dashboard en Looker Studio (IL 3.3)

1. Abrir [lookerstudio.google.com](https://lookerstudio.google.com) → **Crear → Informe en blanco**.
2. **Agregar datos → BigQuery →** `$PROJECT_ID` → `red_santiago` → `analytics_congestion_stream`.
3. Gráficos recomendados (streaming en vivo):

| Gráfico | Dimensión | Métrica |
|---|---|---|
| Congestión por ruta | `ruta` (desglose por `nivel_congestion`) | `total_pings` (SUM) |
| Velocidad promedio por hora | `hora` | `velocidad_promedio` (AVG) |
| Buses activos por ruta | `ruta` | `buses_unicos` (SUM) |
| Impacto del clima | `clima_condicion` | `velocidad_promedio` (AVG) |
| Mapa de pings | `latitud`,`longitud` (desde `posiciones_stream`) | conteo |

4. Para refresco automático: agregar `?refresh=15` a la URL del informe.

**Nombre sugerido:** `RED Santiago — Congestión del Transporte Público en Tiempo Real`

---

## 17. Monitoreo y logs

```bash
# Logs del servicio Cloud Run
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=red-gps-api" \
  --limit 20
```

---

## 18. Cleanup (si es necesario)

```bash
gcloud run services delete red-gps-api --region "$REGION"
gcloud container images delete "gcr.io/$PROJECT_ID/red-gps-api" --quiet
bq rm -r -f red_santiago
gcloud storage rm -r "gs://$BUCKET_NAME"
```

---

## Prueba local rápida (opcional, sin GCP)

```bash
pip install -r requirements.txt
python api_red.py            # arranca en http://localhost:8080
# en otra terminal:
curl -s -X POST localhost:8080/api/posicion \
  -H "Content-Type: application/json" \
  -d '{"bus_id":"BUS_1","ruta":"502c","velocidad_kmh":12,"latitud":-33.45,"longitud":-70.66}'
```

Sin variables GCP, la API funciona en modo memoria (no escribe a GCS/BigQuery) para
que puedas validar la lógica de los 4 aspectos antes de desplegar.
