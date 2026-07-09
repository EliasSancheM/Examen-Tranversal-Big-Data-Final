"""
=============================================================================
RED Santiago Big Data — Control de Errores
=============================================================================
Control técnico requerido por rúbrica:
  - Manejar fallos en cada etapa del pipeline
  - Implementar try/catch para que el proceso no se detenga
  - Registrar errores con contexto
=============================================================================
"""

import functools
import traceback


class ErrorPipeline(Exception):
    """Excepción personalizada para errores del pipeline."""

    def __init__(self, etapa, mensaje, datos_contexto=None):
        self.etapa = etapa
        self.mensaje = mensaje
        self.datos_contexto = datos_contexto or {}
        super().__init__(f"[{etapa}] {mensaje}")


def manejar_errores(etapa_nombre, logger=None, continuar_en_error=True):
    """
    Decorador para manejar errores en funciones del pipeline.
    
    Implementa try/catch automático para que el pipeline no se detenga
    ante un error puntual (requerido por rúbrica).
    
    Args:
        etapa_nombre: Nombre descriptivo de la etapa
        logger: Instancia de PipelineLogger (opcional)
        continuar_en_error: Si True, retorna None en vez de propagar el error
    
    Uso:
        @manejar_errores("limpieza_datos", logger=mi_logger)
        def limpiar_datos(df):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Obtener logger del primer argumento si es un objeto con .log
            log = logger

            if log:
                log.registrar_etapa(etapa_nombre, "INICIO")

            try:
                resultado = func(*args, **kwargs)

                if log:
                    log.registrar_etapa(etapa_nombre, "FIN")

                return resultado

            except ErrorPipeline as e:
                msg_error = (
                    f"Error controlado en '{etapa_nombre}': {e.mensaje} "
                    f"| Contexto: {e.datos_contexto}"
                )
                if log:
                    log.error(msg_error)
                    log.registrar_etapa(etapa_nombre, "ERROR",
                                        {"tipo": "ErrorPipeline", "mensaje": str(e)})
                else:
                    print(f"[ERROR] {msg_error}")

                if continuar_en_error:
                    return None
                raise

            except Exception as e:
                msg_error = (
                    f"Error inesperado en '{etapa_nombre}': {type(e).__name__}: {e}"
                )
                detalle = traceback.format_exc()

                if log:
                    log.error(msg_error)
                    log.debug(f"Traceback completo:\n{detalle}")
                    log.registrar_etapa(etapa_nombre, "ERROR",
                                        {"tipo": type(e).__name__, "mensaje": str(e)})
                else:
                    print(f"[ERROR] {msg_error}")

                if continuar_en_error:
                    return None
                raise

        return wrapper
    return decorator


class ManejadorErroresBatch:
    """
    Manejador de errores a nivel de registro individual.
    
    Permite procesar registros uno a uno, registrando los que fallan
    sin detener el procesamiento del lote completo.
    """

    def __init__(self, logger=None):
        self.logger = logger
        self.errores = []
        self.total_procesados = 0
        self.total_fallidos = 0

    def procesar_registro(self, func, registro, indice=None):
        """
        Procesa un registro individual con manejo de errores.
        
        Args:
            func: Función que procesa el registro
            registro: Datos del registro
            indice: Índice del registro (para referencia)
        
        Returns:
            Resultado de func(registro) o None si falló
        """
        self.total_procesados += 1
        try:
            return func(registro)
        except Exception as e:
            self.total_fallidos += 1
            error_info = {
                "indice": indice,
                "error": str(e),
                "tipo": type(e).__name__,
            }
            self.errores.append(error_info)
            if self.logger:
                self.logger.debug(
                    f"Error en registro {indice}: {type(e).__name__}: {e}"
                )
            return None

    def resumen(self):
        """Retorna resumen de procesamiento."""
        return {
            "total_procesados": self.total_procesados,
            "total_exitosos": self.total_procesados - self.total_fallidos,
            "total_fallidos": self.total_fallidos,
            "tasa_error": (
                f"{(self.total_fallidos/self.total_procesados*100):.1f}%"
                if self.total_procesados > 0 else "N/A"
            ),
            "errores_detalle": self.errores[:10],  # Solo primeros 10
        }
