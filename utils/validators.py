"""
=============================================================================
RED Santiago Big Data — Validación de Datos
=============================================================================
Control técnico requerido por rúbrica:
  - Validar datos y procesos manteniendo trazabilidad desde el origen
  - Permitir reprocesar datos históricos en fechas específicas
  - Validación de rangos, tipos y formatos
=============================================================================
"""

import pandas as pd
from datetime import datetime


class DataValidator:
    """
    Validador de datos con trazabilidad completa.
    
    Valida registros individualmente y genera un reporte detallado
    de registros inválidos con la razón del rechazo.
    """

    def __init__(self, logger=None):
        self.logger = logger
        self.registros_invalidos = []
        self.conteo_por_regla = {}

    def validar_rango(self, df, columna, valor_min, valor_max, nombre_regla=None):
        """
        Valida que los valores de una columna estén dentro de un rango.
        
        Args:
            df: DataFrame a validar
            columna: Nombre de la columna
            valor_min: Valor mínimo aceptable
            valor_max: Valor máximo aceptable
            nombre_regla: Nombre descriptivo de la regla
            
        Returns:
            tuple: (df_validos, df_invalidos)
        """
        regla = nombre_regla or f"rango_{columna}"
        
        mask_invalidos = (df[columna] < valor_min) | (df[columna] > valor_max)
        df_invalidos = df[mask_invalidos].copy()
        df_validos = df[~mask_invalidos].copy()

        n_invalidos = len(df_invalidos)
        self.conteo_por_regla[regla] = n_invalidos

        if n_invalidos > 0:
            self._registrar_invalidos(df_invalidos, regla,
                f"Valor fuera de rango [{valor_min}, {valor_max}] en '{columna}'")
            if self.logger:
                self.logger.warning(
                    f"Validacion '{regla}': {n_invalidos} registros fuera de rango "
                    f"[{valor_min}, {valor_max}] en columna '{columna}'"
                )

        return df_validos, df_invalidos

    def validar_nulos(self, df, columnas, nombre_regla=None):
        """
        Detecta registros con valores nulos en columnas específicas.
        
        Args:
            df: DataFrame a validar
            columnas: Lista de columnas a verificar
            nombre_regla: Nombre descriptivo de la regla
            
        Returns:
            tuple: (df_sin_nulos, df_con_nulos)
        """
        regla = nombre_regla or f"nulos_{'_'.join(columnas)}"

        mask_nulos = df[columnas].isnull().any(axis=1)
        df_con_nulos = df[mask_nulos].copy()
        df_sin_nulos = df[~mask_nulos].copy()

        n_nulos = len(df_con_nulos)
        self.conteo_por_regla[regla] = n_nulos

        if n_nulos > 0:
            self._registrar_invalidos(df_con_nulos, regla,
                f"Valores nulos encontrados en columnas: {columnas}")
            if self.logger:
                self.logger.warning(
                    f"Validacion '{regla}': {n_nulos} registros con nulos "
                    f"en columnas {columnas}"
                )

        return df_sin_nulos, df_con_nulos

    def validar_duplicados(self, df, columnas_clave=None, nombre_regla=None):
        """
        Detecta registros duplicados.
        
        Args:
            df: DataFrame a validar
            columnas_clave: Columnas para determinar duplicados (None = todas)
            nombre_regla: Nombre descriptivo de la regla
            
        Returns:
            tuple: (df_sin_duplicados, df_duplicados)
        """
        regla = nombre_regla or "duplicados"

        if columnas_clave:
            mask_dup = df.duplicated(subset=columnas_clave, keep='first')
        else:
            mask_dup = df.duplicated(keep='first')

        df_duplicados = df[mask_dup].copy()
        df_sin_dup = df[~mask_dup].copy()

        n_dup = len(df_duplicados)
        self.conteo_por_regla[regla] = n_dup

        if n_dup > 0:
            self._registrar_invalidos(df_duplicados, regla,
                f"Registros duplicados detectados")
            if self.logger:
                self.logger.warning(
                    f"Validacion '{regla}': {n_dup} registros duplicados detectados"
                )

        return df_sin_dup, df_duplicados

    def validar_coordenadas(self, df, col_lat, col_lon,
                            lat_min, lat_max, lon_min, lon_max,
                            nombre_regla=None):
        """
        Valida que las coordenadas estén dentro del bounding box de Santiago.
        
        Returns:
            tuple: (df_validos, df_invalidos)
        """
        regla = nombre_regla or "coordenadas_santiago"

        mask_invalidos = (
            (df[col_lat] < lat_min) | (df[col_lat] > lat_max) |
            (df[col_lon] < lon_min) | (df[col_lon] > lon_max)
        )

        df_invalidos = df[mask_invalidos].copy()
        df_validos = df[~mask_invalidos].copy()

        n_invalidos = len(df_invalidos)
        self.conteo_por_regla[regla] = n_invalidos

        if n_invalidos > 0:
            self._registrar_invalidos(df_invalidos, regla,
                f"Coordenadas fuera de Santiago")
            if self.logger:
                self.logger.warning(
                    f"Validacion '{regla}': {n_invalidos} registros con "
                    f"coordenadas fuera de Santiago"
                )

        return df_validos, df_invalidos

    def validar_formato_fecha(self, df, columna, formato="%Y-%m-%d %H:%M:%S",
                               nombre_regla=None):
        """
        Valida que los valores de fecha tengan el formato correcto.
        
        Returns:
            tuple: (df_validos, df_invalidos)
        """
        regla = nombre_regla or f"formato_fecha_{columna}"

        def es_fecha_valida(val):
            try:
                datetime.strptime(str(val), formato)
                return True
            except (ValueError, TypeError):
                return False

        mask_validos = df[columna].apply(es_fecha_valida)
        df_invalidos = df[~mask_validos].copy()
        df_validos = df[mask_validos].copy()

        n_invalidos = len(df_invalidos)
        self.conteo_por_regla[regla] = n_invalidos

        if n_invalidos > 0:
            self._registrar_invalidos(df_invalidos, regla,
                f"Formato de fecha invalido en '{columna}', esperado: {formato}")
            if self.logger:
                self.logger.warning(
                    f"Validacion '{regla}': {n_invalidos} registros con "
                    f"formato de fecha invalido en '{columna}'"
                )

        return df_validos, df_invalidos

    def _registrar_invalidos(self, df_invalidos, regla, razon):
        """Registra los detalles de registros inválidos."""
        for idx, row in df_invalidos.head(5).iterrows():  # Solo primeros 5
            self.registros_invalidos.append({
                "indice_original": idx,
                "regla": regla,
                "razon": razon,
            })

    def reporte(self):
        """
        Genera un reporte completo de validación.
        
        Returns:
            dict: Reporte con conteos por regla y detalle de inválidos
        """
        total_invalidos = sum(self.conteo_por_regla.values())
        reporte = {
            "total_reglas_aplicadas": len(self.conteo_por_regla),
            "total_registros_invalidos": total_invalidos,
            "detalle_por_regla": self.conteo_por_regla.copy(),
            "muestra_invalidos": self.registros_invalidos[:20],
        }

        if self.logger:
            self.logger.info("=" * 50)
            self.logger.info("REPORTE DE VALIDACION")
            self.logger.info("=" * 50)
            for regla, conteo in self.conteo_por_regla.items():
                self.logger.info(f"  {regla}: {conteo} registros invalidos")
            self.logger.info(f"  TOTAL: {total_invalidos} registros invalidos")

        return reporte

    def reset(self):
        """Reinicia el validador para una nueva ejecución."""
        self.registros_invalidos = []
        self.conteo_por_regla = {}
