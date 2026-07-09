"""
=============================================================================
RED Santiago Big Data — Configuración Centralizada
=============================================================================
Archivo de configuración con rutas, parámetros y constantes del proyecto.
=============================================================================
"""

import os

# =============================================================================
# RUTAS DEL PROYECTO
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Archivos de entrada (raw)
RAW_GPS_FILE = os.path.join(BASE_DIR, "historial_rutas_DTPM.csv")
RAW_CLIMA_FILE = os.path.join(BASE_DIR, "clima_santiago.json")

# Directorios del DataLake (simulación local de GCS)
DATALAKE_DIR = os.path.join(BASE_DIR, "datalake")
DATALAKE_RAW = os.path.join(DATALAKE_DIR, "raw")          # Datos crudos
DATALAKE_STAGING = os.path.join(DATALAKE_DIR, "staging")   # Datos en proceso
DATALAKE_CURATED = os.path.join(DATALAKE_DIR, "curated")   # Datos limpios finales

# Directorio de salida
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOGS_DIR = os.path.join(OUTPUT_DIR, "logs")
GRAFICOS_DIR = os.path.join(OUTPUT_DIR, "graficos")

# =============================================================================
# PARÁMETROS DE VALIDACIÓN
# =============================================================================
VELOCIDAD_MIN = 0        # km/h — velocidades negativas son error
VELOCIDAD_MAX = 120      # km/h — velocidad máxima realista para bus urbano

# Límites geográficos de Santiago (bounding box)
LATITUD_MIN = -33.65
LATITUD_MAX = -33.30
LONGITUD_MIN = -70.85
LONGITUD_MAX = -70.50

# =============================================================================
# NORMALIZACIÓN DE RUTAS
# =============================================================================
# Mapeo de rutas con errores de case a su forma canónica
RUTAS_NORMALIZACION = {
    '210':  '210',
    '210e': '210E',
    '210E': '210E',
    '502':  '502',
    '502c': '502C',
    '502C': '502C',
    '104':  '104',
}

# =============================================================================
# CATEGORÍAS DE CONGESTIÓN
# =============================================================================
# Basado en velocidad promedio del bus
CONGESTION_UMBRALES = {
    'Fluido':       (30, 120),   # >= 30 km/h
    'Moderado':     (15, 30),    # 15-30 km/h
    'Congestionado': (0, 15),    # < 15 km/h
}

# =============================================================================
# PARÁMETROS DE GENERACIÓN DE DATOS
# =============================================================================
NUM_REGISTROS_GPS = 5000
PORCENTAJE_VELOCIDADES_NEGATIVAS = 0.05
NUM_DUPLICADOS = 100
PORCENTAJE_TEMPERATURAS_NULAS = 0.10

# =============================================================================
# CONFIGURACIÓN DE LOGGING
# =============================================================================
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = "INFO"
