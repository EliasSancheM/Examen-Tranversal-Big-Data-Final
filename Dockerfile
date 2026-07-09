# =============================================================================
# RED Santiago — Imagen de la API de ingesta GPS en streaming (Cloud Run)
# =============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Instalar dependencias primero (mejor caché de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la API
COPY api_red.py .

# Cloud Run inyecta la variable PORT (default 8080)
ENV PORT=8080

# Servir con gunicorn (producción), 1 worker + varios hilos para el auto-generador
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 api_red:app
