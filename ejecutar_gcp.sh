#!/bin/bash
# =============================================================================
# RED Santiago Big Data — Script de Ejecucion para Google Cloud Shell
# =============================================================================
# Ejecutar en Cloud Shell de Google Skills Boost
#
# USO:
#   chmod +x ejecutar_gcp.sh
#   ./ejecutar_gcp.sh
# =============================================================================

set -e  # Detener si hay error

echo "============================================================"
echo "RED SANTIAGO BIG DATA — PIPELINE BATCH GCP"
echo "============================================================"
echo ""

# 1. Obtener Project ID automaticamente
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
echo "[INFO] Project ID detectado: $PROJECT_ID"

# 2. Verificar que existe el PROJECT_ID
if [ -z "$PROJECT_ID" ]; then
    echo "[ERROR] No se pudo detectar el Project ID."
    echo "        Ejecute: gcloud config set project TU_PROJECT_ID"
    exit 1
fi

# 3. Actualizar gcp_config.py con el PROJECT_ID correcto
echo "[INFO] Actualizando gcp_config.py con PROJECT_ID: $PROJECT_ID"
sed -i "s/PROJECT_ID = \"TU_PROJECT_ID\"/PROJECT_ID = \"$PROJECT_ID\"/" gcp_config.py

# 4. Instalar dependencias
echo ""
echo "[INFO] Instalando dependencias..."
pip install --quiet google-cloud-storage google-cloud-bigquery pandas matplotlib seaborn db-dtypes

# 5. Generar datos sinteticos
echo ""
echo "============================================================"
echo "PASO 1: Generando datos sinteticos..."
echo "============================================================"
python generar_datos.py

# 6. Ejecutar pipeline GCP
echo ""
echo "============================================================"
echo "PASOS 2-3: Ejecutando pipeline GCP..."
echo "============================================================"
python gcp_pipeline.py

# 7. Generar dashboard
echo ""
echo "============================================================"
echo "PASO 4: Generando dashboard..."
echo "============================================================"
python gcp_dashboard.py

# 8. Resumen
echo ""
echo "============================================================"
echo "PIPELINE COMPLETADO EXITOSAMENTE"
echo "============================================================"
echo ""
echo "Recursos GCP creados:"
echo "  Bucket: gs://${PROJECT_ID}-bigdata/"
echo "  Dataset BigQuery: ${PROJECT_ID}.red_santiago"
echo "  Tablas: gps_raw, clima_raw, datos_enriquecidos, datos_agregados"
echo ""
echo "Archivos locales:"
echo "  output/dashboard.html"
echo "  output/graficos/01_heatmap_congestion.png"
echo "  output/graficos/02_velocidad_por_hora.png"
echo "  output/graficos/03_impacto_clima.png"
echo "  output/graficos/04_congestion_por_ruta.png"
echo ""
echo "Para ver el dashboard:"
echo "  cloudshell download output/dashboard.html"
echo "  cloudshell download output/graficos/"
echo ""
echo "Para ver en BigQuery:"
echo "  https://console.cloud.google.com/bigquery?project=$PROJECT_ID"
echo "============================================================"
