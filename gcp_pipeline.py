"""
=============================================================================
RED Santiago Big Data — Pipeline Batch en GCP
=============================================================================
Pipeline ETL completo ejecutado en Google Cloud Platform:

  PASO 1: Generacion de datos (generar_datos.py — ya existe)
  PASO 2: Ingesta a Cloud Storage (DataLake) + carga a BigQuery
  PASO 3: Limpieza y Transformacion con SQL en BigQuery
  PASO 4: Exportar resultados para Dashboard

Controles tecnicos implementados:
  - Control de Errores (try/except en cada etapa)
  - Control de Duplicados (deteccion y eliminacion con SQL)
  - Registro de Actividad (logging completo con timestamps)
  - Validacion de Datos (rangos, nulos, coordenadas con SQL)

EJECUCION:
  1. Abrir Cloud Shell en Google Skills Boost
  2. Subir archivos: generar_datos.py, gcp_pipeline.py, gcp_config.py,
     historial_rutas_DTPM.csv, clima_santiago.json
  3. Ajustar PROJECT_ID en gcp_config.py
  4. Ejecutar: python gcp_pipeline.py
=============================================================================
"""

import os
import sys
import json
import logging
import hashlib
from datetime import datetime

# Intentar importar librerias GCP
try:
    from google.cloud import storage
    from google.cloud import bigquery
    from google.api_core import exceptions as gcp_exceptions
except ImportError:
    print("=" * 60)
    print("INSTALANDO DEPENDENCIAS GCP...")
    print("=" * 60)
    os.system(f"{sys.executable} -m pip install google-cloud-storage google-cloud-bigquery")
    from google.cloud import storage
    from google.cloud import bigquery
    from google.api_core import exceptions as gcp_exceptions

from gcp_config import (
    PROJECT_ID, REGION, BUCKET_NAME,
    DATASET_ID, TABLE_GPS_RAW, TABLE_CLIMA_RAW,
    TABLE_GPS_LIMPIO, TABLE_ENRIQUECIDO, TABLE_AGREGADO,
    GCS_RAW_PREFIX, GCS_STAGING_PREFIX, GCS_CURATED_PREFIX,
    LOCAL_GPS_FILE, LOCAL_CLIMA_FILE,
    VELOCIDAD_MIN, VELOCIDAD_MAX,
    LATITUD_MIN, LATITUD_MAX, LONGITUD_MIN, LONGITUD_MAX,
)

# =============================================================================
# LOGGING — Registro de Actividad (Control Tecnico)
# =============================================================================
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"pipeline_gcp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding='utf-8'
        ),
    ]
)
log = logging.getLogger("gcp_pipeline")

# Estado de ejecuciones para control de re-ejecucion
ESTADO_FILE = "estado_ejecuciones_gcp.json"


def registrar_ejecucion(proceso_id, resultado, detalles=""):
    """Registra ejecucion en archivo JSON para control de re-ejecucion."""
    estado = {}
    if os.path.exists(ESTADO_FILE):
        try:
            with open(ESTADO_FILE, 'r') as f:
                estado = json.load(f)
        except Exception:
            pass

    # Verificar si ya se ejecuto
    if proceso_id in estado:
        log.warning(
            f"Proceso '{proceso_id}' ya fue ejecutado el "
            f"{estado[proceso_id]['timestamp']} con resultado: "
            f"{estado[proceso_id]['resultado']}. Se re-ejecutara."
        )

    estado[proceso_id] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "resultado": resultado,
        "detalles": detalles,
    }
    with open(ESTADO_FILE, 'w') as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)

    log.info(f"Ejecucion registrada: {proceso_id} -> {resultado}")


def calcular_checksum(filepath):
    """Calcula MD5 para verificar integridad de archivos."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# =============================================================================
# PASO 2A: CREAR BUCKET EN CLOUD STORAGE (DATALAKE)
# =============================================================================
def paso2a_crear_bucket():
    """
    Crea el bucket de Cloud Storage que servira como DataLake.
    Estructura: raw/ -> staging/ -> curated/
    """
    log.info("=" * 60)
    log.info("PASO 2A: CREAR BUCKET EN CLOUD STORAGE (DATALAKE)")
    log.info("=" * 60)

    try:
        client = storage.Client(project=PROJECT_ID)

        # Verificar si el bucket ya existe
        try:
            bucket = client.get_bucket(BUCKET_NAME)
            log.warning(f"Bucket '{BUCKET_NAME}' ya existe. Continuando...")
        except gcp_exceptions.NotFound:
            bucket = client.bucket(BUCKET_NAME)
            bucket.location = REGION
            bucket = client.create_bucket(bucket)
            log.info(f"Bucket creado: gs://{BUCKET_NAME}")

        log.info(f"  DataLake GCS: gs://{BUCKET_NAME}/")
        log.info(f"    raw/     -> Datos crudos originales")
        log.info(f"    staging/ -> Datos en proceso")
        log.info(f"    curated/ -> Datos limpios finales")

        registrar_ejecucion("paso2a_crear_bucket", "EXITOSO",
                            f"Bucket: {BUCKET_NAME}")
        return bucket

    except Exception as e:
        log.error(f"Error creando bucket: {e}")
        registrar_ejecucion("paso2a_crear_bucket", "FALLIDO", str(e))
        raise


# =============================================================================
# PASO 2B: SUBIR ARCHIVOS A CLOUD STORAGE
# =============================================================================
def paso2b_subir_archivos(bucket):
    """
    Sube los archivos CSV y JSON al DataLake en Cloud Storage.
    Incluye verificacion de integridad con checksum.
    """
    log.info("")
    log.info("=" * 60)
    log.info("PASO 2B: SUBIR ARCHIVOS A CLOUD STORAGE")
    log.info("=" * 60)

    archivos = [
        (LOCAL_GPS_FILE, f"{GCS_RAW_PREFIX}{LOCAL_GPS_FILE}"),
        (LOCAL_CLIMA_FILE, f"{GCS_RAW_PREFIX}{LOCAL_CLIMA_FILE}"),
    ]

    try:
        for local_path, gcs_path in archivos:
            if not os.path.exists(local_path):
                raise FileNotFoundError(
                    f"Archivo no encontrado: {local_path}. "
                    "Ejecute primero: python generar_datos.py"
                )

            # Calcular checksum antes de subir
            checksum = calcular_checksum(local_path)
            file_size = os.path.getsize(local_path)

            # Verificar si ya existe (control de duplicados)
            blob = bucket.blob(gcs_path)
            if blob.exists():
                log.warning(f"  Archivo ya existe en GCS: {gcs_path}. Sobreescribiendo...")

            # Subir archivo
            blob.upload_from_filename(local_path)
            log.info(f"  [OK] Subido: {local_path}")
            log.info(f"       -> gs://{BUCKET_NAME}/{gcs_path}")
            log.info(f"       Tamano: {file_size:,} bytes | MD5: {checksum}")

        registrar_ejecucion("paso2b_subir_archivos", "EXITOSO",
                            f"{len(archivos)} archivos subidos")

    except Exception as e:
        log.error(f"Error subiendo archivos: {e}")
        registrar_ejecucion("paso2b_subir_archivos", "FALLIDO", str(e))
        raise


# =============================================================================
# PASO 2C: CREAR DATASET Y CARGAR DATOS EN BIGQUERY
# =============================================================================
def paso2c_cargar_bigquery():
    """
    Crea el dataset en BigQuery y carga los datos desde Cloud Storage.
    - GPS (CSV) -> tabla gps_raw
    - Clima (JSON) -> tabla clima_raw
    """
    log.info("")
    log.info("=" * 60)
    log.info("PASO 2C: CARGAR DATOS EN BIGQUERY")
    log.info("=" * 60)

    try:
        client = bigquery.Client(project=PROJECT_ID)

        # --- Crear Dataset ---
        dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
        dataset_ref.location = REGION

        try:
            client.get_dataset(dataset_ref)
            log.warning(f"Dataset '{DATASET_ID}' ya existe. Continuando...")
        except gcp_exceptions.NotFound:
            dataset_ref = client.create_dataset(dataset_ref)
            log.info(f"Dataset creado: {PROJECT_ID}.{DATASET_ID}")

        # --- Cargar CSV de GPS ---
        log.info("-" * 40)
        log.info("Cargando GPS (CSV) -> BigQuery...")

        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=False,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[
                bigquery.SchemaField("ID_Bus", "STRING"),
                bigquery.SchemaField("Ruta", "STRING"),
                bigquery.SchemaField("Velocidad_kmh", "FLOAT64"),
                bigquery.SchemaField("Latitud", "FLOAT64"),
                bigquery.SchemaField("Longitud", "FLOAT64"),
                bigquery.SchemaField("Timestamp", "TIMESTAMP"),
            ],
        )

        uri_gps = f"gs://{BUCKET_NAME}/{GCS_RAW_PREFIX}{LOCAL_GPS_FILE}"
        load_job = client.load_table_from_uri(uri_gps, table_ref, job_config=job_config)
        load_job.result()  # Esperar a que termine

        table = client.get_table(table_ref)
        log.info(f"  [OK] Tabla: {table_ref}")
        log.info(f"       Filas cargadas: {table.num_rows}")

        # --- Cargar JSON de Clima ---
        log.info("-" * 40)
        log.info("Cargando Clima (JSON) -> BigQuery...")

        table_ref_clima = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_CLIMA_RAW}"

        job_config_clima = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[
                bigquery.SchemaField("fecha", "DATE"),
                bigquery.SchemaField("condicion", "STRING"),
                bigquery.SchemaField("temperatura_promedio", "FLOAT64"),
            ],
        )

        # BigQuery necesita JSON en formato newline-delimited
        # Convertir el JSON array a NDJSON
        log.info("  Convirtiendo JSON a formato NDJSON para BigQuery...")
        with open(LOCAL_CLIMA_FILE, 'r', encoding='utf-8') as f:
            clima_data = json.load(f)

        ndjson_file = "clima_santiago_ndjson.json"
        with open(ndjson_file, 'w', encoding='utf-8') as f:
            for record in clima_data:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        # Subir NDJSON a GCS
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.get_bucket(BUCKET_NAME)
        blob = bucket.blob(f"{GCS_RAW_PREFIX}clima_santiago_ndjson.json")
        blob.upload_from_filename(ndjson_file)

        uri_clima = f"gs://{BUCKET_NAME}/{GCS_RAW_PREFIX}clima_santiago_ndjson.json"
        load_job_clima = client.load_table_from_uri(
            uri_clima, table_ref_clima, job_config=job_config_clima
        )
        load_job_clima.result()

        table_clima = client.get_table(table_ref_clima)
        log.info(f"  [OK] Tabla: {table_ref_clima}")
        log.info(f"       Filas cargadas: {table_clima.num_rows}")

        # Limpiar archivo temporal
        if os.path.exists(ndjson_file):
            os.remove(ndjson_file)

        registrar_ejecucion("paso2c_cargar_bigquery", "EXITOSO",
                            f"GPS: {table.num_rows} filas, Clima: {table_clima.num_rows} filas")
        return client

    except Exception as e:
        log.error(f"Error cargando datos en BigQuery: {e}")
        registrar_ejecucion("paso2c_cargar_bigquery", "FALLIDO", str(e))
        raise


# =============================================================================
# PASO 3: LIMPIEZA Y TRANSFORMACION EN BIGQUERY (SQL)
# =============================================================================
def paso3_limpieza_transformacion(client):
    """
    Ejecuta las transformaciones Batch directamente en BigQuery con SQL.

    Procesos:
      1. Deduplicacion
      2. Validacion de rangos (velocidad, coordenadas)
      3. Normalizacion de rutas
      4. Enriquecimiento con datos climaticos
      5. Categorizacion de congestion
      6. Agregacion por ruta/hora
    """
    log.info("")
    log.info("=" * 60)
    log.info("PASO 3: LIMPIEZA Y TRANSFORMACION EN BIGQUERY")
    log.info("=" * 60)

    try:
        # ---------------------------------------------------------------
        # 3.1 CONTAR ERRORES ANTES DE LIMPIAR (para evidencia)
        # ---------------------------------------------------------------
        log.info("-" * 40)
        log.info("3.1 ANALISIS DE DATOS CRUDOS")

        query_analisis = f"""
        SELECT
            COUNT(*) as total_registros,
            COUNTIF(Velocidad_kmh < {VELOCIDAD_MIN} OR Velocidad_kmh > {VELOCIDAD_MAX}) as velocidades_invalidas,
            (SELECT COUNT(*) FROM (
                SELECT ID_Bus, Ruta, Velocidad_kmh, Latitud, Longitud, Timestamp,
                       COUNT(*) as cnt
                FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}`
                GROUP BY ID_Bus, Ruta, Velocidad_kmh, Latitud, Longitud, Timestamp
                HAVING cnt > 1
            )) as registros_con_duplicados,
            COUNT(*) - COUNT(DISTINCT CONCAT(
                ID_Bus, Ruta, CAST(Velocidad_kmh AS STRING),
                CAST(Latitud AS STRING), CAST(Longitud AS STRING),
                CAST(Timestamp AS STRING)
            )) as total_duplicados,
            COUNTIF(
                Latitud < {LATITUD_MIN} OR Latitud > {LATITUD_MAX} OR
                Longitud < {LONGITUD_MIN} OR Longitud > {LONGITUD_MAX}
            ) as coordenadas_fuera_rango
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}`
        """

        result = client.query(query_analisis).result()
        for row in result:
            log.info(f"  Total registros:         {row.total_registros}")
            log.info(f"  Velocidades invalidas:   {row.velocidades_invalidas}")
            log.info(f"  Registros duplicados:    {row.total_duplicados}")
            log.info(f"  Coordenadas fuera rango: {row.coordenadas_fuera_rango}")

        # ---------------------------------------------------------------
        # 3.2 GUARDAR DUPLICADOS COMO EVIDENCIA (staging)
        # ---------------------------------------------------------------
        log.info("-" * 40)
        log.info("3.2 GUARDANDO REGISTROS INVALIDOS (evidencia)")

        query_guardar_invalidos = f"""
        CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET_ID}.registros_invalidos` AS

        -- Duplicados
        SELECT *, 'DUPLICADO' as tipo_error FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY ID_Bus, Ruta, CAST(Velocidad_kmh AS STRING), CAST(Latitud AS STRING), CAST(Longitud AS STRING), Timestamp
                ORDER BY ID_Bus
            ) as rn
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}`
        ) WHERE rn > 1

        UNION ALL

        -- Velocidades invalidas
        SELECT *, 1 as rn, 'VELOCIDAD_INVALIDA' as tipo_error
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}`
        WHERE Velocidad_kmh < {VELOCIDAD_MIN} OR Velocidad_kmh > {VELOCIDAD_MAX}
        """

        client.query(query_guardar_invalidos).result()
        invalidos_table = client.get_table(
            f"{PROJECT_ID}.{DATASET_ID}.registros_invalidos"
        )
        log.info(f"  [OK] Registros invalidos guardados: {invalidos_table.num_rows}")

        # ---------------------------------------------------------------
        # 3.3 CREAR TABLA LIMPIA CON TODAS LAS TRANSFORMACIONES
        # ---------------------------------------------------------------
        log.info("-" * 40)
        log.info("3.3 LIMPIEZA + NORMALIZACION + ENRIQUECIMIENTO")

        query_limpieza = f"""
        CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}` AS

        WITH
        -- Paso 1: Deduplicar
        deduplicado AS (
            SELECT DISTINCT
                ID_Bus, Ruta, Velocidad_kmh, Latitud, Longitud, Timestamp
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_GPS_RAW}`
        ),

        -- Paso 2: Validar rangos (eliminar velocidades negativas y fuera de rango)
        validado AS (
            SELECT *
            FROM deduplicado
            WHERE Velocidad_kmh >= {VELOCIDAD_MIN}
              AND Velocidad_kmh <= {VELOCIDAD_MAX}
              AND Latitud BETWEEN {LATITUD_MIN} AND {LATITUD_MAX}
              AND Longitud BETWEEN {LONGITUD_MIN} AND {LONGITUD_MAX}
        ),

        -- Paso 3: Normalizar rutas (case sensitivity) y extraer componentes de fecha
        normalizado AS (
            SELECT
                ID_Bus,
                -- Normalizacion de rutas
                CASE UPPER(Ruta)
                    WHEN '210'  THEN '210'
                    WHEN '210E' THEN '210E'
                    WHEN '502'  THEN '502'
                    WHEN '502C' THEN '502C'
                    WHEN '104'  THEN '104'
                    ELSE UPPER(Ruta)
                END AS Ruta,
                Velocidad_kmh,
                Latitud,
                Longitud,
                Timestamp,
                -- Componentes de fecha/hora
                EXTRACT(DATE FROM Timestamp) AS Fecha,
                EXTRACT(HOUR FROM Timestamp) AS Hora,
                FORMAT_TIMESTAMP('%A', Timestamp) AS DiaSemana,
            FROM validado
        ),

        -- Paso 4: Imputar temperaturas nulas en clima
        clima_limpio AS (
            SELECT
                fecha,
                condicion,
                COALESCE(
                    temperatura_promedio,
                    (SELECT AVG(temperatura_promedio)
                     FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_CLIMA_RAW}`
                     WHERE temperatura_promedio IS NOT NULL)
                ) AS temperatura_promedio
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_CLIMA_RAW}`
        )

        -- Paso 5: Enriquecer con clima + Categorizar congestion
        SELECT
            n.*,
            c.condicion AS Clima_Condicion,
            c.temperatura_promedio AS Clima_Temperatura,
            -- Categorizacion de congestion
            CASE
                WHEN n.Velocidad_kmh >= 30 THEN 'Fluido'
                WHEN n.Velocidad_kmh >= 15 THEN 'Moderado'
                ELSE 'Congestionado'
            END AS Nivel_Congestion
        FROM normalizado n
        LEFT JOIN clima_limpio c
            ON n.Fecha = c.fecha
        """

        client.query(query_limpieza).result()
        tabla_enriquecida = client.get_table(
            f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}"
        )
        log.info(f"  [OK] Tabla enriquecida: {tabla_enriquecida.num_rows} filas")

        # ---------------------------------------------------------------
        # 3.4 ESTADISTICAS POST-LIMPIEZA
        # ---------------------------------------------------------------
        log.info("-" * 40)
        log.info("3.4 ESTADISTICAS POST-LIMPIEZA")

        query_stats = f"""
        SELECT
            COUNT(*) as total_registros,
            COUNT(DISTINCT Ruta) as rutas_unicas,
            COUNT(DISTINCT ID_Bus) as buses_unicos,
            ROUND(AVG(Velocidad_kmh), 2) as vel_promedio,
            COUNTIF(Nivel_Congestion = 'Fluido') as n_fluido,
            COUNTIF(Nivel_Congestion = 'Moderado') as n_moderado,
            COUNTIF(Nivel_Congestion = 'Congestionado') as n_congestionado,
            COUNT(DISTINCT Clima_Condicion) as condiciones_clima
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}`
        """

        result = client.query(query_stats).result()
        for row in result:
            total = row.total_registros
            log.info(f"  Registros finales:      {total}")
            log.info(f"  Rutas unicas:           {row.rutas_unicas}")
            log.info(f"  Buses unicos:           {row.buses_unicos}")
            log.info(f"  Velocidad promedio:     {row.vel_promedio} km/h")
            log.info(f"  Fluido:                 {row.n_fluido} ({row.n_fluido/total*100:.1f}%)")
            log.info(f"  Moderado:               {row.n_moderado} ({row.n_moderado/total*100:.1f}%)")
            log.info(f"  Congestionado:          {row.n_congestionado} ({row.n_congestionado/total*100:.1f}%)")
            log.info(f"  Condiciones climaticas: {row.condiciones_clima}")

        # ---------------------------------------------------------------
        # 3.5 CREAR TABLA AGREGADA POR RUTA Y HORA
        # ---------------------------------------------------------------
        log.info("-" * 40)
        log.info("3.5 AGREGACION POR RUTA Y HORA")

        query_agregacion = f"""
        CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET_ID}.{TABLE_AGREGADO}` AS
        SELECT
            Ruta,
            Hora,
            ROUND(AVG(Velocidad_kmh), 2) AS Velocidad_Promedio,
            ROUND(STDDEV(Velocidad_kmh), 2) AS Velocidad_Std,
            MIN(Velocidad_kmh) AS Velocidad_Min,
            MAX(Velocidad_kmh) AS Velocidad_Max,
            COUNT(DISTINCT ID_Bus) AS Total_Buses,
            COUNT(*) AS Total_Registros
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}`
        GROUP BY Ruta, Hora
        ORDER BY Ruta, Hora
        """

        client.query(query_agregacion).result()
        tabla_agregada = client.get_table(
            f"{PROJECT_ID}.{DATASET_ID}.{TABLE_AGREGADO}"
        )
        log.info(f"  [OK] Tabla agregada: {tabla_agregada.num_rows} grupos ruta-hora")

        registrar_ejecucion("paso3_limpieza", "EXITOSO",
                            f"Enriquecido: {tabla_enriquecida.num_rows}, "
                            f"Agregado: {tabla_agregada.num_rows}")

        return tabla_enriquecida.num_rows

    except Exception as e:
        log.error(f"Error en limpieza/transformacion: {e}")
        registrar_ejecucion("paso3_limpieza", "FALLIDO", str(e))
        raise


# =============================================================================
# PASO 4: EXPORTAR RESULTADOS PARA DASHBOARD
# =============================================================================
def paso4_exportar_resultados(client):
    """
    Exporta los datos procesados de BigQuery a CSV local
    para generar los graficos del dashboard.
    """
    log.info("")
    log.info("=" * 60)
    log.info("PASO 4: EXPORTAR RESULTADOS PARA DASHBOARD")
    log.info("=" * 60)

    try:
        os.makedirs("output/graficos", exist_ok=True)

        # Exportar datos enriquecidos
        log.info("Exportando datos enriquecidos...")
        query_detalle = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}`
        """
        df_detalle = client.query(query_detalle).to_dataframe()
        df_detalle.to_csv("output/datos_enriquecidos.csv", index=False)
        log.info(f"  [OK] output/datos_enriquecidos.csv ({len(df_detalle)} filas)")

        # Exportar datos agregados
        log.info("Exportando datos agregados...")
        query_agregado = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_AGREGADO}`
        """
        df_agregado = client.query(query_agregado).to_dataframe()
        df_agregado.to_csv("output/datos_agregados.csv", index=False)
        log.info(f"  [OK] output/datos_agregados.csv ({len(df_agregado)} filas)")

        # Tambien exportar a GCS (curated layer)
        log.info("Exportando a GCS curated layer...")
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.get_bucket(BUCKET_NAME)

        blob_det = bucket.blob(f"{GCS_CURATED_PREFIX}datos_enriquecidos.csv")
        blob_det.upload_from_filename("output/datos_enriquecidos.csv")

        blob_agr = bucket.blob(f"{GCS_CURATED_PREFIX}datos_agregados.csv")
        blob_agr.upload_from_filename("output/datos_agregados.csv")

        log.info(f"  [OK] Exportado a gs://{BUCKET_NAME}/{GCS_CURATED_PREFIX}")

        registrar_ejecucion("paso4_exportar", "EXITOSO",
                            f"Detalle: {len(df_detalle)}, Agregado: {len(df_agregado)}")

        return df_detalle, df_agregado

    except Exception as e:
        log.error(f"Error exportando resultados: {e}")
        registrar_ejecucion("paso4_exportar", "FALLIDO", str(e))
        raise


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================
def main():
    """Ejecuta el pipeline Batch completo en GCP."""
    log.info("")
    log.info("*" * 60)
    log.info("RED SANTIAGO BIG DATA — PIPELINE BATCH GCP")
    log.info(f"Proyecto: {PROJECT_ID}")
    log.info(f"Region:   {REGION}")
    log.info(f"Inicio:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("*" * 60)

    # Validar configuracion
    if PROJECT_ID == "TU_PROJECT_ID":
        log.error("ERROR: Debe configurar PROJECT_ID en gcp_config.py")
        log.error("En Cloud Shell ejecute: gcloud config get-value project")
        sys.exit(1)

    # PASO 2A: Crear bucket
    bucket = paso2a_crear_bucket()

    # PASO 2B: Subir archivos a GCS
    paso2b_subir_archivos(bucket)

    # PASO 2C: Cargar datos en BigQuery
    bq_client = paso2c_cargar_bigquery()

    # PASO 3: Limpieza y Transformacion en BigQuery
    paso3_limpieza_transformacion(bq_client)

    # PASO 4: Exportar resultados
    df_detalle, df_agregado = paso4_exportar_resultados(bq_client)

    # Resumen final
    log.info("")
    log.info("*" * 60)
    log.info("PIPELINE GCP COMPLETADO EXITOSAMENTE")
    log.info(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("*" * 60)
    log.info("")
    log.info("Recursos GCP creados:")
    log.info(f"  Bucket:   gs://{BUCKET_NAME}/")
    log.info(f"  Dataset:  {PROJECT_ID}.{DATASET_ID}")
    log.info(f"  Tablas:")
    log.info(f"    - {TABLE_GPS_RAW}           (datos crudos GPS)")
    log.info(f"    - {TABLE_CLIMA_RAW}         (datos crudos clima)")
    log.info(f"    - registros_invalidos  (evidencia de limpieza)")
    log.info(f"    - {TABLE_ENRIQUECIDO}  (datos limpios + clima)")
    log.info(f"    - {TABLE_AGREGADO}     (agregado por ruta/hora)")
    log.info("")
    log.info("Siguiente paso: python gcp_dashboard.py")
    log.info("*" * 60)


if __name__ == "__main__":
    main()
