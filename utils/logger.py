"""
=============================================================================
RED Santiago Big Data — Sistema de Registro de Actividad (Logging)
=============================================================================
Control técnico requerido por rúbrica:
  - Llevar log de ejecuciones
  - Definir si un proceso ejecutado puede re-ejecutarse
  - Registrar actividad con trazabilidad completa
=============================================================================
"""

import logging
import os
import json
from datetime import datetime


class PipelineLogger:
    """
    Sistema de logging para el pipeline Batch.
    
    Registra toda la actividad del pipeline en archivo y consola,
    incluyendo control de re-ejecución.
    """

    def __init__(self, nombre_modulo="pipeline", logs_dir=None):
        """
        Inicializa el logger con archivo de log por fecha.
        
        Args:
            nombre_modulo: Nombre del módulo que genera los logs
            logs_dir: Directorio donde guardar los logs
        """
        if logs_dir is None:
            from config import LOGS_DIR
            logs_dir = LOGS_DIR

        os.makedirs(logs_dir, exist_ok=True)

        # Archivo de log con fecha
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(logs_dir, f"pipeline_{fecha_hoy}.log")

        # Archivo de estado de ejecuciones
        self.estado_file = os.path.join(logs_dir, "estado_ejecuciones.json")

        # Configurar logger
        self.logger = logging.getLogger(nombre_modulo)
        self.logger.setLevel(logging.DEBUG)

        # Evitar duplicar handlers si ya existen
        if not self.logger.handlers:
            # Handler de archivo
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setLevel(logging.DEBUG)

            # Handler de consola
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)

            # Formato
            from config import LOG_FORMAT, LOG_DATE_FORMAT
            formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
            fh.setFormatter(formatter)
            ch.setFormatter(formatter)

            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

        self.logger.info(f"Logger inicializado para modulo: {nombre_modulo}")

    def info(self, mensaje):
        """Registra mensaje informativo."""
        self.logger.info(mensaje)

    def warning(self, mensaje):
        """Registra advertencia."""
        self.logger.warning(mensaje)

    def error(self, mensaje):
        """Registra error."""
        self.logger.error(mensaje)

    def debug(self, mensaje):
        """Registra detalle de depuración."""
        self.logger.debug(mensaje)

    def registrar_etapa(self, etapa, estado, detalles=None):
        """
        Registra el inicio/fin de una etapa del pipeline.
        
        Args:
            etapa: Nombre de la etapa (ej: 'ingesta', 'limpieza')
            estado: 'INICIO', 'FIN', 'ERROR'
            detalles: Diccionario con métricas o detalles adicionales
        """
        msg = f"[ETAPA: {etapa}] Estado: {estado}"
        if detalles:
            msg += f" | Detalles: {json.dumps(detalles, ensure_ascii=False)}"
        
        if estado == 'ERROR':
            self.logger.error(msg)
        else:
            self.logger.info(msg)

    def puede_ejecutar(self, proceso_id):
        """
        Verifica si un proceso puede ejecutarse (control de re-ejecución).
        
        Args:
            proceso_id: Identificador único del proceso
            
        Returns:
            tuple: (puede_ejecutar: bool, ultimo_run: str o None)
        """
        estado = self._cargar_estado()
        
        if proceso_id in estado:
            ultimo_run = estado[proceso_id].get("ultima_ejecucion", "desconocido")
            resultado = estado[proceso_id].get("resultado", "desconocido")
            self.logger.warning(
                f"Proceso '{proceso_id}' ya fue ejecutado el {ultimo_run} "
                f"con resultado: {resultado}. Se re-ejecutara."
            )
            return True, ultimo_run
        
        return True, None

    def registrar_ejecucion(self, proceso_id, resultado, registros_procesados=0):
        """
        Registra que un proceso fue ejecutado.
        
        Args:
            proceso_id: Identificador único del proceso
            resultado: 'EXITOSO' o 'FALLIDO'
            registros_procesados: Cantidad de registros procesados
        """
        estado = self._cargar_estado()
        estado[proceso_id] = {
            "ultima_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "resultado": resultado,
            "registros_procesados": registros_procesados,
        }
        self._guardar_estado(estado)
        self.logger.info(
            f"Ejecucion registrada: {proceso_id} -> {resultado} "
            f"({registros_procesados} registros)"
        )

    def _cargar_estado(self):
        """Carga el estado de ejecuciones desde archivo JSON."""
        if os.path.exists(self.estado_file):
            try:
                with open(self.estado_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _guardar_estado(self, estado):
        """Guarda el estado de ejecuciones en archivo JSON."""
        with open(self.estado_file, 'w', encoding='utf-8') as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
