# Guía de Despliegue en GCP

> Pipeline completo: Batch (CSV → GCS → BigQuery → Star Schema) + Streaming (API → GCS NDJSON → BigQuery → Looker Studio)

---

## 0. Requisitos previos

- Tener `gcloud` instalado y autenticado
- Tener un proyecto GCP con facturación habilitada
- Tener habilitadas las APIs: `run.googleapis.com`, `cloudbuild.googleapis.com`, `bigquery.googleapis.com`, `storage.googleapis.com`

---

## 1. Subir archivos a Cloud Shell

Desde el menú **⋮ → Upload** en Cloud Shell, subir:

- `main.py`
- `voting_api.py`
- `Dockerfile`
- `requirements.txt`
- `setup_bq.sql`
- `demo_stream.sh`

---

## 2. Configurar variables de entorno

```bash
# Reemplaza con tu project ID real
PROJECT_ID="qwiklabs-gcp-03-5128b7abbcbe"
REGION="us-east4"
BUCKET_NAME="valorant-bigdata-2026-1"

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

---

## 3. Crear bucket de Cloud Storage (Data Lake)

```bash
gcloud storage buckets create "gs://$BUCKET_NAME" \
  --location="$REGION" \
  --uniform-bucket-level-access

# Crear estructura de carpetas batch
for table in users skins transactions regions daily_store payment_methods; do
  gcloud storage cp /dev/null "gs://$BUCKET_NAME/raw/$table/.keep" 2>/dev/null || \
  echo "" | gcloud storage cp - "gs://$BUCKET_NAME/raw/$table/.keep"
done

# Crear estructura de carpetas streaming
for table in votes purchases api_log; do
  echo "" | gcloud storage cp - "gs://$BUCKET_NAME/streaming/$table/.keep"
done
```

---

## 4. Generar datasets batch (local o Cloud Shell)

```bash
# Instalar dependencias si no están
pip install -r requirements.txt

# Generar datos sintéticos (ejecutar localmente)
python main.py
```

Esto generará en `data/`:

| Archivo | Descripción |
|---|---|
| `regions.csv` | 6 regiones de juego |
| `payment_methods.csv` | 3 métodos de pago |
| `payment_methods.json` | Ídem en JSON |
| `skins.csv` | 50 skins |
| `users.csv` | 2000 usuarios |
| `transactions.csv` | 10000 transacciones |
| `daily_store.csv` | Rotación diaria (365 días) |

---

## 5. Subir datos batch a GCS (Data Lake)

```bash
# Users
gcloud storage cp data/users.csv gs://$BUCKET_NAME/raw/users/

# Skins
gcloud storage cp data/skins.csv gs://$BUCKET_NAME/raw/skins/

# Transactions
gcloud storage cp data/transactions.csv gs://$BUCKET_NAME/raw/transactions/

# Regions
gcloud storage cp data/regions.csv gs://$BUCKET_NAME/raw/regions/

# Daily Store
gcloud storage cp data/daily_store.csv gs://$BUCKET_NAME/raw/daily_store/

# Payment Methods
gcloud storage cp data/payment_methods.csv gs://$BUCKET_NAME/raw/payment_methods/
gcloud storage cp data/payment_methods.json gs://$BUCKET_NAME/raw/payment_methods/

# ETL Log (opcional para tracking manual)
# gcloud storage cp data/etl_log.csv gs://$BUCKET_NAME/raw/etl_log/
```

---

## 6. Crear dataset en BigQuery

```bash
bq mk --dataset --location="$REGION" valorant_dw
```

---

## 7. Carga de CSVs a BigQuery (datos raw)

```bash
# Users
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.users gs://$BUCKET_NAME/raw/users/users.csv

# Skins
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.skins gs://$BUCKET_NAME/raw/skins/skins.csv

# Transactions
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.transactions gs://$BUCKET_NAME/raw/transactions/transactions.csv

# Regions
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.regions gs://$BUCKET_NAME/raw/regions/regions.csv

# Daily Store
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.daily_store gs://$BUCKET_NAME/raw/daily_store/daily_store.csv

# Payment Methods (CSV)
bq load --skip_leading_rows=1 --autodetect --source_format=CSV \
  valorant_dw.payment_methods gs://$BUCKET_NAME/raw/payment_methods/payment_methods.csv

### Payment Methods (JSON → NDJSON)

```bash
gcloud storage cp gs://$BUCKET_NAME/raw/payment_methods/payment_methods.json ./payment_methods.json
jq -c '.[]' payment_methods.json > payment_methods_ndjson.json
gcloud storage cp payment_methods_ndjson.json gs://$BUCKET_NAME/raw/payment_methods/

# Cargar NDJSON a BigQuery
bq load \
  --autodetect \
  --source_format=NEWLINE_DELIMITED_JSON \
  valorant_dw.payment_methods \
  gs://$BUCKET_NAME/raw/payment_methods/payment_methods_ndjson.json
```

### Verificar tablas cargadas

```bash
bq ls valorant_dw
bq head valorant_dw.users
bq head valorant_dw.transactions
```

---

## 8. Crear modelo Star Schema (ETL batch)

```bash
# Dim Users
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE valorant_dw.dim_users AS
SELECT DISTINCT
    user_id,
    username,
    region_id,
    level,
    total_hours_played,
    rank,
    registration_date,
    last_login
FROM valorant_dw.users;
"

# Dim Regions
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE valorant_dw.dim_regions AS
SELECT DISTINCT region_id, region_name, avg_player_spending
FROM valorant_dw.regions;
"

# Dim Payment Methods
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE valorant_dw.dim_payment_methods AS
SELECT DISTINCT payment_method_id, method_name
FROM valorant_dw.payment_methods;
"

# Dim Skins
bq query --use_legacy_sql=false "
CREATE OR REPLACE TABLE valorant_dw.dim_skins AS
SELECT DISTINCT
    skin_id, skin_name, weapon, rarity, base_price_vp, collection, release_date
FROM valorant_dw.skins;
"

# Fact Transactions
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE valorant_dw.fact_transactions AS
SELECT
    transaction_id,
    user_id,
    skin_id,
    payment_method_id,
    purchase_date,
    final_price_vp,
    discount_percent,
    bundle_purchase
FROM valorant_dw.transactions;
'
```

---

## 9. Crear tabla analítica final (batch)

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE valorant_dw.analytics_sales AS
SELECT
    ft.transaction_id,
    du.username,
    dr.region_name,
    du.rank,
    ds.skin_name,
    ds.weapon,
    ds.rarity,
    ds.collection,
    dpm.method_name AS payment_method,
    ft.purchase_date,
    ft.final_price_vp,
    ft.discount_percent,
    ft.bundle_purchase
FROM valorant_dw.fact_transactions ft
JOIN valorant_dw.dim_users du ON ft.user_id = du.user_id
JOIN valorant_dw.dim_regions dr ON du.region_id = dr.region_id
JOIN valorant_dw.dim_skins ds ON ft.skin_id = ds.skin_id
JOIN valorant_dw.dim_payment_methods dpm ON ft.payment_method_id = dpm.payment_method_id;
'

bq head valorant_dw.analytics_sales
```

---

## 10. Desplegar API de Streaming (Cloud Run)

### 10.1 Habilitar servicios

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

### 10.2 Buildear imagen Docker

```bash
gcloud builds submit --tag "gcr.io/$PROJECT_ID/valorant-vote-api"
```

### 10.3 Desplegar en Cloud Run

```bash
gcloud run deploy valorant-vote-api \
  --image "gcr.io/$PROJECT_ID/valorant-vote-api" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=$PROJECT_ID,BQ_DATASET=valorant_dw,GCS_BUCKET=$BUCKET_NAME,AUTO_PURCHASE_INTERVAL=15,MIN_VOTES_FOR_AUTO=5" \
  --min-instances 1 \
  --timeout 300
```

### 10.4 Obtener URL

```bash
API_URL=$(gcloud run services describe valorant-vote-api \
  --region "$REGION" --format="value(status.url)")
echo "API URL: $API_URL"
```

---

## 11. Configurar BigQuery para Streaming

```bash
# Ejecutar setup_bq.sql para crear tablas streaming + vistas
cat setup_bq.sql | bq query --nouse_legacy_sql
```

Esto crea:

| Tabla | Propósito |
|---|---|
| `charities` | Datos de referencia (5 beneficencias) |
| `voting_skins` | Skins en votación (2 skins) |
| `votes` | Votos streaming con campos enriquecidos |
| `purchases` | Compras streaming con campos enriquecidos |
| `api_log` | Log de actividad de la API |
| `etl_log` | Log de actividad ETL batch |
| `analytics_voting` | Vista analítica de votación |
| `analytics_donations` | Vista analítica de donaciones |
| `v_dq_duplicate_votes` | Vista control calidad: votos duplicados |
| `v_dq_anomalous_purchases` | Vista control calidad: anomalías en montos |
| `v_dq_orphan_votes` | Vista control calidad: registros huérfanos |

---

## 12. Probar API

```bash
curl -s "$API_URL/"
```

---

## 13. Generar votos de prueba (streaming)

```bash
# Voto individual
curl -s -X POST "$API_URL/api/vote" \
  -H "Content-Type: application/json" \
  -d '{"player_id": "test-001", "skin_id": 1, "charity_id": 2}' | python3 -m json.tool

# Ver archivos en GCS Data Lake
curl -s "$API_URL/api/gcs/list" | python3 -m json.tool

# Ver resultados de votación
curl -s "$API_URL/api/vote/results" | python3 -m json.tool
```

---

## 14. Activar compras automáticas

```bash
curl -s -X POST "$API_URL/api/auto-purchase/start"
```

---

## 15. Demo: tráfico pesado para el video

```bash
while true; do
  for i in $(seq 1 40); do
    PLAYER="player-$(date +%s)-$i-$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 4 | head -1)"
    SKIN=$(( (RANDOM % 2) + 1 ))
    CHARITY=$(( (RANDOM % 5) + 1 ))
    curl -s -X POST "$API_URL/api/vote" \
      -H "Content-Type: application/json" \
      -d "{\"player_id\": \"$PLAYER\", \"skin_id\": $SKIN, \"charity_id\": $CHARITY}" > /dev/null
  done
  echo "[$(date)] 40 votos enviados ✓"
  sleep 5
done
```

O usar el script de demo:

```bash
chmod +x demo_stream.sh
./demo_stream.sh "$API_URL"
```

---

## 16. Dashboard en Looker Studio

### Batch (ventas históricas)

1. Abrir [lookerstudio.google.com](https://lookerstudio.google.com)
2. **Crear → Informe en blanco**
3. Agregar datos → **BigQuery** → `$PROJECT_ID` → `valorant_dw` → `analytics_sales`
4. Gráficos recomendados:

| Gráfico | Dimensión | Métrica |
|---|---|---|
| Ventas por región | `region_name` | `final_price_vp` (SUM) |
| Ingresos en el tiempo | `purchase_date` | `final_price_vp` (SUM) |
| Top skins vendidas | `skin_name` | `transaction_id` (COUNT) |
| Ventas por rareza | `rarity` | `final_price_vp` (SUM) |
| Método de pago | `payment_method` | `transaction_id` (COUNT) |


### Streaming (votación en vivo)

4. Agregar otra fuente de datos → **BigQuery** → `$PROJECT_ID` → `valorant_dw` → `analytics_voting`

| Gráfico | Dimensión | Métrica |
|---|---|---|
| Votos por skin | `skin_name` | `vote_id` (COUNT) |
| Votos en el tiempo | `voted_at` | `vote_id` (COUNT) |
| Charity leaderboard | `charity_voted` | `vote_id` (COUNT) |
| Dispositivos | `device_type` | `vote_id` (COUNT) |
| Jugadores premium | `is_premium_player` | `vote_id` (COUNT) |

5. Para refrescar automático: agregar `?refresh=15` a la URL del informe

---

## 17. Consultas analíticas de ejemplo

```bash
# Total ventas por región (batch)
bq query --use_legacy_sql=false "
SELECT region_name, COUNT(*) AS total_sales, SUM(final_price_vp) AS total_vp
FROM valorant_dw.analytics_sales
GROUP BY region_name ORDER BY total_vp DESC;
"

# Resultados de votación en vivo (streaming)
bq query --use_legacy_sql=false "
SELECT skin_name, COUNT(*) AS votes,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS percentage
FROM valorant_dw.analytics_voting
GROUP BY skin_name ORDER BY votes DESC;
"

# Donaciones por beneficencia
bq query --use_legacy_sql=false "
SELECT beneficiary, SUM(amount_vp) AS total_donated, COUNT(*) AS purchases
FROM valorant_dw.analytics_donations
GROUP BY beneficiary ORDER BY total_donated DESC;
"

# Ver control de calidad
bq query --use_legacy_sql=false "SELECT * FROM valorant_dw.v_dq_duplicate_votes;"
bq query --use_legacy_sql=false "SELECT * FROM valorant_dw.v_dq_anomalous_purchases;"
```

---

## 18. Monitoreo y logs

```bash
# Logs de la API
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=valorant-vote-api" --limit 20

# Ver logs de actividad desde BigQuery
bq query --use_legacy_sql=false "
SELECT event_type, description, created_at
FROM valorant_dw.api_log
ORDER BY created_at DESC LIMIT 20;
"
```

---

## 19. Cleanup (si es necesario)

```bash
# Eliminar servicio Cloud Run
gcloud run services delete valorant-vote-api --region "$REGION"

# Eliminar imágenes de Container Registry
gcloud container images delete "gcr.io/$PROJECT_ID/valorant-vote-api" --quiet

# Eliminar dataset BigQuery
bq rm -r -f valorant_dw

# Eliminar bucket GCS
gcloud storage rm -r "gs://$BUCKET_NAME"
```
