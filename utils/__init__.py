"""
Paquete de utilidades para el pipeline RED Santiago Big Data.
Incluye: logger, validators, error_handler
"""

from utils.logger import PipelineLogger
from utils.validators import DataValidator
from utils.error_handler import manejar_errores, ErrorPipeline
