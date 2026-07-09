"""
=============================================================================
RED Santiago Big Data — Pipeline Batch Completo
=============================================================================
Pipeline ETL (Extract-Transform-Load) para procesamiento Batch de datos
del transporte publico de Santiago.

Pasos cubiertos:
  PASO 2: DataLake en GCP (simulacion local con estructura GCS)
  PASO 3: Limpieza y Transformacion (norm, agr, val, dedup, enriquecimiento)

Controles tecnicos implementados:
  - Control de Errores (try/catch en cada etapa)
  - Control de Duplicados (deteccion, registro, eliminacion)
  - Registro de Actividad (logging completo)
  - Validacion de Datos (rangos, nulos, formatos, coordenadas)
=============================================================================
"""

import pandas as pd
import json
import os
import shutil
import hashlib
from datetime import datetime

# Importar configuracion y utilidades del proyecto
from config import (
    BASE_DIR, RAW_GPS_FILE, RAW_CLIMA_FILE,
    DATALAKE_DIR, DATALAKE_RAW, DATALAKE_STAGING, DATALAKE_CURATED,
    OUTPUT_DIR, LOGS_DIR, GRAFICOS_DIR,
    VELOCIDAD_MIN, VELOCIDAD_MAX,
    LATITUD_MIN, LATITUD_MAX, LONGITUD_MIN, LONGITUD_MAX,
    RUTAS_NORMALIZACION, CONGESTION_UMBRALES,
)
from utils.logger import PipelineLogger
from utils.validators import DataValidator
from utils.error_handler import manejar_errores, ManejadorErroresBatch


# =============================================================================
# INICIALIZACION
# =============================================================================
log = PipelineLogger(nombre_modulo="pipeline_batch")
validator = DataValidator(logger=log)


def crear_directorios():
    """Crea la estructura de directorios del DataLake y salida."""
    directorios = [
        DATALAKE_RAW, DATALAKE_STAGING, DATALAKE_CURATED,
        OUTPUT_DIR, LOGS_DIR, GRAFICOS_DIR,
    ]
    for d in directorios:
        os.makedirs(d, exist_ok=True)
    log.info(f"Estructura de directorios creada en: {DATALAKE_DIR}")


def calcular_checksum(filepath):
    """Calcula MD5 checksum de un archivo para verificar integridad."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# =============================================================================
# PASO 2: DATALAKE — INGESTA AL DATA LAKE
# =============================================================================
@manejar_errores("paso2_datalake", logger=log, continuar_en_error=False)
def paso2_ingesta_datalake():
    """
    PASO 2: Carga de datos crudos al DataLake.
    
    Simula la estructura de Google Cloud Storage (GCS):
      datalake/
        raw/        -> Datos originales sin modificar
        staging/    -> Datos en proceso de limpieza
        curated/    -> Datos limpios y listos para analisis
    """
    log.info("=" * 60)
    log.info("PASO 2: INGESTA AL DATALAKE")
    log.info("=" * 60)

    # Verificar control de re-ejecucion
    puede, ultimo_run = log.puede_ejecutar("paso2_ingesta")

    # --- Cargar CSV de GPS ---
    if not os.path.exists(RAW_GPS_FILE):
        raise FileNotFoundError(
            f"Archivo GPS no encontrado: {RAW_GPS_FILE}. "
            "Ejecute primero generar_datos.py"
        )

    destino_gps = os.path.join(DATALAKE_RAW, "historial_rutas_DTPM.csv")
    shutil.copy2(RAW_GPS_FILE, destino_gps)
    checksum_gps = calcular_checksum(destino_gps)
    log.info(f"  GPS cargado a DataLake/raw: {destino_gps}")
    log.info(f"  Checksum MD5: {checksum_gps}")

    # --- Cargar JSON de Clima ---
    if not os.path.exists(RAW_CLIMA_FILE):
        raise FileNotFoundError(
            f"Archivo Clima no encontrado: {RAW_CLIMA_FILE}. "
            "Ejecute primero generar_datos.py"
        )

    destino_clima = os.path.join(DATALAKE_RAW, "clima_santiago.json")
    shutil.copy2(RAW_CLIMA_FILE, destino_clima)
    checksum_clima = calcular_checksum(destino_clima)
    log.info(f"  Clima cargado a DataLake/raw: {destino_clima}")
    log.info(f"  Checksum MD5: {checksum_clima}")

    # --- Verificar integridad post-carga ---
    df_gps = pd.read_csv(destino_gps)
    with open(destino_clima, 'r', encoding='utf-8') as f:
        clima = json.load(f)

    log.registrar_etapa("paso2_ingesta", "FIN", {
        "archivos_cargados": 2,
        "registros_gps": len(df_gps),
        "registros_clima": len(clima),
        "checksum_gps": checksum_gps,
        "checksum_clima": checksum_clima,
    })

    log.registrar_ejecucion("paso2_ingesta", "EXITOSO",
                            registros_procesados=len(df_gps) + len(clima))

    return df_gps, clima


# =============================================================================
# PASO 3: LIMPIEZA Y TRANSFORMACION
# =============================================================================
@manejar_errores("paso3_limpieza", logger=log, continuar_en_error=False)
def paso3_limpieza_transformacion(df_gps, clima_data):
    """
    PASO 3: Limpieza y transformacion Batch.
    
    Procesos aplicados:
      1. Deduplicacion
      2. Normalizacion de rutas y formatos
      3. Validacion de rangos (velocidad, coordenadas, fechas)
      4. Agregacion por ruta/hora
      5. Enriquecimiento con datos climaticos
      6. Categorizacion de congestion
    """
    log.info("")
    log.info("=" * 60)
    log.info("PASO 3: LIMPIEZA Y TRANSFORMACION")
    log.info("=" * 60)

    puede, ultimo_run = log.puede_ejecutar("paso3_limpieza")
    registros_iniciales = len(df_gps)
    log.info(f"Registros iniciales: {registros_iniciales}")

    # -----------------------------------------------------------------
    # 3.1 DEDUPLICACION
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.1 DEDUPLICACION")
    log.info("-" * 40)

    df_limpio, df_duplicados = validator.validar_duplicados(
        df_gps, nombre_regla="duplicados_exactos"
    )
    log.info(f"  Duplicados eliminados: {len(df_duplicados)}")
    log.info(f"  Registros despues de deduplicacion: {len(df_limpio)}")

    # Guardar duplicados como evidencia
    if len(df_duplicados) > 0:
        ruta_dup = os.path.join(DATALAKE_STAGING, "duplicados_eliminados.csv")
        df_duplicados.to_csv(ruta_dup, index=False)
        log.info(f"  Duplicados guardados como evidencia: {ruta_dup}")

    # -----------------------------------------------------------------
    # 3.2 NORMALIZACION
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.2 NORMALIZACION")
    log.info("-" * 40)

    # Normalizar rutas (case sensitivity)
    rutas_antes = df_limpio['Ruta'].unique().tolist()
    df_limpio['Ruta'] = df_limpio['Ruta'].map(
        lambda x: RUTAS_NORMALIZACION.get(x, x.upper())
    )
    rutas_despues = df_limpio['Ruta'].unique().tolist()
    log.info(f"  Rutas antes:   {sorted(rutas_antes)}")
    log.info(f"  Rutas despues: {sorted(rutas_despues)}")

    # Normalizar Timestamp a datetime
    df_limpio['Timestamp'] = pd.to_datetime(df_limpio['Timestamp'])

    # Extraer componentes de fecha/hora para analisis
    df_limpio['Fecha'] = df_limpio['Timestamp'].dt.date.astype(str)
    df_limpio['Hora'] = df_limpio['Timestamp'].dt.hour
    df_limpio['DiaSemana'] = df_limpio['Timestamp'].dt.day_name()

    log.info("  Timestamps convertidos a datetime")
    log.info("  Columnas extraidas: Fecha, Hora, DiaSemana")

    # -----------------------------------------------------------------
    # 3.3 VALIDACION DE RANGOS
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.3 VALIDACION DE RANGOS")
    log.info("-" * 40)

    # Validar velocidades
    df_limpio, df_vel_invalidas = validator.validar_rango(
        df_limpio, 'Velocidad_kmh', VELOCIDAD_MIN, VELOCIDAD_MAX,
        nombre_regla="velocidad_rango"
    )
    log.info(f"  Velocidades invalidas eliminadas: {len(df_vel_invalidas)}")

    # Guardar registros invalidos como evidencia
    if len(df_vel_invalidas) > 0:
        ruta_inv = os.path.join(DATALAKE_STAGING, "velocidades_invalidas.csv")
        df_vel_invalidas.to_csv(ruta_inv, index=False)

    # Validar coordenadas dentro de Santiago
    df_limpio, df_coord_invalidas = validator.validar_coordenadas(
        df_limpio, 'Latitud', 'Longitud',
        LATITUD_MIN, LATITUD_MAX, LONGITUD_MIN, LONGITUD_MAX,
        nombre_regla="coordenadas_santiago"
    )
    log.info(f"  Coordenadas fuera de Santiago: {len(df_coord_invalidas)}")

    log.info(f"  Registros despues de validacion: {len(df_limpio)}")

    # -----------------------------------------------------------------
    # 3.4 ENRIQUECIMIENTO CON DATOS CLIMATICOS
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.4 ENRIQUECIMIENTO (GPS + CLIMA)")
    log.info("-" * 40)

    # Convertir datos climaticos a DataFrame
    df_clima = pd.DataFrame(clima_data)

    # Manejar temperaturas nulas (imputar con promedio)
    temp_promedio = df_clima['temperatura_promedio'].mean()
    nulos_antes = df_clima['temperatura_promedio'].isnull().sum()
    df_clima['temperatura_promedio'] = df_clima['temperatura_promedio'].fillna(
        round(temp_promedio, 1)
    )
    log.info(f"  Temperaturas nulas imputadas con promedio ({temp_promedio:.1f}C): "
             f"{nulos_antes} registros")

    # Cruzar GPS con clima por fecha
    df_enriquecido = df_limpio.merge(
        df_clima,
        left_on='Fecha',
        right_on='fecha',
        how='left'
    )

    # Limpiar columnas duplicadas del merge
    if 'fecha' in df_enriquecido.columns:
        df_enriquecido.drop(columns=['fecha'], inplace=True)

    # Renombrar para claridad
    df_enriquecido.rename(columns={
        'condicion': 'Clima_Condicion',
        'temperatura_promedio': 'Clima_Temperatura'
    }, inplace=True)

    log.info(f"  Registros enriquecidos con clima: {len(df_enriquecido)}")
    log.info(f"  Columnas finales: {list(df_enriquecido.columns)}")

    # -----------------------------------------------------------------
    # 3.5 CATEGORIZACION DE CONGESTION
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.5 CATEGORIZACION DE CONGESTION")
    log.info("-" * 40)

    def clasificar_congestion(velocidad):
        """Clasifica el nivel de congestion segun la velocidad."""
        for categoria, (v_min, v_max) in CONGESTION_UMBRALES.items():
            if v_min <= velocidad < v_max:
                return categoria
        return 'Desconocido'

    df_enriquecido['Nivel_Congestion'] = df_enriquecido['Velocidad_kmh'].apply(
        clasificar_congestion
    )

    conteo_congestion = df_enriquecido['Nivel_Congestion'].value_counts()
    for nivel, conteo in conteo_congestion.items():
        porcentaje = conteo / len(df_enriquecido) * 100
        log.info(f"  {nivel}: {conteo} registros ({porcentaje:.1f}%)")

    # -----------------------------------------------------------------
    # 3.6 AGREGACION POR RUTA Y HORA
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("3.6 AGREGACION POR RUTA Y HORA")
    log.info("-" * 40)

    df_agregado = df_enriquecido.groupby(['Ruta', 'Hora']).agg(
        Velocidad_Promedio=('Velocidad_kmh', 'mean'),
        Velocidad_Std=('Velocidad_kmh', 'std'),
        Velocidad_Min=('Velocidad_kmh', 'min'),
        Velocidad_Max=('Velocidad_kmh', 'max'),
        Total_Buses=('ID_Bus', 'nunique'),
        Total_Registros=('ID_Bus', 'count'),
    ).reset_index()

    df_agregado['Velocidad_Promedio'] = df_agregado['Velocidad_Promedio'].round(2)
    df_agregado['Velocidad_Std'] = df_agregado['Velocidad_Std'].round(2)

    log.info(f"  Grupos ruta-hora generados: {len(df_agregado)}")
    log.info(f"  Rutas unicas: {df_agregado['Ruta'].nunique()}")
    log.info(f"  Rango de horas: {df_agregado['Hora'].min()}-{df_agregado['Hora'].max()}")

    # -----------------------------------------------------------------
    # GUARDAR RESULTADOS EN DATALAKE CURATED
    # -----------------------------------------------------------------
    log.info("-" * 40)
    log.info("GUARDANDO RESULTADOS")
    log.info("-" * 40)

    # Datos detallados enriquecidos
    ruta_detalle = os.path.join(DATALAKE_CURATED, "datos_enriquecidos.csv")
    df_enriquecido.to_csv(ruta_detalle, index=False)
    log.info(f"  Datos enriquecidos: {ruta_detalle} ({len(df_enriquecido)} filas)")

    # Datos agregados
    ruta_agregado = os.path.join(DATALAKE_CURATED, "datos_agregados_ruta_hora.csv")
    df_agregado.to_csv(ruta_agregado, index=False)
    log.info(f"  Datos agregados: {ruta_agregado} ({len(df_agregado)} filas)")

    # Copias en output/ para acceso directo
    df_enriquecido.to_csv(os.path.join(OUTPUT_DIR, "datos_enriquecidos.csv"), index=False)
    df_agregado.to_csv(os.path.join(OUTPUT_DIR, "datos_agregados.csv"), index=False)

    # JSON solo para el archivo más pequeño (datos_agregados tiene menos filas)
    if len(df_agregado) <= len(df_enriquecido):
        ruta_json = os.path.join(OUTPUT_DIR, "datos_agregados.json")
        df_agregado.to_json(ruta_json, orient="records", indent=2, force_ascii=False)
        log.info(f"  JSON (archivo mas pequeno): {ruta_json} ({len(df_agregado)} filas)")
        # También copia a curated
        ruta_json_curated = os.path.join(DATALAKE_CURATED, "datos_agregados.json")
        df_agregado.to_json(ruta_json_curated, orient="records", indent=2, force_ascii=False)

    # --- Reporte de validacion ---
    reporte = validator.reporte()

    # --- Resumen final ---
    log.info("")
    log.info("=" * 60)
    log.info("RESUMEN PASO 3: LIMPIEZA Y TRANSFORMACION")
    log.info("=" * 60)
    log.info(f"  Registros iniciales:           {registros_iniciales}")
    log.info(f"  Duplicados eliminados:         {reporte['detalle_por_regla'].get('duplicados_exactos', 0)}")
    log.info(f"  Velocidades invalidas:         {reporte['detalle_por_regla'].get('velocidad_rango', 0)}")
    log.info(f"  Coordenadas fuera de rango:    {reporte['detalle_por_regla'].get('coordenadas_santiago', 0)}")
    log.info(f"  Registros finales (detalle):   {len(df_enriquecido)}")
    log.info(f"  Registros finales (agregados): {len(df_agregado)}")
    log.info(f"  Columnas enriquecidas:         {len(df_enriquecido.columns)}")

    log.registrar_ejecucion("paso3_limpieza", "EXITOSO",
                            registros_procesados=len(df_enriquecido))

    return df_enriquecido, df_agregado


# =============================================================================
# FUNCION PRINCIPAL — EJECUTAR PIPELINE COMPLETO
# =============================================================================
def main():
    """Ejecuta el pipeline Batch completo (Pasos 2-3)."""
    print("")
    log.info("*" * 60)
    log.info("RED SANTIAGO BIG DATA — PIPELINE BATCH")
    log.info(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("*" * 60)

    # Crear estructura de directorios
    crear_directorios()

    # PASO 2: Ingesta al DataLake
    resultado_paso2 = paso2_ingesta_datalake()
    if resultado_paso2 is None:
        log.error("Pipeline detenido: fallo en Paso 2 (Ingesta)")
        return

    df_gps, clima_data = resultado_paso2

    # PASO 3: Limpieza y Transformacion
    resultado_paso3 = paso3_limpieza_transformacion(df_gps, clima_data)
    if resultado_paso3 is None:
        log.error("Pipeline detenido: fallo en Paso 3 (Limpieza)")
        return

    df_enriquecido, df_agregado = resultado_paso3

    # Resumen final del pipeline
    log.info("")
    log.info("*" * 60)
    log.info("PIPELINE BATCH COMPLETADO EXITOSAMENTE")
    log.info(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("*" * 60)
    log.info("")
    log.info("Archivos generados:")
    log.info(f"  DataLake/raw/     -> Datos crudos originales")
    log.info(f"  DataLake/staging/ -> Registros invalidos (evidencia)")
    log.info(f"  DataLake/curated/ -> Datos limpios y enriquecidos (CSV + JSON el mas pequeno)")
    log.info(f"  output/           -> Datos listos para dashboard (CSV + JSON el mas pequeno)")
    log.info("")
    log.info("Siguiente paso: ejecutar dashboard.py para generar graficos")
    log.info("*" * 60)


if __name__ == "__main__":
    main()
