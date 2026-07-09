-- ============================================================================
-- RED Santiago — Setup BigQuery para la capa STREAMING
-- ============================================================================
-- Crea las tablas que la API de Cloud Run necesita para el streaming insert,
-- la tabla de log, la vista analítica (AGREGACIÓN en vivo) y las vistas de
-- control de calidad (data quality).
--
-- Ejecutar con:
--   cat setup_bq_red.sql | bq query --nouse_legacy_sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Tabla de posiciones en streaming (destino del insert de la API)
--    Ya viene NORMALIZADA y ENRIQUECIDA desde la API (IL 3.2).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `red_santiago.posiciones_stream` (
  viaje_id           STRING    NOT NULL,
  bus_id             STRING    NOT NULL,
  ruta               STRING,        -- ruta canónica (502C)
  ruta_raw           STRING,        -- ruta original recibida (502c)
  velocidad_kmh      FLOAT64,
  latitud            FLOAT64,
  longitud           FLOAT64,
  hora               INT64,
  dia_semana         STRING,
  nivel_congestion   STRING,        -- Fluido / Moderado / Congestionado
  clima_condicion    STRING,
  clima_temperatura  FLOAT64,
  ingest_timestamp   TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 2. Tabla de log de actividad de la API (trazabilidad / registro)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `red_santiago.api_log` (
  event_id     STRING,
  event_type   STRING,
  description  STRING,
  status       STRING,
  created_at   TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 3. Vista analítica para el dashboard (AGREGACIÓN en vivo por ruta y hora)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW `red_santiago.analytics_congestion_stream` AS
SELECT
  ruta,
  hora,
  nivel_congestion,
  clima_condicion,
  COUNT(*)                       AS total_pings,
  COUNT(DISTINCT bus_id)         AS buses_unicos,
  ROUND(AVG(velocidad_kmh), 2)   AS velocidad_promedio,
  ROUND(MIN(velocidad_kmh), 2)   AS velocidad_min,
  ROUND(MAX(velocidad_kmh), 2)   AS velocidad_max
FROM `red_santiago.posiciones_stream`
GROUP BY ruta, hora, nivel_congestion, clima_condicion;

-- ---------------------------------------------------------------------------
-- 4. Vistas de control de calidad (Data Quality)
-- ---------------------------------------------------------------------------

-- 4.1 Posibles duplicados: mismo bus, misma ruta, mismo minuto
CREATE OR REPLACE VIEW `red_santiago.v_dq_duplicados` AS
SELECT
  bus_id,
  ruta,
  TIMESTAMP_TRUNC(ingest_timestamp, MINUTE) AS minuto,
  COUNT(*) AS apariciones
FROM `red_santiago.posiciones_stream`
GROUP BY bus_id, ruta, minuto
HAVING COUNT(*) > 1;

-- 4.2 Velocidades anómalas que se hubieran colado (la API ya las filtra)
CREATE OR REPLACE VIEW `red_santiago.v_dq_velocidad_anomala` AS
SELECT *
FROM `red_santiago.posiciones_stream`
WHERE velocidad_kmh < 0 OR velocidad_kmh > 120;

-- 4.3 Coordenadas fuera del bounding box de Santiago
CREATE OR REPLACE VIEW `red_santiago.v_dq_fuera_santiago` AS
SELECT *
FROM `red_santiago.posiciones_stream`
WHERE latitud  NOT BETWEEN -33.65 AND -33.30
   OR longitud NOT BETWEEN -70.85 AND -70.50;
