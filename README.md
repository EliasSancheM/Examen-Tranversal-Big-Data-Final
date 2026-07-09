# Examen Transversal — Big Data · RED Santiago

Plataforma de datos **Batch + Streaming** sobre **Google Cloud Platform** para el análisis de
congestión del transporte público de Santiago (buses RED). Ambos procesos se ejecutan **en
paralelo** sobre el mismo Data Lake (Cloud Storage) y el mismo Data Warehouse (BigQuery), y se
sintetizan en un panel de control en Looker Studio.

- **Asignatura:** BIY7131 — Big Data · **Sección:** 006D
- **Integrantes:** Benjamín Pumarino · Elías Sánchez · Felipe Villanueva
- **Docente:** Matías Rojas

---

## Arquitectura (Lambda)

```
Buses GPS ── BATCH  ─▶ Cloud Storage (CSV+JSON) ─▶ BigQuery (raw) ─▶ limpieza/agregación
          └─ STREAM ─▶ API Cloud Run (/api/posicion) ─▶ GCS NDJSON + BigQuery (posiciones_stream)
                                      │
                                      ▼
                        Dataset red_santiago  ─▶  Looker Studio (dashboard)
```

| Capa | Servicio GCP | Componente |
|---|---|---|
| Batch | Cloud Storage + BigQuery | `gcp_pipeline.py` |
| Speed (streaming) | Cloud Run (Flask) | `api_red.py` |
| Serving | BigQuery + Looker Studio | vistas + dashboard |
| Orquestación | Python (hilos) | `orquestador.py` |

---

## Estructura del repositorio

| Archivo | Descripción |
|---|---|
| `historial_rutas_DTPM.csv` | Fuente batch — GPS de buses (CSV) |
| `clima_santiago.json` | Fuente batch — clima (JSON) |
| `config.py` / `gcp_config.py` | Parámetros de validación / configuración GCP |
| `gcp_pipeline.py` | Pipeline **batch** (ingesta → limpieza → agregación) |
| `api_red.py` | API **streaming** de ingesta GPS (Cloud Run) |
| `Dockerfile` / `requirements.txt` | Imagen y dependencias de la API |
| `setup_bq_red.sql` | Tablas y vistas de streaming en BigQuery |
| `orquestador.py` | Ejecuta **batch + streaming en paralelo** |
| `GCP_DEPLOY_EXAMEN.md` | Guía de despliegue detallada |
| `INFORME_EXAMEN_FINAL.docx` | Informe del examen (10 págs) |

---

## Orden de comandos para la ejecución (Cloud Shell)

> Requisitos: proyecto GCP con facturación y `gcloud` autenticado. Subir los archivos a Cloud Shell.

```bash
# 1. Variables de sesión
PROJECT_ID="$(gcloud config get-value project)"
REGION="europe-west1"
BUCKET_NAME="buses-red-examen-2024"
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

# 2. Habilitar servicios
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  bigquery.googleapis.com storage.googleapis.com

# 3. Crear el Data Lake (bucket)
gcloud storage buckets create "gs://$BUCKET_NAME" --location="$REGION" \
  --uniform-bucket-level-access

# 4. Crear el dataset en BigQuery
bq mk --dataset --location="$REGION" red_santiago

# 5. Crear tablas/vistas de streaming + tabla de log
cat setup_bq_red.sql | bq query --nouse_legacy_sql
bq query --use_legacy_sql=false '
CREATE TABLE IF NOT EXISTS red_santiago.proceso_log (
  proceso STRING, tipo STRING, evento STRING, estado STRING,
  registros_leidos INT64, registros_cargados INT64, nulos INT64,
  mensaje STRING, timestamp TIMESTAMP
);'

# 6. Configurar el batch (Project ID, región y bucket)
sed -i "s/TU_PROJECT_ID/$PROJECT_ID/g" gcp_config.py
sed -i "s/us-central1/$REGION/g" gcp_config.py
sed -i "s/^BUCKET_NAME.*/BUCKET_NAME = \"$BUCKET_NAME\"/" gcp_config.py

# 7. Construir la imagen Docker de la API
gcloud builds submit --tag "gcr.io/$PROJECT_ID/red-gps-api"

# 8. Desplegar la API en Cloud Run (queda siempre activa)
gcloud run deploy red-gps-api \
  --image "gcr.io/$PROJECT_ID/red-gps-api" --platform managed --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=$PROJECT_ID,BQ_DATASET=red_santiago,GCS_BUCKET=$BUCKET_NAME,AUTO_INTERVAL=2,BUSES_POR_TICK=20" \
  --min-instances 1 --timeout 300

# 9. Obtener la URL de la API
API_URL=$(gcloud run services describe red-gps-api --region "$REGION" --format="value(status.url)")
echo "$API_URL"

# 10. ▶ EJECUTAR BATCH + STREAMING AL MISMO TIEMPO
pip install -r requirements.txt --quiet
python orquestador.py "$API_URL"

# 11. Verificar que ambos poblaron el dataset
bq query --use_legacy_sql=false "SELECT COUNT(*) AS streaming FROM red_santiago.posiciones_stream;"
bq query --use_legacy_sql=false "SELECT COUNT(*) AS batch FROM red_santiago.datos_enriquecidos;"
```

---

## Dashboard (Looker Studio)

1. https://lookerstudio.google.com → **Crear → Informe** → **BigQuery**.
2. Conectar dos fuentes del dataset `red_santiago`:
   - `analytics_congestion_stream` (streaming en vivo)
   - `datos_agregados` (histórico batch)
3. Gráficos: congestión por ruta, distribución, velocidad por hora, pings en vivo, KPIs.
4. Menú del informe → **Actualización de datos → 1 minuto** (auto-refresh).

---

## Controles implementados

| Control | Batch | Streaming |
|---|---|---|
| Errores | `try/except` + `CREATE OR REPLACE` (idempotencia) | `try/except`; la API no se cae |
| Duplicidad | `SELECT DISTINCT` + hash compuesto | dedup `bus_id\|minuto` (SKIP) |
| Registro | `estado_ejecuciones_gcp.json` + `proceso_log` | `api_log` |
| Validación | rangos + nulos + leídos vs cargados | validación en línea + vistas `v_dq_*` |
