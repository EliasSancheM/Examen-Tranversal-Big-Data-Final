"""
=============================================================================
RED Santiago Big Data — Dashboard & Visualizacion (PASO 4)
=============================================================================
Genera 4 graficos representativos con insights relevantes y predictivos
del proceso de congestion del transporte publico.

Graficos:
  1. Mapa de calor de congestion por ruta y hora
  2. Velocidad promedio por ruta y hora del dia
  3. Impacto del clima en la velocidad de los buses
  4. Distribucion de congestion por ruta (con KPIs)
=============================================================================
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI para Windows
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import numpy as np
import os
from datetime import datetime

from config import OUTPUT_DIR, GRAFICOS_DIR, DATALAKE_CURATED, CONGESTION_UMBRALES
from utils.logger import PipelineLogger
from utils.error_handler import manejar_errores

# =============================================================================
# INICIALIZACION
# =============================================================================
log = PipelineLogger(nombre_modulo="dashboard")

# Estilo profesional para graficos
plt.rcParams.update({
    'figure.facecolor': '#0d1117',
    'axes.facecolor': '#161b22',
    'axes.edgecolor': '#30363d',
    'axes.labelcolor': '#c9d1d9',
    'text.color': '#c9d1d9',
    'xtick.color': '#8b949e',
    'ytick.color': '#8b949e',
    'grid.color': '#21262d',
    'grid.alpha': 0.6,
    'font.family': 'sans-serif',
    'font.size': 11,
    'axes.titlesize': 16,
    'axes.labelsize': 13,
    'figure.titlesize': 20,
})

# Paleta de colores profesional
COLORES = {
    'primario':     '#58a6ff',
    'secundario':   '#7ee787',
    'acento':       '#ff7b72',
    'warning':      '#d29922',
    'info':         '#79c0ff',
    'gradiente':    ['#0d1117', '#161b22', '#1f6feb', '#58a6ff', '#79c0ff'],
    'congestion': {
        'Fluido':         '#7ee787',
        'Moderado':       '#d29922',
        'Congestionado':  '#ff7b72',
    },
    'rutas': ['#58a6ff', '#7ee787', '#ff7b72', '#d2a8ff', '#d29922', '#79c0ff'],
}


def cargar_datos():
    """Carga los datos procesados por el pipeline."""
    ruta_detalle = os.path.join(DATALAKE_CURATED, "datos_enriquecidos.csv")
    ruta_agregado = os.path.join(DATALAKE_CURATED, "datos_agregados_ruta_hora.csv")

    if not os.path.exists(ruta_detalle):
        # Intentar desde output/
        ruta_detalle = os.path.join(OUTPUT_DIR, "datos_enriquecidos.csv")
        ruta_agregado = os.path.join(OUTPUT_DIR, "datos_agregados.csv")

    if not os.path.exists(ruta_detalle):
        raise FileNotFoundError(
            "No se encontraron datos procesados. "
            "Ejecute primero: python pipeline_batch.py"
        )

    df_detalle = pd.read_csv(ruta_detalle)
    df_agregado = pd.read_csv(ruta_agregado)

    log.info(f"Datos cargados: {len(df_detalle)} registros detallados, "
             f"{len(df_agregado)} registros agregados")

    return df_detalle, df_agregado


# =============================================================================
# GRAFICO 1: MAPA DE CALOR DE CONGESTION POR RUTA Y HORA
# =============================================================================
@manejar_errores("grafico1_heatmap", logger=log)
def grafico1_heatmap_congestion(df_detalle):
    """
    Mapa de calor: velocidad promedio por ruta y hora del dia.
    
    INSIGHT: Identifica las zonas criticas de congestion para cada ruta
    en cada franja horaria, permitiendo predecir horas punta.
    """
    log.info("Generando Grafico 1: Mapa de calor de congestion...")

    # Crear tabla pivote
    pivot = df_detalle.pivot_table(
        values='Velocidad_kmh',
        index='Ruta',
        columns='Hora',
        aggfunc='mean'
    ).round(1)

    fig, ax = plt.subplots(figsize=(16, 7))

    # Heatmap con colores invertidos (rojo = congestion, verde = fluido)
    cmap = sns.color_palette("RdYlGn", as_cmap=True)
    sns.heatmap(
        pivot, ax=ax, cmap=cmap, annot=True, fmt='.0f',
        linewidths=0.5, linecolor='#30363d',
        cbar_kws={
            'label': 'Velocidad Promedio (km/h)',
            'shrink': 0.8,
        },
        annot_kws={'size': 9, 'weight': 'bold'},
        vmin=10, vmax=55,
    )

    ax.set_title('Mapa de Calor: Congestion por Ruta y Hora del Dia',
                 fontweight='bold', pad=20, fontsize=18)
    ax.set_xlabel('Hora del Dia', fontweight='bold')
    ax.set_ylabel('Ruta', fontweight='bold')

    # Insight como texto
    hora_peor = pivot.mean().idxmin()
    vel_peor = pivot.mean().min()
    ruta_peor = pivot.mean(axis=1).idxmin()
    fig.text(0.5, -0.02,
             f"INSIGHT: La hora mas congestionada es las {hora_peor}:00 "
             f"(vel. promedio {vel_peor:.0f} km/h). "
             f"La ruta mas afectada es la {ruta_peor}.",
             ha='center', fontsize=12, style='italic',
             color=COLORES['warning'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['warning'], alpha=0.9))

    plt.tight_layout()
    ruta_salida = os.path.join(GRAFICOS_DIR, "01_heatmap_congestion.png")
    fig.savefig(ruta_salida, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)

    log.info(f"  Grafico 1 guardado: {ruta_salida}")
    return ruta_salida


# =============================================================================
# GRAFICO 2: VELOCIDAD PROMEDIO POR RUTA Y HORA (LINEAS)
# =============================================================================
@manejar_errores("grafico2_lineas", logger=log)
def grafico2_velocidad_por_hora(df_detalle):
    """
    Grafico de lineas: velocidad promedio por hora para cada ruta.
    
    INSIGHT: Patron temporal de congestion — identifica horas punta
    y permite predecir periodos criticos del dia.
    """
    log.info("Generando Grafico 2: Velocidad por ruta y hora...")

    fig, ax = plt.subplots(figsize=(14, 8))

    rutas = sorted(df_detalle['Ruta'].unique())

    for i, ruta in enumerate(rutas):
        df_ruta = df_detalle[df_detalle['Ruta'] == ruta]
        vel_por_hora = df_ruta.groupby('Hora')['Velocidad_kmh'].mean()

        color = COLORES['rutas'][i % len(COLORES['rutas'])]
        ax.plot(vel_por_hora.index, vel_por_hora.values,
                marker='o', linewidth=2.5, markersize=6,
                label=f'Ruta {ruta}', color=color, alpha=0.9)

        # Area sombreada
        ax.fill_between(vel_por_hora.index, vel_por_hora.values,
                        alpha=0.08, color=color)

    # Lineas de referencia de congestion
    ax.axhline(y=30, color=COLORES['congestion']['Fluido'],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=15, color=COLORES['congestion']['Congestionado'],
               linestyle='--', alpha=0.5, linewidth=1)

    # Zonas sombreadas de congestion
    ax.axhspan(30, 60, alpha=0.04, color=COLORES['congestion']['Fluido'])
    ax.axhspan(15, 30, alpha=0.04, color=COLORES['congestion']['Moderado'])
    ax.axhspan(0, 15, alpha=0.06, color=COLORES['congestion']['Congestionado'])

    # Etiquetas de zona
    ax.text(23.5, 45, 'FLUIDO', fontsize=9, color=COLORES['congestion']['Fluido'],
            ha='right', alpha=0.7, fontweight='bold')
    ax.text(23.5, 22, 'MODERADO', fontsize=9, color=COLORES['congestion']['Moderado'],
            ha='right', alpha=0.7, fontweight='bold')
    ax.text(23.5, 7, 'CONGESTIONADO', fontsize=9,
            color=COLORES['congestion']['Congestionado'],
            ha='right', alpha=0.7, fontweight='bold')

    ax.set_title('Velocidad Promedio por Ruta y Hora del Dia',
                 fontweight='bold', pad=20, fontsize=18)
    ax.set_xlabel('Hora del Dia', fontweight='bold')
    ax.set_ylabel('Velocidad Promedio (km/h)', fontweight='bold')
    ax.set_xlim(0, 23)
    ax.set_ylim(0, 60)
    ax.set_xticks(range(0, 24))
    ax.legend(loc='upper left', framealpha=0.9, facecolor='#161b22',
             edgecolor='#30363d')
    ax.grid(True, alpha=0.3)

    # Insight
    vel_global_hora = df_detalle.groupby('Hora')['Velocidad_kmh'].mean()
    hora_punta = vel_global_hora.idxmin()
    hora_libre = vel_global_hora.idxmax()
    fig.text(0.5, -0.02,
             f"INSIGHT PREDICTIVO: Hora punta detectada a las {hora_punta}:00. "
             f"Hora mas fluida a las {hora_libre}:00. "
             f"Se recomienda evitar viajes entre {max(0,hora_punta-1)}:00 y {min(23,hora_punta+1)}:00.",
             ha='center', fontsize=12, style='italic',
             color=COLORES['info'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['info'], alpha=0.9))

    plt.tight_layout()
    ruta_salida = os.path.join(GRAFICOS_DIR, "02_velocidad_por_hora.png")
    fig.savefig(ruta_salida, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)

    log.info(f"  Grafico 2 guardado: {ruta_salida}")
    return ruta_salida


# =============================================================================
# GRAFICO 3: IMPACTO DEL CLIMA EN LA VELOCIDAD
# =============================================================================
@manejar_errores("grafico3_clima", logger=log)
def grafico3_impacto_clima(df_detalle):
    """
    Boxplot: distribucion de velocidad por condicion climatica.
    
    INSIGHT: Correlacion entre clima y congestion — lluvia impacta
    significativamente la velocidad promedio de los buses.
    """
    log.info("Generando Grafico 3: Impacto del clima...")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8),
                                    gridspec_kw={'width_ratios': [3, 2]})

    # --- Boxplot principal ---
    orden_clima = ['Despejado', 'Nublado', 'Lluvia']
    colores_clima = {
        'Despejado': COLORES['congestion']['Fluido'],
        'Nublado':   COLORES['info'],
        'Lluvia':    COLORES['acento'],
    }

    bp = ax1.boxplot(
        [df_detalle[df_detalle['Clima_Condicion'] == c]['Velocidad_kmh'].dropna()
         for c in orden_clima],
        tick_labels=orden_clima,
        patch_artist=True,
        widths=0.5,
        showmeans=True,
        meanprops=dict(marker='D', markerfacecolor='white', markersize=8),
        medianprops=dict(color='white', linewidth=2),
        whiskerprops=dict(color='#8b949e'),
        capprops=dict(color='#8b949e'),
        flierprops=dict(marker='o', markerfacecolor='#8b949e', alpha=0.3),
    )

    for patch, clima in zip(bp['boxes'], orden_clima):
        patch.set_facecolor(colores_clima[clima])
        patch.set_alpha(0.7)
        patch.set_edgecolor('white')

    ax1.set_title('Distribucion de Velocidad por Condicion Climatica',
                  fontweight='bold', pad=15, fontsize=15)
    ax1.set_ylabel('Velocidad (km/h)', fontweight='bold')
    ax1.set_xlabel('Condicion Climatica', fontweight='bold')
    ax1.grid(True, alpha=0.2, axis='y')

    # Lineas de referencia
    ax1.axhline(y=30, color=COLORES['congestion']['Fluido'],
                linestyle='--', alpha=0.4, linewidth=1)
    ax1.axhline(y=15, color=COLORES['congestion']['Congestionado'],
                linestyle='--', alpha=0.4, linewidth=1)

    # --- Grafico de barras con promedios ---
    promedios = df_detalle.groupby('Clima_Condicion')['Velocidad_kmh'].mean()
    promedios = promedios.reindex(orden_clima)

    bars = ax2.barh(orden_clima, promedios.values, height=0.5)
    for bar, clima in zip(bars, orden_clima):
        bar.set_color(colores_clima[clima])
        bar.set_alpha(0.8)
        bar.set_edgecolor('white')
        bar.set_linewidth(0.5)
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{bar.get_width():.1f} km/h',
                va='center', fontweight='bold', fontsize=12,
                color=colores_clima[clima])

    ax2.set_title('Velocidad Promedio por Clima',
                  fontweight='bold', pad=15, fontsize=15)
    ax2.set_xlabel('Velocidad Promedio (km/h)', fontweight='bold')
    ax2.set_xlim(0, promedios.max() * 1.3)
    ax2.grid(True, alpha=0.2, axis='x')

    # Insight
    vel_lluvia = promedios.get('Lluvia', 0)
    vel_despejado = promedios.get('Despejado', 0)
    diferencia = vel_despejado - vel_lluvia
    pct = (diferencia / vel_despejado * 100) if vel_despejado > 0 else 0

    fig.text(0.5, -0.02,
             f"INSIGHT: La lluvia reduce la velocidad promedio en {diferencia:.1f} km/h "
             f"({pct:.1f}% mas lento). "
             f"Prediccion: dias lluviosos aumentan congestion significativamente.",
             ha='center', fontsize=12, style='italic',
             color=COLORES['acento'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['acento'], alpha=0.9))

    plt.tight_layout()
    ruta_salida = os.path.join(GRAFICOS_DIR, "03_impacto_clima.png")
    fig.savefig(ruta_salida, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)

    log.info(f"  Grafico 3 guardado: {ruta_salida}")
    return ruta_salida


# =============================================================================
# GRAFICO 4: DISTRIBUCION DE CONGESTION POR RUTA + KPIs
# =============================================================================
@manejar_errores("grafico4_congestion", logger=log)
def grafico4_congestion_por_ruta(df_detalle):
    """
    Barras apiladas + KPIs: distribucion de niveles de congestion por ruta.
    
    INSIGHT: Ranking de rutas mas congestionadas para priorizar
    mejoras operacionales y asignacion de flota.
    """
    log.info("Generando Grafico 4: Congestion por ruta...")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8),
                                    gridspec_kw={'width_ratios': [3, 2]})

    # --- Barras apiladas ---
    niveles = ['Fluido', 'Moderado', 'Congestionado']
    pivot = df_detalle.pivot_table(
        index='Ruta',
        columns='Nivel_Congestion',
        values='ID_Bus',
        aggfunc='count',
        fill_value=0
    )

    # Asegurar que existen todas las columnas
    for nivel in niveles:
        if nivel not in pivot.columns:
            pivot[nivel] = 0
    pivot = pivot[niveles]

    # Convertir a porcentajes
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    # Ordenar por porcentaje de congestion (de mas a menos congestionada)
    pivot_pct = pivot_pct.sort_values('Congestionado', ascending=True)

    # Grafico de barras apiladas horizontales
    left = np.zeros(len(pivot_pct))
    for nivel in niveles:
        color = COLORES['congestion'][nivel]
        bars = ax1.barh(pivot_pct.index, pivot_pct[nivel], left=left,
                       label=nivel, color=color, alpha=0.85,
                       edgecolor='white', linewidth=0.5, height=0.6)

        # Etiquetas dentro de las barras (solo si hay espacio)
        for bar, val in zip(bars, pivot_pct[nivel]):
            if val > 8:
                ax1.text(bar.get_x() + bar.get_width()/2,
                        bar.get_y() + bar.get_height()/2,
                        f'{val:.0f}%', ha='center', va='center',
                        fontsize=10, fontweight='bold', color='white')

        left += pivot_pct[nivel].values

    ax1.set_title('Distribucion de Congestion por Ruta',
                  fontweight='bold', pad=15, fontsize=15)
    ax1.set_xlabel('Porcentaje (%)', fontweight='bold')
    ax1.set_ylabel('Ruta', fontweight='bold')
    ax1.set_xlim(0, 100)
    ax1.legend(loc='lower right', framealpha=0.9,
              facecolor='#161b22', edgecolor='#30363d')

    # --- Panel KPIs ---
    ax2.axis('off')
    ax2.set_title('KPIs del Sistema', fontweight='bold', pad=15, fontsize=15)

    # Calcular KPIs
    vel_global = df_detalle['Velocidad_kmh'].mean()
    total_buses = df_detalle['ID_Bus'].nunique()
    total_registros = len(df_detalle)
    pct_congestionado = (
        (df_detalle['Nivel_Congestion'] == 'Congestionado').sum() / total_registros * 100
    )
    ruta_peor = pivot_pct['Congestionado'].idxmax()
    pct_peor = pivot_pct['Congestionado'].max()

    kpis = [
        ("Velocidad Global", f"{vel_global:.1f} km/h", COLORES['primario']),
        ("Buses Activos", f"{total_buses}", COLORES['secundario']),
        ("Total Registros", f"{total_registros:,}", COLORES['info']),
        ("% Congestionado", f"{pct_congestionado:.1f}%", COLORES['acento']),
        ("Ruta Mas Critica", f"{ruta_peor} ({pct_peor:.0f}%)", COLORES['warning']),
    ]

    for i, (label, valor, color) in enumerate(kpis):
        y = 0.85 - i * 0.18

        # Caja del KPI
        ax2.add_patch(plt.Rectangle((0.05, y - 0.06), 0.9, 0.14,
                      facecolor='#1c2128', edgecolor=color,
                      linewidth=2, alpha=0.9, transform=ax2.transAxes,
                      clip_on=False))

        ax2.text(0.15, y + 0.02, label, transform=ax2.transAxes,
                fontsize=10, color='#8b949e', va='center')
        ax2.text(0.15, y - 0.03, valor, transform=ax2.transAxes,
                fontsize=16, fontweight='bold', color=color, va='center')

    # Insight
    fig.text(0.5, -0.02,
             f"INSIGHT PREDICTIVO: La ruta {ruta_peor} presenta {pct_peor:.0f}% de "
             f"congestion. Se recomienda aumentar frecuencia en esta ruta. "
             f"El {pct_congestionado:.1f}% del sistema opera congestionado.",
             ha='center', fontsize=12, style='italic',
             color=COLORES['warning'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['warning'], alpha=0.9))

    plt.tight_layout()
    ruta_salida = os.path.join(GRAFICOS_DIR, "04_congestion_por_ruta.png")
    fig.savefig(ruta_salida, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)

    log.info(f"  Grafico 4 guardado: {ruta_salida}")
    return ruta_salida


# =============================================================================
# GENERAR DASHBOARD HTML INTERACTIVO
# =============================================================================
@manejar_errores("dashboard_html", logger=log)
def generar_dashboard_html(graficos_paths):
    """Genera un archivo HTML con los 4 graficos y resumen."""
    log.info("Generando Dashboard HTML...")

    # Convertir rutas de imagenes a relativas
    html_imgs = ""
    titulos = [
        "Mapa de Calor: Congestion por Ruta y Hora",
        "Velocidad Promedio por Ruta y Hora del Dia",
        "Impacto del Clima en la Velocidad",
        "Distribucion de Congestion por Ruta + KPIs",
    ]

    for i, (path, titulo) in enumerate(zip(graficos_paths, titulos)):
        if path and os.path.exists(path):
            rel_path = os.path.relpath(path, OUTPUT_DIR)
            html_imgs += f"""
            <div class="grafico-card">
                <h2>Grafico {i+1}: {titulo}</h2>
                <img src="{rel_path}" alt="{titulo}">
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RED Santiago Big Data - Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0d1117; color: #c9d1d9;
            min-height: 100vh; padding: 2rem;
        }}
        .header {{
            text-align: center; margin-bottom: 3rem;
            padding: 2rem; border-radius: 16px;
            background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
            border: 1px solid #30363d;
        }}
        .header h1 {{
            font-size: 2.5rem; margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #58a6ff, #7ee787);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .header p {{ color: #8b949e; font-size: 1.1rem; }}
        .timestamp {{ color: #484f58; font-size: 0.9rem; margin-top: 0.5rem; }}
        .grid {{ display: grid; grid-template-columns: 1fr; gap: 2rem; max-width: 1200px; margin: 0 auto; }}
        .grafico-card {{
            background: #161b22; border: 1px solid #30363d;
            border-radius: 12px; padding: 1.5rem; transition: transform 0.2s;
        }}
        .grafico-card:hover {{ transform: translateY(-2px); border-color: #58a6ff; }}
        .grafico-card h2 {{
            font-size: 1.2rem; margin-bottom: 1rem;
            padding-bottom: 0.5rem; border-bottom: 1px solid #21262d;
            color: #58a6ff;
        }}
        .grafico-card img {{ width: 100%; border-radius: 8px; }}
        .footer {{
            text-align: center; margin-top: 3rem; padding: 1.5rem;
            color: #484f58; font-size: 0.9rem;
            border-top: 1px solid #21262d;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>RED Santiago Big Data</h1>
        <p>Dashboard de Prediccion de Congestion — Pipeline Batch GCP</p>
        <div class="timestamp">Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    <div class="grid">
        {html_imgs}
    </div>
    <div class="footer">
        <p>AVY1101 — Evaluacion Parcial N2 — DuocUC — Big Data</p>
    </div>
</body>
</html>"""

    html_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    log.info(f"  Dashboard HTML guardado: {html_path}")
    return html_path


# =============================================================================
# FUNCION PRINCIPAL
# =============================================================================
def main():
    """Genera los 4 graficos del dashboard."""
    log.info("*" * 60)
    log.info("RED SANTIAGO BIG DATA — DASHBOARD & VISUALIZACION")
    log.info(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("*" * 60)

    # Crear directorio de graficos
    os.makedirs(GRAFICOS_DIR, exist_ok=True)

    # Cargar datos procesados
    df_detalle, df_agregado = cargar_datos()

    # Generar los 4 graficos
    graficos = []
    graficos.append(grafico1_heatmap_congestion(df_detalle))
    graficos.append(grafico2_velocidad_por_hora(df_detalle))
    graficos.append(grafico3_impacto_clima(df_detalle))
    graficos.append(grafico4_congestion_por_ruta(df_detalle))

    # Generar dashboard HTML
    generar_dashboard_html([g for g in graficos if g is not None])

    log.info("")
    log.info("*" * 60)
    log.info("DASHBOARD GENERADO EXITOSAMENTE")
    log.info(f"Graficos en: {GRAFICOS_DIR}")
    log.info(f"Dashboard: {os.path.join(OUTPUT_DIR, 'dashboard.html')}")
    log.info("*" * 60)


if __name__ == "__main__":
    main()
