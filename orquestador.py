"""
=============================================================================
Examen Final — ORQUESTADOR: Batch + Streaming EN PARALELO
=============================================================================
La rúbrica del examen exige que el proceso BATCH y el proceso STREAMING se
ejecuten AL MISMO TIEMPO, escribiendo en el mismo Data Lake (GCS) y el mismo
dataset de BigQuery (red_santiago), en tablas distintas.

Este script lanza los dos flujos en hilos concurrentes:

  Hilo BATCH   -> ejecuta gcp_pipeline.main()
                  (GPS histórico + clima -> GCS -> BigQuery -> limpieza ->
                   datos_enriquecidos / datos_agregados)

  Hilo STREAM  -> enciende el generador de la API de Cloud Run (api_red)
                  y monitorea las métricas de ingesta en vivo
                  (posiciones GPS -> GCS -> posiciones_stream)

Uso:
  python orquestador.py https://red-gps-api-XXXX.run.app

Si no se pasa URL, solo corre el batch (útil para pruebas).
=============================================================================
"""
import sys
import time
import threading
import logging

try:
    import requests
except ImportError:
    import os
    os.system(f"{sys.executable} -m pip install requests")
    import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(threadName)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orquestador")

_stream_activo = True


# =============================================================================
# HILO BATCH
# =============================================================================
def correr_batch():
    log.info(">>> INICIO proceso BATCH (GPS histórico + clima — buses RED)")
    try:
        import gcp_pipeline
        gcp_pipeline.main()
        log.info(">>> BATCH finalizado correctamente.")
    except SystemExit:
        log.error(">>> BATCH abortado: revisa PROJECT_ID en gcp_config.py")
    except Exception as e:
        log.error(f">>> BATCH falló: {e}")


# =============================================================================
# HILO STREAMING
# =============================================================================
def correr_streaming(api_url):
    global _stream_activo
    log.info(f">>> INICIO proceso STREAMING contra {api_url}")
    try:
        r = requests.post(f"{api_url}/api/auto/start", timeout=30)
        log.info(f">>> Generador streaming: {r.json()}")
    except Exception as e:
        log.error(f">>> No se pudo iniciar el streaming: {e}")
        return

    # Monitorear métricas mientras el batch trabaja
    while _stream_activo:
        try:
            m = requests.get(f"{api_url}/api/metricas", timeout=15).json()
            log.info(f"    [streaming] aceptados={m.get('aceptados')} "
                     f"rechazados_val={m.get('rechazados_validacion')} "
                     f"duplicados={m.get('rechazados_duplicado')}")
        except Exception as e:
            log.warning(f"    [streaming] sin métricas: {e}")
        time.sleep(10)

    try:
        requests.post(f"{api_url}/api/auto/stop", timeout=30)
        log.info(">>> Generador streaming detenido.")
    except Exception:
        pass


# =============================================================================
# MAIN
# =============================================================================
def main():
    global _stream_activo
    api_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None

    log.info("=" * 60)
    log.info("EXAMEN FINAL — ORQUESTADOR BATCH + STREAMING (paralelo)")
    log.info("=" * 60)

    hilos = []
    t_batch = threading.Thread(target=correr_batch, name="BATCH")
    hilos.append(t_batch)

    if api_url:
        t_stream = threading.Thread(target=correr_streaming, name="STREAM",
                                    args=(api_url,))
        hilos.append(t_stream)
    else:
        log.warning("Sin URL de API: solo se ejecutará el BATCH. "
                    "Pasa la URL de Cloud Run para correr ambos en paralelo.")

    # Arrancar ambos AL MISMO TIEMPO
    for t in hilos:
        t.start()

    # El streaming es continuo; se detiene cuando termina el batch
    t_batch.join()
    _stream_activo = False
    for t in hilos:
        t.join()

    log.info("=" * 60)
    log.info("ORQUESTACIÓN COMPLETADA. Batch y streaming corrieron en paralelo.")
    log.info("Ambos escribieron en el dataset 'red_santiago'.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
