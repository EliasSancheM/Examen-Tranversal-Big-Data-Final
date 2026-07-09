#!/usr/bin/env bash
# ============================================================================
# RED Santiago — Demo de tráfico en streaming para la presentación/video
# ============================================================================
# Uso:  ./demo_stream_red.sh "https://tu-api-xxxx.run.app"
#
# Envía oleadas de pings GPS de buses con bus_id, ruta, velocidad y
# coordenadas aleatorias dentro de Santiago. ~5% serán inválidos a propósito
# para evidenciar la validación en vivo.
# ============================================================================
set -euo pipefail

API_URL="${1:-}"
if [[ -z "$API_URL" ]]; then
  echo "Uso: $0 <API_URL>"
  exit 1
fi

RUTAS=("210" "210e" "502" "502c" "104")

rand_lat() { awk -v s="$RANDOM" 'BEGIN{srand(s); printf "%.6f", -33.65 + rand()*0.35}'; }
rand_lon() { awk -v s="$RANDOM" 'BEGIN{srand(s); printf "%.6f", -70.85 + rand()*0.35}'; }

echo "Enviando tráfico de buses a: $API_URL"
while true; do
  for i in $(seq 1 30); do
    BUS="BUS_$(( (RANDOM % 50) + 1000 ))"
    RUTA="${RUTAS[$RANDOM % ${#RUTAS[@]}]}"
    if (( RANDOM % 20 == 0 )); then
      VEL=-5                          # ~5% inválidos
    else
      VEL=$(( RANDOM % 70 ))
    fi
    curl -s -X POST "$API_URL/api/posicion" \
      -H "Content-Type: application/json" \
      -d "{\"bus_id\":\"$BUS\",\"ruta\":\"$RUTA\",\"velocidad_kmh\":$VEL,\"latitud\":$(rand_lat),\"longitud\":$(rand_lon)}" \
      > /dev/null
  done
  echo "[$(date +%H:%M:%S)] 30 pings enviados ✓"
  sleep 3
done
