"""
=============================================================================
RED Santiago Big Data — API de Ingesta en Streaming (Cloud Run)
=============================================================================
Equivalente "buses RED" de la API de votación de Valorant.

En vez de recibir VOTOS, esta API recibe PINGS GPS de buses EN VIVO:
cada bus reporta su posición y velocidad en tiempo real. Por cada ping, la
API ejecuta en línea los 4 aspectos exigidos por el IL 3.2:

  1. NORMALIZACIÓN   -> ruta a forma canónica (502c -> 502C), bus_id, redondeo
  2. VALIDACIÓN+LIMPIEZA+DEDUP -> rangos de velocidad y coordenadas + anti-duplicado
  3. ENRIQUECIMIENTO -> hora, día de semana, nivel de congestión, clima del día
  4. AGREGACIÓN      -> vista analytics_congestion_stream (en BigQuery)

Flujo de un ping:
  POST /api/posicion
     -> validar + normalizar + enriquecer + deduplicar
     -> escribir NDJSON en GCS (Data Lake, capa streaming/)
     -> streaming insert a BigQuery (red_santiago.posiciones_stream)
     -> registrar en red_santiago.api_log

Variables de entorno (se setean en `gcloud run deploy`):
  GCP_PROJECT        ID del proyecto GCP
  BQ_DATASET         dataset BigQuery (default: red_santiago)
  GCS_BUCKET         bucket Data Lake (default: buses_red_2026)
  AUTO_INTERVAL      segundos entre pings del generador automático (default: 2)
  BUSES_POR_TICK     pings generados por ciclo del auto-generador (default: 20)
=============================================================================
"""

import os
import json
import uuid
import random
import threading
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify

# --- Librerías GCP (no fallar el arranque si faltan en local) ---
try:
    from google.cloud import bigquery
    from google.cloud import storage
    _GCP_OK = True
except ImportError:
    _GCP_OK = False

app = Flask(__name__)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
PROJECT_ID = os.environ.get("GCP_PROJECT", "")
BQ_DATASET = os.environ.get("BQ_DATASET", "red_santiago")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "buses_red_2026")
AUTO_INTERVAL = int(os.environ.get("AUTO_INTERVAL", "2"))
BUSES_POR_TICK = int(os.environ.get("BUSES_POR_TICK", "20"))

TABLE_STREAM = f"{PROJECT_ID}.{BQ_DATASET}.posiciones_stream"
TABLE_LOG = f"{PROJECT_ID}.{BQ_DATASET}.api_log"

# --- Reglas de validación (idénticas al batch: config.py) ---
VELOCIDAD_MIN, VELOCIDAD_MAX = 0, 120
LATITUD_MIN, LATITUD_MAX = -33.65, -33.30
LONGITUD_MIN, LONGITUD_MAX = -70.85, -70.50

# --- Normalización de rutas (mismo mapeo que el batch) ---
RUTAS_CANONICAS = {
    "210": "210", "210E": "210E",
    "502": "502", "502C": "502C",
    "104": "104",
}

# --- Catálogo de rutas/buses para el generador automático ---
RUTAS_DEMO = ["210", "210e", "502", "502c", "104"]   # case "sucio" a propósito
BUSES_DEMO = [f"BUS_{1000 + i}" for i in range(1, 51)]

# --- Clientes GCP (perezosos) ---
_bq_client = None
_gcs_bucket = None

# --- Estado en memoria (fallback + métricas para los endpoints GET) ---
_lock = threading.Lock()
_vistos = set()                 # claves de deduplicación (bus_id|minuto)
_metricas = {
    "recibidos": 0,
    "aceptados": 0,
    "rechazados_validacion": 0,
    "rechazados_duplicado": 0,
}
_recientes = []                 # últimas posiciones aceptadas (máx 200)
_auto_on = False

# --- Clima de referencia (semilla local; en prod vendría de clima_raw) ---
_CLIMA_DEMO = {"condicion": "Despejado", "temperatura_promedio": 14.0}


def bq():
    global _bq_client
    if _bq_client is None and _GCP_OK and PROJECT_ID:
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


def gcs():
    global _gcs_bucket
    if _gcs_bucket is None and _GCP_OK and PROJECT_ID:
        _gcs_bucket = storage.Client(project=PROJECT_ID).bucket(GCS_BUCKET)
    return _gcs_bucket


# =============================================================================
# REGISTRO DE ACTIVIDAD (control de ejecución / trazabilidad)
# =============================================================================
def log_evento(event_type, description, status="OK"):
    fila = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "description": description,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client = bq()
    if client:
        try:
            client.insert_rows_json(TABLE_LOG, [fila])
        except Exception as e:
            print(f"[WARN] no se pudo registrar en api_log: {e}")


# =============================================================================
# TRANSFORMACIÓN EN LÍNEA (los 4 aspectos del IL 3.2)
# =============================================================================
def normalizar(ping):
    """Aspecto 1: Normalización. Devuelve dict normalizado o lanza ValueError."""
    bus_id = str(ping.get("bus_id", "")).strip().upper()
    ruta_raw = str(ping.get("ruta", "")).strip()
    ruta = RUTAS_CANONICAS.get(ruta_raw.upper(), ruta_raw.upper())

    if not bus_id or not ruta_raw:
        raise ValueError("bus_id y ruta son obligatorios")

    try:
        velocidad = round(float(ping["velocidad_kmh"]), 1)
        lat = float(ping["latitud"])
        lon = float(ping["longitud"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("velocidad_kmh, latitud y longitud deben ser numéricos")

    return {
        "bus_id": bus_id,
        "ruta": ruta,
        "ruta_raw": ruta_raw,
        "velocidad_kmh": velocidad,
        "latitud": lat,
        "longitud": lon,
    }


def validar(d):
    """Aspecto 2a: Validación + limpieza. Lanza ValueError si está fuera de rango."""
    if not (VELOCIDAD_MIN <= d["velocidad_kmh"] <= VELOCIDAD_MAX):
        raise ValueError(f"velocidad fuera de rango ({d['velocidad_kmh']})")
    if not (LATITUD_MIN <= d["latitud"] <= LATITUD_MAX):
        raise ValueError(f"latitud fuera de Santiago ({d['latitud']})")
    if not (LONGITUD_MIN <= d["longitud"] <= LONGITUD_MAX):
        raise ValueError(f"longitud fuera de Santiago ({d['longitud']})")


def es_duplicado(d, ts):
    """Aspecto 2b: Deduplicación. Un bus no puede tener 2 pings en el mismo minuto."""
    clave = f"{d['bus_id']}|{ts[:16]}"   # YYYY-MM-DDTHH:MM
    with _lock:
        if clave in _vistos:
            return True
        _vistos.add(clave)
        if len(_vistos) > 50000:          # acotar memoria
            _vistos.clear()
    return False


def enriquecer(d, ts):
    """Aspecto 3: Enriquecimiento. Agrega hora, día, congestión y clima."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if d["velocidad_kmh"] >= 30:
        nivel = "Fluido"
    elif d["velocidad_kmh"] >= 15:
        nivel = "Moderado"
    else:
        nivel = "Congestionado"

    dias = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]
    d.update({
        "hora": dt.hour,
        "dia_semana": dias[dt.weekday()],
        "nivel_congestion": nivel,
        "clima_condicion": _CLIMA_DEMO["condicion"],
        "clima_temperatura": _CLIMA_DEMO["temperatura_promedio"],
        "ingest_timestamp": ts,
        "viaje_id": str(uuid.uuid4()),
    })
    return d


# =============================================================================
# PERSISTENCIA: GCS (Data Lake) + BigQuery (streaming insert)
# =============================================================================
def escribir_gcs(registro):
    bucket = gcs()
    if not bucket:
        return
    try:
        ts = registro["ingest_timestamp"].replace(":", "").replace("-", "")
        path = f"streaming/posiciones/{ts[:8]}/{registro['viaje_id']}.json"
        bucket.blob(path).upload_from_string(
            json.dumps(registro, ensure_ascii=False),
            content_type="application/json",
        )
    except Exception as e:
        print(f"[WARN] no se pudo escribir en GCS: {e}")


def insertar_bigquery(registro):
    client = bq()
    if not client:
        return
    try:
        errores = client.insert_rows_json(TABLE_STREAM, [registro])
        if errores:
            print(f"[WARN] BigQuery rechazó filas: {errores}")
    except Exception as e:
        print(f"[WARN] no se pudo insertar en BigQuery: {e}")


def procesar_ping(ping):
    """Orquesta los 4 aspectos + persistencia. Devuelve (ok, mensaje, registro)."""
    with _lock:
        _metricas["recibidos"] += 1
    ts = datetime.now(timezone.utc).isoformat()

    # 1) Normalizar
    try:
        d = normalizar(ping)
    except ValueError as e:
        with _lock:
            _metricas["rechazados_validacion"] += 1
        log_evento("posicion_rechazada", f"normalizacion: {e}", "ERROR")
        return False, str(e), None

    # 2a) Validar
    try:
        validar(d)
    except ValueError as e:
        with _lock:
            _metricas["rechazados_validacion"] += 1
        log_evento("posicion_rechazada", f"validacion: {e}", "ERROR")
        return False, str(e), None

    # 2b) Deduplicar
    if es_duplicado(d, ts):
        with _lock:
            _metricas["rechazados_duplicado"] += 1
        log_evento("posicion_duplicada", f"{d['bus_id']} en {ts[:16]}", "WARN")
        return False, "duplicado (mismo bus, mismo minuto)", None

    # 3) Enriquecer
    registro = enriquecer(d, ts)

    # Persistir (Data Lake + Warehouse)
    escribir_gcs(registro)
    insertar_bigquery(registro)

    with _lock:
        _metricas["aceptados"] += 1
        _recientes.append(registro)
        if len(_recientes) > 200:
            _recientes.pop(0)

    return True, "ok", registro


# =============================================================================
# GENERADOR AUTOMÁTICO (simula buses reportando en vivo)
# =============================================================================
def generar_ping_aleatorio():
    return {
        "bus_id": random.choice(BUSES_DEMO),
        "ruta": random.choice(RUTAS_DEMO),
        # 5% de velocidades inválidas para demostrar la validación
        "velocidad_kmh": (random.randint(0, 70)
                          if random.random() > 0.05
                          else random.choice([-5, 999])),
        "latitud": round(random.uniform(LATITUD_MIN, LATITUD_MAX), 6),
        "longitud": round(random.uniform(LONGITUD_MIN, LONGITUD_MAX), 6),
    }


def _auto_loop():
    global _auto_on
    while _auto_on:
        for _ in range(BUSES_POR_TICK):
            procesar_ping(generar_ping_aleatorio())
        time.sleep(AUTO_INTERVAL)


# =============================================================================
# ENDPOINTS
# =============================================================================
@app.route("/")
def home():
    return jsonify({
        "servicio": "RED Santiago — Ingesta GPS en Streaming",
        "proyecto": PROJECT_ID or "(sin GCP en local)",
        "dataset": BQ_DATASET,
        "bucket": GCS_BUCKET,
        "auto_generador": _auto_on,
        "metricas": _metricas,
        "endpoints": {
            "POST /api/posicion": "ingestar un ping GPS",
            "POST /api/auto/start": "iniciar generador automático",
            "POST /api/auto/stop": "detener generador automático",
            "GET  /api/posiciones/recientes": "últimas posiciones aceptadas",
            "GET  /api/congestion/resumen": "resumen de congestión en vivo",
            "GET  /api/metricas": "contadores de ingesta",
        },
    })


@app.route("/api/posicion", methods=["POST"])
def api_posicion():
    ping = request.get_json(silent=True) or {}
    ok, msg, registro = procesar_ping(ping)
    if ok:
        return jsonify({"status": "aceptado", "registro": registro}), 201
    return jsonify({"status": "rechazado", "motivo": msg}), 422


@app.route("/api/auto/start", methods=["POST"])
def api_auto_start():
    global _auto_on
    if _auto_on:
        return jsonify({"status": "ya estaba activo"}), 200
    _auto_on = True
    threading.Thread(target=_auto_loop, daemon=True).start()
    log_evento("auto_start", f"intervalo={AUTO_INTERVAL}s buses={BUSES_POR_TICK}")
    return jsonify({"status": "generador iniciado",
                    "intervalo_s": AUTO_INTERVAL,
                    "buses_por_tick": BUSES_POR_TICK}), 200


@app.route("/api/auto/stop", methods=["POST"])
def api_auto_stop():
    global _auto_on
    _auto_on = False
    log_evento("auto_stop", "generador detenido")
    return jsonify({"status": "generador detenido"}), 200


@app.route("/api/posiciones/recientes")
def api_recientes():
    with _lock:
        return jsonify(_recientes[-50:])


@app.route("/api/metricas")
def api_metricas():
    with _lock:
        return jsonify(dict(_metricas))


@app.route("/api/congestion/resumen")
def api_congestion():
    """Resumen en vivo desde BigQuery; si no hay GCP, usa memoria local."""
    client = bq()
    if client:
        sql = f"""
        SELECT ruta, nivel_congestion, COUNT(*) AS pings,
               ROUND(AVG(velocidad_kmh), 1) AS vel_promedio
        FROM `{TABLE_STREAM}`
        GROUP BY ruta, nivel_congestion
        ORDER BY ruta, nivel_congestion
        """
        try:
            filas = [dict(r) for r in client.query(sql).result()]
            return jsonify({"fuente": "bigquery", "resumen": filas})
        except Exception as e:
            return jsonify({"fuente": "error_bq", "detalle": str(e)}), 200

    # Fallback en memoria
    with _lock:
        agg = {}
        for r in _recientes:
            k = (r["ruta"], r["nivel_congestion"])
            agg.setdefault(k, []).append(r["velocidad_kmh"])
    resumen = [
        {"ruta": k[0], "nivel_congestion": k[1], "pings": len(v),
         "vel_promedio": round(sum(v) / len(v), 1)}
        for k, v in sorted(agg.items())
    ]
    return jsonify({"fuente": "memoria", "resumen": resumen})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
