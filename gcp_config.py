"""
=============================================================================
RED Santiago Big Data — Configuracion GCP
=============================================================================
Configuracion para Google Cloud Platform.
Ajustar PROJECT_ID y BUCKET_NAME segun el lab de Skills Boost.
=============================================================================
"""

# =============================================================================
# CONFIGURACION GCP — AJUSTAR SEGUN TU LAB
# =============================================================================
# Estos valores se obtienen del lab de Google Skills Boost.
# En Cloud Shell, ejecuta: gcloud config get-value project
PROJECT_ID = "TU_PROJECT_ID"         # <-- Cambiar por tu Project ID del lab
REGION = "europe-west1"
BUCKET_NAME = f"{PROJECT_ID}-bigdata" # Nombre del bucket en GCS

# =============================================================================
# BIGQUERY
# =============================================================================
DATASET_ID = "red_santiago"           # Dataset en BigQuery
TABLE_GPS_RAW = "gps_raw"             # Tabla de datos GPS crudos
TABLE_CLIMA_RAW = "clima_raw"         # Tabla de datos climaticos crudos
TABLE_GPS_LIMPIO = "gps_limpio"       # Tabla de datos GPS limpios
TABLE_ENRIQUECIDO = "datos_enriquecidos"  # Tabla enriquecida (GPS + Clima)
TABLE_AGREGADO = "datos_agregados"    # Tabla agregada por ruta/hora

# =============================================================================
# CLOUD STORAGE — ESTRUCTURA DEL DATALAKE
# =============================================================================
GCS_RAW_PREFIX = "datalake/raw/"
GCS_STAGING_PREFIX = "datalake/staging/"
GCS_CURATED_PREFIX = "datalake/curated/"

# =============================================================================
# ARCHIVOS FUENTE
# =============================================================================
LOCAL_GPS_FILE = "historial_rutas_DTPM.csv"
LOCAL_CLIMA_FILE = "clima_santiago.json"

# =============================================================================
# VALIDACION
# =============================================================================
VELOCIDAD_MIN = 0
VELOCIDAD_MAX = 120
LATITUD_MIN = -33.65
LATITUD_MAX = -33.30
LONGITUD_MIN = -70.85
LONGITUD_MAX = -70.50
