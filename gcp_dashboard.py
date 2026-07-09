"""
=============================================================================
RED Santiago Big Data — Dashboard GCP (PASO 4)
=============================================================================
Genera 4 graficos con insights desde BigQuery o desde CSV exportados.
Funciona tanto en Cloud Shell como en entorno local.

Graficos:
  1. Mapa de calor de congestion por ruta y hora
  2. Velocidad promedio por ruta y hora del dia
  3. Impacto del clima en la velocidad de los buses
  4. Distribucion de congestion por ruta (con KPIs)
=============================================================================
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import sys
import logging
from datetime import datetime

from gcp_config import PROJECT_ID, DATASET_ID, TABLE_ENRIQUECIDO, TABLE_AGREGADO

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("gcp_dashboard")

# =============================================================================
# ESTILO PROFESIONAL
# =============================================================================
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
})

COLORES = {
    'primario': '#58a6ff', 'secundario': '#7ee787',
    'acento': '#ff7b72', 'warning': '#d29922', 'info': '#79c0ff',
    'congestion': {'Fluido': '#7ee787', 'Moderado': '#d29922', 'Congestionado': '#ff7b72'},
    'rutas': ['#58a6ff', '#7ee787', '#ff7b72', '#d2a8ff', '#d29922', '#79c0ff'],
}

GRAFICOS_DIR = "output/graficos"


# =============================================================================
# CARGAR DATOS (desde BigQuery o CSV local)
# =============================================================================
def cargar_datos():
    """Intenta cargar datos desde BigQuery, si falla usa CSV local."""

    # Intentar BigQuery primero
    if PROJECT_ID != "TU_PROJECT_ID":
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=PROJECT_ID)
            log.info("Cargando datos desde BigQuery...")

            df_detalle = client.query(
                f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ENRIQUECIDO}`"
            ).to_dataframe()

            df_agregado = client.query(
                f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_AGREGADO}`"
            ).to_dataframe()

            log.info(f"  BigQuery: {len(df_detalle)} registros detallados, "
                     f"{len(df_agregado)} agregados")
            return df_detalle, df_agregado

        except Exception as e:
            log.warning(f"No se pudo conectar a BigQuery: {e}")
            log.info("Intentando cargar desde CSV local...")

    # Fallback: CSV local
    csv_paths = [
        ("output/datos_enriquecidos.csv", "output/datos_agregados.csv"),
        ("datalake/curated/datos_enriquecidos.csv",
         "datalake/curated/datos_agregados_ruta_hora.csv"),
    ]

    for det_path, agr_path in csv_paths:
        if os.path.exists(det_path):
            df_detalle = pd.read_csv(det_path)
            df_agregado = pd.read_csv(agr_path)
            log.info(f"  CSV: {len(df_detalle)} registros desde {det_path}")
            return df_detalle, df_agregado

    raise FileNotFoundError(
        "No se encontraron datos. Ejecute primero:\n"
        "  python gcp_pipeline.py  (GCP)\n"
        "  python pipeline_batch.py (local)"
    )


# =============================================================================
# GRAFICO 1: MAPA DE CALOR
# =============================================================================
def grafico1_heatmap(df):
    log.info("Generando Grafico 1: Mapa de calor...")

    pivot = df.pivot_table(values='Velocidad_kmh', index='Ruta',
                           columns='Hora', aggfunc='mean').round(1)

    fig, ax = plt.subplots(figsize=(16, 7))
    cmap = sns.color_palette("RdYlGn", as_cmap=True)
    sns.heatmap(pivot, ax=ax, cmap=cmap, annot=True, fmt='.0f',
                linewidths=0.5, linecolor='#30363d',
                cbar_kws={'label': 'Velocidad Promedio (km/h)', 'shrink': 0.8},
                annot_kws={'size': 9, 'weight': 'bold'}, vmin=10, vmax=55)

    ax.set_title('Mapa de Calor: Congestion por Ruta y Hora del Dia',
                 fontweight='bold', pad=20, fontsize=18)
    ax.set_xlabel('Hora del Dia', fontweight='bold')
    ax.set_ylabel('Ruta', fontweight='bold')

    hora_peor = pivot.mean().idxmin()
    vel_peor = pivot.mean().min()
    ruta_peor = pivot.mean(axis=1).idxmin()
    fig.text(0.5, -0.02,
             f"INSIGHT: Hora mas congestionada: {hora_peor}:00 "
             f"(vel. promedio {vel_peor:.0f} km/h). Ruta mas afectada: {ruta_peor}.",
             ha='center', fontsize=12, style='italic', color=COLORES['warning'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['warning'], alpha=0.9))

    plt.tight_layout()
    path = os.path.join(GRAFICOS_DIR, "01_heatmap_congestion.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info(f"  [OK] {path}")
    return path


# =============================================================================
# GRAFICO 2: VELOCIDAD POR HORA
# =============================================================================
def grafico2_velocidad_hora(df):
    log.info("Generando Grafico 2: Velocidad por ruta y hora...")

    fig, ax = plt.subplots(figsize=(14, 8))
    rutas = sorted(df['Ruta'].unique())

    for i, ruta in enumerate(rutas):
        df_r = df[df['Ruta'] == ruta]
        vel = df_r.groupby('Hora')['Velocidad_kmh'].mean()
        color = COLORES['rutas'][i % len(COLORES['rutas'])]
        ax.plot(vel.index, vel.values, marker='o', linewidth=2.5, markersize=6,
                label=f'Ruta {ruta}', color=color, alpha=0.9)
        ax.fill_between(vel.index, vel.values, alpha=0.08, color=color)

    ax.axhline(y=30, color=COLORES['congestion']['Fluido'], linestyle='--', alpha=0.5)
    ax.axhline(y=15, color=COLORES['congestion']['Congestionado'], linestyle='--', alpha=0.5)
    ax.axhspan(30, 60, alpha=0.04, color=COLORES['congestion']['Fluido'])
    ax.axhspan(15, 30, alpha=0.04, color=COLORES['congestion']['Moderado'])
    ax.axhspan(0, 15, alpha=0.06, color=COLORES['congestion']['Congestionado'])

    ax.text(23.5, 45, 'FLUIDO', fontsize=9, color=COLORES['congestion']['Fluido'],
            ha='right', alpha=0.7, fontweight='bold')
    ax.text(23.5, 22, 'MODERADO', fontsize=9, color=COLORES['congestion']['Moderado'],
            ha='right', alpha=0.7, fontweight='bold')
    ax.text(23.5, 7, 'CONGESTIONADO', fontsize=9,
            color=COLORES['congestion']['Congestionado'], ha='right', alpha=0.7, fontweight='bold')

    ax.set_title('Velocidad Promedio por Ruta y Hora del Dia',
                 fontweight='bold', pad=20, fontsize=18)
    ax.set_xlabel('Hora del Dia', fontweight='bold')
    ax.set_ylabel('Velocidad Promedio (km/h)', fontweight='bold')
    ax.set_xlim(0, 23); ax.set_ylim(0, 60); ax.set_xticks(range(0, 24))
    ax.legend(loc='upper left', framealpha=0.9, facecolor='#161b22', edgecolor='#30363d')
    ax.grid(True, alpha=0.3)

    vel_global = df.groupby('Hora')['Velocidad_kmh'].mean()
    hp = vel_global.idxmin(); hl = vel_global.idxmax()
    fig.text(0.5, -0.02,
             f"INSIGHT PREDICTIVO: Hora punta: {hp}:00. Hora fluida: {hl}:00. "
             f"Evitar viajes entre {max(0,hp-1)}:00 y {min(23,hp+1)}:00.",
             ha='center', fontsize=12, style='italic', color=COLORES['info'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['info'], alpha=0.9))

    plt.tight_layout()
    path = os.path.join(GRAFICOS_DIR, "02_velocidad_por_hora.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info(f"  [OK] {path}")
    return path


# =============================================================================
# GRAFICO 3: IMPACTO DEL CLIMA
# =============================================================================
def grafico3_clima(df):
    log.info("Generando Grafico 3: Impacto del clima...")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8),
                                    gridspec_kw={'width_ratios': [3, 2]})

    # Usar solo condiciones que existan en los datos
    condiciones_existentes = df['Clima_Condicion'].dropna().unique().tolist()
    orden_clima = [c for c in ['Despejado', 'Nublado', 'Lluvia'] if c in condiciones_existentes]

    colores_clima = {
        'Despejado': COLORES['congestion']['Fluido'],
        'Nublado': COLORES['info'],
        'Lluvia': COLORES['acento'],
    }

    # Boxplot
    datos_box = [df[df['Clima_Condicion'] == c]['Velocidad_kmh'].dropna() for c in orden_clima]
    bp = ax1.boxplot(datos_box, tick_labels=orden_clima, patch_artist=True, widths=0.5,
                     showmeans=True,
                     meanprops=dict(marker='D', markerfacecolor='white', markersize=8),
                     medianprops=dict(color='white', linewidth=2),
                     whiskerprops=dict(color='#8b949e'),
                     capprops=dict(color='#8b949e'),
                     flierprops=dict(marker='o', markerfacecolor='#8b949e', alpha=0.3))

    for patch, clima in zip(bp['boxes'], orden_clima):
        patch.set_facecolor(colores_clima.get(clima, '#8b949e'))
        patch.set_alpha(0.7); patch.set_edgecolor('white')

    ax1.set_title('Distribucion de Velocidad por Condicion Climatica',
                  fontweight='bold', pad=15, fontsize=15)
    ax1.set_ylabel('Velocidad (km/h)', fontweight='bold')
    ax1.set_xlabel('Condicion Climatica', fontweight='bold')
    ax1.grid(True, alpha=0.2, axis='y')
    ax1.axhline(y=30, color=COLORES['congestion']['Fluido'], linestyle='--', alpha=0.4)
    ax1.axhline(y=15, color=COLORES['congestion']['Congestionado'], linestyle='--', alpha=0.4)

    # Barras horizontales
    promedios = df.groupby('Clima_Condicion')['Velocidad_kmh'].mean().reindex(orden_clima)
    bars = ax2.barh(orden_clima, promedios.values, height=0.5)
    for bar, clima in zip(bars, orden_clima):
        bar.set_color(colores_clima.get(clima, '#8b949e'))
        bar.set_alpha(0.8); bar.set_edgecolor('white'); bar.set_linewidth(0.5)
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{bar.get_width():.1f} km/h', va='center', fontweight='bold',
                fontsize=12, color=colores_clima.get(clima, '#8b949e'))

    ax2.set_title('Velocidad Promedio por Clima', fontweight='bold', pad=15, fontsize=15)
    ax2.set_xlabel('Velocidad Promedio (km/h)', fontweight='bold')
    ax2.set_xlim(0, promedios.max() * 1.3)
    ax2.grid(True, alpha=0.2, axis='x')

    # Insight
    vel_ll = promedios.get('Lluvia', promedios.min())
    vel_de = promedios.get('Despejado', promedios.max())
    dif = vel_de - vel_ll
    pct = (dif / vel_de * 100) if vel_de > 0 else 0
    fig.text(0.5, -0.02,
             f"INSIGHT: La lluvia reduce la velocidad en {dif:.1f} km/h "
             f"({pct:.1f}% mas lento). Dias lluviosos aumentan congestion.",
             ha='center', fontsize=12, style='italic', color=COLORES['acento'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['acento'], alpha=0.9))

    plt.tight_layout()
    path = os.path.join(GRAFICOS_DIR, "03_impacto_clima.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info(f"  [OK] {path}")
    return path


# =============================================================================
# GRAFICO 4: CONGESTION POR RUTA + KPIs
# =============================================================================
def grafico4_congestion(df):
    log.info("Generando Grafico 4: Congestion por ruta + KPIs...")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8),
                                    gridspec_kw={'width_ratios': [3, 2]})

    niveles = ['Fluido', 'Moderado', 'Congestionado']
    pivot = df.pivot_table(index='Ruta', columns='Nivel_Congestion',
                           values='ID_Bus', aggfunc='count', fill_value=0)
    for n in niveles:
        if n not in pivot.columns:
            pivot[n] = 0
    pivot = pivot[niveles]
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
    pivot_pct = pivot_pct.sort_values('Congestionado', ascending=True)

    left = np.zeros(len(pivot_pct))
    for nivel in niveles:
        color = COLORES['congestion'][nivel]
        bars = ax1.barh(pivot_pct.index, pivot_pct[nivel], left=left,
                       label=nivel, color=color, alpha=0.85,
                       edgecolor='white', linewidth=0.5, height=0.6)
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
    ax1.legend(loc='lower right', framealpha=0.9, facecolor='#161b22', edgecolor='#30363d')

    # KPIs
    ax2.axis('off')
    ax2.set_title('KPIs del Sistema', fontweight='bold', pad=15, fontsize=15)

    vel_global = df['Velocidad_kmh'].mean()
    total_buses = df['ID_Bus'].nunique()
    total_reg = len(df)
    pct_cong = (df['Nivel_Congestion'] == 'Congestionado').sum() / total_reg * 100
    ruta_peor = pivot_pct['Congestionado'].idxmax()
    pct_peor = pivot_pct['Congestionado'].max()

    kpis = [
        ("Velocidad Global", f"{vel_global:.1f} km/h", COLORES['primario']),
        ("Buses Activos", f"{total_buses}", COLORES['secundario']),
        ("Total Registros", f"{total_reg:,}", COLORES['info']),
        ("% Congestionado", f"{pct_cong:.1f}%", COLORES['acento']),
        ("Ruta Mas Critica", f"{ruta_peor} ({pct_peor:.0f}%)", COLORES['warning']),
    ]

    for i, (label, valor, color) in enumerate(kpis):
        y = 0.85 - i * 0.18
        ax2.add_patch(plt.Rectangle((0.05, y - 0.06), 0.9, 0.14,
                      facecolor='#1c2128', edgecolor=color, linewidth=2,
                      alpha=0.9, transform=ax2.transAxes, clip_on=False))
        ax2.text(0.15, y + 0.02, label, transform=ax2.transAxes,
                fontsize=10, color='#8b949e', va='center')
        ax2.text(0.15, y - 0.03, valor, transform=ax2.transAxes,
                fontsize=16, fontweight='bold', color=color, va='center')

    fig.text(0.5, -0.02,
             f"INSIGHT PREDICTIVO: Ruta {ruta_peor} con {pct_peor:.0f}% congestion. "
             f"El {pct_cong:.1f}% del sistema opera congestionado.",
             ha='center', fontsize=12, style='italic', color=COLORES['warning'],
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#1c2128',
                      edgecolor=COLORES['warning'], alpha=0.9))

    plt.tight_layout()
    path = os.path.join(GRAFICOS_DIR, "04_congestion_por_ruta.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info(f"  [OK] {path}")
    return path


# =============================================================================
# DASHBOARD HTML
# =============================================================================
def generar_html(graficos):
    titulos = [
        "Mapa de Calor: Congestion por Ruta y Hora",
        "Velocidad Promedio por Ruta y Hora del Dia",
        "Impacto del Clima en la Velocidad",
        "Distribucion de Congestion por Ruta + KPIs",
    ]
    imgs = ""
    for i, (path, titulo) in enumerate(zip(graficos, titulos)):
        if path and os.path.exists(path):
            rel = os.path.relpath(path, "output")
            imgs += f'<div class="card"><h2>Grafico {i+1}: {titulo}</h2><img src="{rel}"></div>\n'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RED Santiago Big Data - Dashboard GCP</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem}}
.header{{text-align:center;margin-bottom:3rem;padding:2rem;border-radius:16px;background:linear-gradient(135deg,#161b22,#1c2128);border:1px solid #30363d}}
.header h1{{font-size:2.5rem;margin-bottom:.5rem;background:linear-gradient(90deg,#58a6ff,#7ee787);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header p{{color:#8b949e;font-size:1.1rem}}
.badge{{display:inline-block;background:#1f6feb;color:white;padding:4px 12px;border-radius:20px;font-size:0.85rem;margin-top:8px}}
.grid{{display:grid;grid-template-columns:1fr;gap:2rem;max-width:1200px;margin:0 auto}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:1.5rem;transition:transform .2s}}
.card:hover{{transform:translateY(-2px);border-color:#58a6ff}}
.card h2{{font-size:1.2rem;margin-bottom:1rem;padding-bottom:.5rem;border-bottom:1px solid #21262d;color:#58a6ff}}
.card img{{width:100%;border-radius:8px}}
.footer{{text-align:center;margin-top:3rem;padding:1.5rem;color:#484f58;font-size:.9rem;border-top:1px solid #21262d}}
</style>
</head>
<body>
<div class="header">
<h1>RED Santiago Big Data</h1>
<p>Dashboard de Prediccion de Congestion &mdash; Pipeline Batch GCP</p>
<span class="badge">Google Cloud Platform</span>
<div style="color:#484f58;font-size:.9rem;margin-top:8px">Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
<div class="grid">{imgs}</div>
<div class="footer">
<p>AVY1101 &mdash; Evaluacion Parcial N&deg;2 &mdash; DuocUC &mdash; Big Data</p>
<p style="margin-top:4px">Pipeline: Cloud Storage &rarr; BigQuery &rarr; Dashboard</p>
</div>
</body>
</html>"""

    html_path = "output/dashboard.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    log.info(f"  [OK] Dashboard HTML: {html_path}")
    return html_path


# =============================================================================
# MAIN
# =============================================================================
def main():
    log.info("*" * 60)
    log.info("RED SANTIAGO — DASHBOARD GCP")
    log.info("*" * 60)

    os.makedirs(GRAFICOS_DIR, exist_ok=True)
    df_detalle, df_agregado = cargar_datos()

    graficos = [
        grafico1_heatmap(df_detalle),
        grafico2_velocidad_hora(df_detalle),
        grafico3_clima(df_detalle),
        grafico4_congestion(df_detalle),
    ]

    generar_html([g for g in graficos if g])

    log.info("")
    log.info("*" * 60)
    log.info("DASHBOARD GENERADO EXITOSAMENTE")
    log.info(f"  Graficos: {GRAFICOS_DIR}/")
    log.info(f"  Dashboard: output/dashboard.html")
    log.info("*" * 60)


if __name__ == "__main__":
    main()
