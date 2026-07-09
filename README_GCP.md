# RED Santiago Big Data — Pipeline en GCP

## 1. Subir archivos al bucket

```bash
gcloud storage cp historial_rutas_DTPM.csv gs://buses_red_2026/raw/
gcloud storage cp clima_santiago.json gs://buses_red_2026/raw/
```

## 2. Verificar archivos

```bash
gcloud storage ls gs://buses_red_2026/raw/
```

## 3. Convertir clima JSON a NDJSON (formato BigQuery)

```bash
gcloud storage cp gs://buses_red_2026/raw/clima_santiago.json ./clima_santiago.json
jq -c '.[]' clima_santiago.json > clima_ndjson.json
gcloud storage cp clima_ndjson.json gs://buses_red_2026/raw/
```

## 4. Crear dataset en BigQuery

```bash
bq mk --dataset --location=US-WEST1 red_santiago
```

## 5. Cargar datos a BigQuery

```bash
bq load --skip_leading_rows=1 --autodetect --source_format=CSV red_santiago.gps_raw gs://buses_red_2026/raw/historial_rutas_DTPM.csv

bq load --autodetect --source_format=NEWLINE_DELIMITED_JSON red_santiago.clima_raw gs://buses_red_2026/raw/clima_ndjson.json
```

## 6. Verificar tablas

```bash
bq ls red_santiago
bq head red_santiago.gps_raw
bq head red_santiago.clima_raw
```

## 7. Modelo Estrella (Star Schema)

### Dimensiones

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.dim_ruta AS
SELECT DISTINCT
    UPPER(Ruta) as ruta_id,
    UPPER(Ruta) as nombre_ruta
FROM red_santiago.gps_raw;
'

bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.dim_bus AS
SELECT DISTINCT
    ID_Bus as bus_id,
    ID_Bus as codigo_bus
FROM red_santiago.gps_raw;
'

bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.dim_fecha AS
SELECT DISTINCT
    EXTRACT(DATE FROM Timestamp) as fecha_id,
    EXTRACT(YEAR FROM Timestamp) as anio,
    EXTRACT(MONTH FROM Timestamp) as mes,
    EXTRACT(DAY FROM Timestamp) as dia,
    EXTRACT(HOUR FROM Timestamp) as hora,
    FORMAT_TIMESTAMP("%A", Timestamp) as dia_semana
FROM red_santiago.gps_raw;
'

bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.dim_clima AS
SELECT DISTINCT
    GENERATE_UUID() as clima_id,
    fecha,
    condicion,
    temperatura_promedio
FROM red_santiago.clima_raw;
'
```

### Fact Table

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.fact_viajes AS
SELECT
    GENERATE_UUID() as viaje_id,
    UPPER(g.Ruta) as ruta_id,
    g.ID_Bus as bus_id,
    EXTRACT(DATE FROM g.Timestamp) as fecha_id,
    c.clima_id,
    g.Velocidad_kmh,
    g.Latitud,
    g.Longitud,
    g.Timestamp,
    CASE
        WHEN g.Velocidad_kmh >= 30 THEN "Fluido"
        WHEN g.Velocidad_kmh >= 15 THEN "Moderado"
        ELSE "Congestionado"
    END as nivel_congestion
FROM red_santiago.gps_raw g
LEFT JOIN red_santiago.dim_clima c
    ON EXTRACT(DATE FROM g.Timestamp) = c.fecha;
'
```

## 8. Detección de errores (duplicados y nulos)

```bash
bq query --use_legacy_sql=false '
SELECT
    COUNT(*) as total_registros,
    COUNTIF(Velocidad_kmh IS NULL) as nulos_velocidad,
    COUNTIF(Latitud IS NULL OR Longitud IS NULL) as nulos_coordenadas,
    COUNTIF(Timestamp IS NULL) as nulos_timestamp,
    COUNT(*) - COUNT(DISTINCT CONCAT(ID_Bus, Ruta, CAST(Velocidad_kmh AS STRING), CAST(Latitud AS STRING), CAST(Longitud AS STRING), CAST(Timestamp AS STRING))) as duplicados
FROM red_santiago.gps_raw;
'

bq query --use_legacy_sql=false '
SELECT
    COUNT(*) as total_registros,
    COUNTIF(temperatura_promedio IS NULL) as nulos_temperatura,
    COUNTIF(condicion IS NULL) as nulos_condicion,
    COUNTIF(fecha IS NULL) as nulos_fecha
FROM red_santiago.clima_raw;
'
```

## 9. Imputar nulos en clima

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.clima_limpio AS
SELECT
    fecha,
    condicion,
    CASE
        WHEN temperatura_promedio IS NULL
        THEN (SELECT ROUND(AVG(temperatura_promedio), 1) FROM red_santiago.clima_raw)
        ELSE temperatura_promedio
    END as temperatura_promedio
FROM red_santiago.clima_raw;
'
```

## 10. Transformación de datos

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.datos_transformados AS
SELECT
    ID_Bus,
    UPPER(Ruta) as ruta_normalizada,
    Velocidad_kmh,
    Latitud,
    Longitud,
    Timestamp,
    EXTRACT(DATE FROM Timestamp) as fecha,
    EXTRACT(HOUR FROM Timestamp) as hora,
    FORMAT_TIMESTAMP("%A", Timestamp) as dia_semana,
    CASE
        WHEN Velocidad_kmh >= 30 THEN "Fluido"
        WHEN Velocidad_kmh >= 15 THEN "Moderado"
        ELSE "Congestionado"
    END as nivel_congestion
FROM red_santiago.gps_raw;
'
```

## 11. Enriquecer con clima

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.datos_enriquecidos AS
SELECT
    t.*,
    c.condicion as clima_condicion,
    c.temperatura_promedio as clima_temperatura
FROM red_santiago.datos_transformados t
LEFT JOIN red_santiago.clima_limpio c
    ON t.fecha = c.fecha;
'
```

## 12. Agregación por ruta y hora

```bash
bq query --use_legacy_sql=false '
CREATE OR REPLACE TABLE red_santiago.datos_agregados AS
SELECT
    ruta_normalizada as ruta,
    hora,
    ROUND(AVG(Velocidad_kmh), 2) as velocidad_promedio,
    ROUND(STDDEV(Velocidad_kmh), 2) as velocidad_std,
    MIN(Velocidad_kmh) as velocidad_min,
    MAX(Velocidad_kmh) as velocidad_max,
    COUNT(DISTINCT ID_Bus) as total_buses,
    COUNT(*) as total_registros
FROM red_santiago.datos_enriquecidos
GROUP BY ruta, hora
ORDER BY ruta, hora;
'
```

## 13. Verificar resultados finales

```bash
bq ls red_santiago
bq query --use_legacy_sql=false 'SELECT * FROM red_santiago.datos_agregados LIMIT 20'
bq head red_santiago.datos_enriquecidos
```

## 14. Dashboard en Looker Studio

**Link:** https://lookerstudio.google.com

Conectar BigQuery → proyecto → dataset `red_santiago` → tabla `fact_viajes`.

| Gráfico | Dimensión | Métrica |
|---|---|---|
| Tabla | `ruta_id` | COUNT(`viaje_id`), AVG(`Velocidad_kmh`), MIN(`Velocidad_kmh`) |
| Barras apiladas | `ruta_id` desglosado por `nivel_congestion` | COUNT(`viaje_id`) |
| Barras | `nivel_congestion` | COUNT(`viaje_id`) |
| Boxplot | `nivel_congestion` | `Velocidad_kmh` |

### Nombre del Dashboard
`RED Santiago - Análisis de Congestión del Transporte Público`

### Nombres de los gráficos
1. **Boxplot**: `Distribución de Velocidad por Nivel de Congestión`
2. **Barras**: `Total de Registros por Nivel de Congestión`
3. **Barras apiladas**: `Distribución de Congestión por Ruta`
4. **Tabla**: `Ranking de Rutas - Velocidad y Volumen`

## 15. Limpiar dataset (si es necesario)

```bash
bq rm -r -f red_santiago
```
