"""
=============================================================================
RED Santiago Big Data - Generación de Datos Sintéticos
=============================================================================
Proyecto: Predicción de Congestión del Transporte Público (Batch)
Plataforma: Google Cloud Platform (GCP)

Este script genera los datasets base para el pipeline Batch:
   1. historial_rutas_DTPM.csv  - Datos GPS de buses (CSV)
   2. clima_santiago.json       - Datos climáticos (JSON)
=============================================================================
"""

import pandas as pd
import random
import json
from datetime import datetime, timedelta

# Semilla para reproducibilidad (comentar para datos aleatorios cada vez)
random.seed(42)

# =============================================================================
# 1. GENERAR DATOS GPS (CSV)
# =============================================================================
print("=" * 60)
print("FASE 1: Generación de Datos GPS de Buses")
print("=" * 60)

num_records = 10000  # Volumen para procesamiento Batch

# Incluye errores intencionales de case: '502C' vs '502c'
rutas = ['210', '210e', '502', '502C', '502c', '104']

data_gps = []
start_time = datetime(2026, 5, 1, 6, 0, 0)

for i in range(num_records):
    id_bus = f"BUS_{random.randint(1000, 1050)}"
    ruta = random.choice(rutas)

    velocidad = random.randint(10, 60)

    lat = -33.45 + random.uniform(-0.1, 0.1)
    lon = -70.66 + random.uniform(-0.1, 0.1)
    timestamp = start_time + timedelta(minutes=random.randint(1, 44640))  # 31 días

    data_gps.append([
        id_bus, ruta, velocidad, lat, lon,
        timestamp.strftime("%Y-%m-%d %H:%M:%S")
    ])

df_gps = pd.DataFrame(
    data_gps,
    columns=['ID_Bus', 'Ruta', 'Velocidad_kmh', 'Latitud', 'Longitud', 'Timestamp']
)

df_final = df_gps

# Guardar CSV
df_final.to_csv('historial_rutas_DTPM.csv', index=False)

print(f"  [OK] Registros totales generados: {len(df_final)}")
print(f"       - Rutas únicas:               {df_final['Ruta'].nunique()}")
print(f"  [OK] Archivo guardado: historial_rutas_DTPM.csv")

# =============================================================================
# 2. GENERAR DATOS CLIMÁTICOS (JSON)
# =============================================================================
print()
print("=" * 60)
print("FASE 2: Generación de Datos Climáticos")
print("=" * 60)

clima_data = []

for i in range(31):  # Mayo 2026, 31 días
    fecha = datetime(2026, 5, 1) + timedelta(days=i)
    condicion = random.choice(['Despejado', 'Lluvia', 'Nublado'])

    temp = round(random.uniform(5.0, 25.0), 1)

    clima_data.append({
        "fecha": fecha.strftime("%Y-%m-%d"),
        "condicion": condicion,
        "temperatura_promedio": temp
    })

# Guardar JSON
with open('clima_santiago.json', 'w', encoding='utf-8') as f:
    json.dump(clima_data, f, indent=4, ensure_ascii=False)

print(f"  [OK] Registros climáticos generados: {len(clima_data)}")
print(f"  [OK] Archivo guardado: clima_santiago.json")

# =============================================================================
# RESUMEN FINAL
# =============================================================================
print()
print("=" * 60)
print("RESUMEN DE GENERACIÓN")
print("=" * 60)
print(f"  Archivos generados:")
print(f"    1. historial_rutas_DTPM.csv  ({len(df_final)} registros)")
print(f"    2. clima_santiago.json       ({len(clima_data)} registros)")
print()
print("  [OK] Archivos generados exitosamente.")
print("=" * 60)
