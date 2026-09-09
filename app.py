import streamlit as st
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Layout Completo de Planta - Interactivo CAD")

st.title("Plano Esquemático de Layout Completo - Planta Industrial")
st.caption("Reconstrucción geométrica 2D modular sobre malla ortogonal con panel dinámico de inspección.")

# ==========================================
# 1. BASE DE DATOS DEL LAYOUT COMPLETO
# ==========================================
# Diccionario de elementos categorizados con sus geometrías normalizadas (x0, y0, x1, y1) o centro (x, y, r)

elements = {
    # --- SECCIÓN 1: LOOP SUPERIOR IZQUIERDO Y DESCENSO VERTICAL ---
    "LIFTER_01": {"type": "LIFTER", "shape": "rect", "coords": [1.5, 22.0, 2.5, 23.2], "name": "Lifter Entrada Principal"},
    "TV_01": {"type": "TV_ROT", "shape": "circle", "center": [2.0, 20.8], "r": 0.5, "name": "Turning Table TV-01"},
    "TL_TOP_1": {"type": "TL", "shape": "rect", "coords": [2.5, 20.3, 3.7, 21.3], "name": "Conveyor TL Top 1"},
    "LIFTER_02": {"type": "LIFTER", "shape": "rect", "coords": [3.7, 20.3, 4.7, 21.3], "name": "Lifter Intermedio 1"},
    "TL_TOP_2": {"type": "TL", "shape": "rect", "coords": [4.7, 20.3, 10.7, 21.3], "name": "Línea Conveyors TL Top (Tramo Largo 1)"},
    "TV_02": {"type": "TV_ROT", "shape": "circle", "center": [11.2, 20.8], "r": 0.5, "name": "Turning Table TV-02"},
    
    "TV_03": {"type": "TV_ROT", "shape": "circle", "center": [2.0, 19.0], "r": 0.5, "name": "Turning Table TV-03"},
    "TV_04": {"type": "TV_ROT", "shape": "circle", "center": [3.2, 19.0], "r": 0.5, "name": "Turning Table TV-04"},
    "TS_01": {"type": "TS", "shape": "rect", "coords": [2.5, 18.75, 2.7, 19.25], "name": "Conveyor Small TS-01"},
    
    "TL_V_01": {"type": "TL", "shape": "rect", "coords": [2.7, 17.2, 3.7, 18.5], "name": "Conveyor Vertical TL-V01"},
    "INDEX_01": {"type": "TV_IND", "shape": "rect", "coords": [2.7, 15.5, 3.7, 17.0], "name": "Indexing Table IT-01"},
    
    # Bloques TU (Corner Converter Anchos - Zonas Oscuras)
    "TU_BLOCK_1": {"type": "TU", "shape": "rect", "coords": [1.5, 13.5, 5.0, 15.0], "name": "Corner Converter TU - Módulo 1"},
    "TL_V_02": {"type": "TL", "shape": "rect", "coords": [2.0, 11.5, 3.0, 13.2], "name": "Conveyor Vertical TL-V02"},
    "TL_V_03": {"type": "TL", "shape": "rect", "coords": [3.5, 11.5, 4.5, 13.2], "name": "Conveyor Vertical TL-V03"},
    "INDEX_02": {"type": "TV_IND", "shape": "rect", "coords": [2.0, 9.8, 3.0, 11.2], "name": "Indexing Table IT-02"},
    "INDEX_03": {"type": "TV_IND", "shape": "rect", "coords": [3.5, 9.8, 4.5, 11.2], "name": "Indexing Table IT-03"},
    "TU_BLOCK_2": {"type": "TU", "shape": "rect", "coords": [1.5, 8.0, 5.0, 9.5], "name": "Corner Converter TU - Módulo 2"},

    "LIFTER_03": {"type": "LIFTER", "shape": "rect", "coords": [1.7, 6.2, 2.8, 7.3], "name": "Lifter Salida Inferior Izq"},
    "TL_H_BOTTOM_1": {"type": "TL", "shape": "rect", "coords": [2.8, 6.3, 4.0, 7.3], "name": "Conveyor TL Bottom 1"},
    "TV_05": {"type": "TV_ROT", "shape": "circle", "center": [4.5, 6.8], "r": 0.5, "name": "Turning Table TV-05"},
    "INDEX_04": {"type": "TV_IND", "shape": "rect", "coords": [5.2, 6.3, 6.7, 7.3], "name": "Indexing Table IT-04"},
    "TL_H_BOTTOM_2": {"type": "TL", "shape": "rect", "coords": [6.9, 6.3, 7.9, 7.3], "name": "Conveyor TL Bottom 2"},
    "TV_06": {"type": "TV_ROT", "shape": "circle", "center": [8.4, 6.8], "r": 0.5, "name": "Turning Table TV-06"},

    # --- SECCIÓN 2: TRAMO CENTRAL Y LOOP MATRICIAL (OVEN / BASTIDORES) ---
    "TL_DESC_LONG": {"type": "TL", "shape": "rect", "coords": [10.7, 11.0, 11.7, 19.8], "name": "Bajada Vertical TL Long (Tramo Continuo)"},
    "TV_07": {"type": "TV_ROT", "shape": "circle", "center": [11.2, 10.3], "r": 0.5, "name": "Turning Table TV-07"},
    "DOOR_01": {"type": "DOOR", "shape": "rect", "coords": [11.8, 10.0, 12.3, 10.6], "name": "Lifting Conveyor / Door 01"},
    "TL_MID_1": {"type": "TL", "shape": "rect", "coords": [12.4, 9.8, 14.4, 10.8], "name": "Conveyor TL Medio 1"},
    "TV_08": {"type": "TV_ROT", "shape": "circle", "center": [14.9, 10.3], "r": 0.5, "name": "Turning Table TV-08"},
    "DOOR_02": {"type": "DOOR", "shape": "rect", "coords": [10.9, 8.2, 11.5, 9.7], "name": "Lifting Conveyor / Door 02 (Vertical)"},

    # Matriz del Loop Central (Matriz de Estaciones y Horno/Sub-ensamble)
    "TV_GRID_11": {"type": "TV_ROT", "shape": "circle", "center": [13.5, 14.5], "r": 0.5, "name": "Turning Table Grid [1,1]"},
    "TV_GRID_12": {"type": "TV_ROT", "shape": "circle", "center": [14.8, 14.5], "r": 0.5, "name": "Turning Table Grid [1,2]"},
    "TV_GRID_13": {"type": "TV_ROT", "shape": "circle", "center": [16.1, 14.5], "r": 0.5, "name": "Turning Table Grid [1,3]"},
    "INDEX_MID_1": {"type": "TV_IND", "shape": "rect", "coords": [13.0, 12.5, 14.0, 13.8], "name": "Indexing Table Central 1"},
    "INDEX_MID_2": {"type": "TV_IND", "shape": "rect", "coords": [15.6, 12.5, 16.6, 13.8], "name": "Indexing Table Central 2"},
    
    "TV_GRID_21": {"type": "TV_ROT", "shape": "circle", "center": [13.5, 11.5], "r": 0.5, "name": "Turning Table Grid [2,1]"},
    "TV_GRID_22": {"type": "TV_ROT", "shape": "circle", "center": [14.8, 11.5], "r": 0.5, "name": "Turning Table Grid [2,2]"},
    "TV_GRID_23": {"type": "TV_ROT", "shape": "circle", "center": [16.1, 11.5], "r": 0.5, "name": "Turning Table Grid [2,3]"},

    "TV_GRID_31": {"type": "TV_ROT", "shape": "circle", "center": [13.5, 8.5], "r": 0.5, "name": "Turning Table Grid [3,1]"},
    "TV_GRID_32": {"type": "TV_ROT", "shape": "circle", "center": [14.8, 8.5], "r": 0.5, "name": "Turning Table Grid [3,2]"},
    "TV_GRID_33": {"type": "TV_ROT", "shape": "circle", "center": [16.1, 8.5], "r": 0.5, "name": "Turning Table Grid [3,3]"},
    "INDEX_MID_3": {"type": "TV_IND", "shape": "rect", "coords": [15.6, 9.5, 16.6, 10.8], "name": "Indexing Table Central 3"},
    "TV_GRID_42": {"type": "TV_ROT", "shape": "circle", "center": [14.8, 6.8], "r": 0.5, "name": "Turning Table Grid [4,2]"},

    # --- SECCIÓN 3: ZONA DERECHA, BUCLE DE ELEVACIÓN Y DESCARGA FINAL ---
    "TL_MID_LONG_H": {"type": "TL", "shape": "rect", "coords": [15.5, 6.3, 19.5, 7.3], "name": "Conveyor Largo Horizontal de Transición"},
    "TV_09": {"type": "TV_ROT", "shape": "circle", "center": [20.0, 6.8], "r": 0.5, "name": "Turning Table TV-09"},
    "TL_V_RIGHT_1": {"type": "TL", "shape": "rect", "coords": [19.5, 7.5, 20.5, 9.0], "name": "Conveyor Vertical Derecha 1"},
    "INDEX_RIGHT_1": {"type": "TV_IND", "shape": "rect", "coords": [19.5, 9.2, 20.5, 10.5], "name": "Indexing Table Derecha 1"},
    "DOOR_03": {"type": "DOOR", "shape": "rect", "coords": [19.5, 10.7, 20.5, 11.2], "name": "Lifting Conveyor / Door 03"},
    "TL_V_RIGHT_2": {"type": "TL", "shape": "rect", "coords": [19.5, 11.4, 20.5, 13.0], "name": "Conveyor Vertical Derecha 2"},
    "TV_10": {"type": "TV_ROT", "shape": "circle", "center": [20.0, 13.5], "r": 0.5, "name": "Turning Table TV-10"},
    "LIFTER_04": {"type": "LIFTER", "shape": "rect", "coords": [19.5, 14.2, 20.5, 15.2], "name": "Lifter Superior Derecha"},

    "DOOR_04": {"type": "DOOR", "shape": "rect", "coords": [21.5, 13.0, 22.5, 13.5], "name": "Lifting Conveyor / Door 04"},
    "TL_H_TOP_RIGHT": {"type": "TL", "shape": "rect", "coords": [22.7, 13.0, 24.2, 14.0], "name": "Conveyor TL Superior Derecha"},
    "TV_11": {"type": "TV_ROT", "shape": "circle", "center": [24.7, 13.5], "r": 0.5, "name": "Turning Table TV-11"},

    "INDEX_RIGHT_2": {"type": "TV_IND", "shape": "rect", "coords": [22.7, 10.0, 23.7, 11.2], "name": "Indexing Table Derecha 2"},
    "DOOR_05": {"type": "DOOR", "shape": "rect", "coords": [22.7, 9.3, 23.7, 9.8], "name": "Lifting Conveyor / Door 05"},
    "TV_12": {"type": "TV_ROT", "shape": "circle", "center": [23.2, 8.8], "r": 0.5, "name": "Turning Table TV-12"},
    
    "TU_BLOCK_3": {"type": "TU", "shape": "rect", "coords": [21.5, 4.5, 25.0, 6.0], "name": "Corner Converter TU - Módulo 3"},
    "TV_13": {"type": "TV_ROT", "shape": "circle", "center": [22.2, 3.5], "r": 0.5, "name": "Turning Table TV-13"},
    "TV_14": {"type": "TV_ROT", "shape": "circle", "center": [24.5, 3.5], "r": 0.5, "name": "Turning Table TV-14"},

    "TV_15": {"type": "TV_ROT", "shape": "circle", "center": [24.5, 1.5], "r": 0.5, "name": "Turning Table TV-15"},
    "TV_16": {"type": "TV_ROT", "shape": "circle", "center": [26.5, 1.5], "r": 0.5, "name": "Turning Table TV-16 (Entrada Racks)"},
    "INDEX_RIGHT_3": {"type": "TV_IND", "shape": "rect", "coords": [26.0, 3.0, 27.0, 4.5], "name": "Indexing Table Salida 3"},
    "TV_17": {"type": "TV_ROT", "shape": "circle", "center": [26.5, 9.8], "r": 0.5, "name": "Turning Table TV-17 (Transición Racks)"},

    # Estructura Especial: RACKS / OVEN
    "RACKS_AREA": {"type": "RACKS", "shape": "rect", "coords": [27.5, 6.0, 29.8, 16.5], "name": "Módulo de Almazenamiento / Racks / Oven 1 y 2"}
}

# Configuración Estética de Colores basada en tu Leyenda Oficial
styles = {
    "TL": {"line": "#1F77B4", "fill": "#A6CEE3", "width": 2, "label": "TL - Longitudinal Conveyor"},
    "TS": {"line": "#00B4D8", "fill": "#E0F7FA", "width": 2, "label": "TL - Longitudinal Conveyor (Small)"},
    "TV_IND": {"line": "#D62728", "fill": "#FADBD8", "width": 2, "label": "TV - Indexing Table"},
    "TU": {"line": "#0B3C5D", "fill": "#1D507A", "width": 2, "label": "TU - Corner Converter"},
    "DOOR": {"line": "#D4AC0D", "fill": "#F9E79F", "width": 2, "label": "Lifting Conveyor / Door"},
    "TV_ROT": {"line": "#E67E22", "fill": "rgba(0,0,0,0)", "width": 3, "label": "TV - Turning Table"},
    "LIFTER": {"line": "#1C2833", "fill": "#2C3E50", "width": 2, "label": "LIFTER"},
    "RACKS": {"line": "#5D6D7E", "fill": "#EBEDEF", "width": 2, "label": "Racks / Area Industrial"}
}

# ==========================================
# 2. RENDERIZADO VECTORIAL DEL PLANO COMPLETO
# ==========================================
def render_full_layout():
    fig = go.Figure()
    shapes = []

    for key, item in elements.items():
        st_cfg = styles[item["type"]]

        if item["shape"] == "circle":
            cx, cy = item["center"]
            r = item["r"]
            shapes.append(dict(
                type="circle", xref="x", yref="y",
                x0=cx - r, y0=cy - r, x1=cx + r, y1=cy + r,
                line=dict(color=st_cfg["line"], width=st_cfg["width"]),
                fillcolor=st_cfg["fill"]
            ))
            center_x, center_y = cx, cy
        else:
            x0, y0, x1, y1 = item["coords"]
            shapes.append(dict(
                type="rect", xref="x", yref="y",
                x0=x0, y0=y0, x1=x1, y1=y1,
                line=dict(color=st_cfg["line"], width=st_cfg["width"]),
                fillcolor=st_cfg["fill"]
            ))
            center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2

        # Puntos interactivos transparentes para Hover/Clics
        fig.add_trace(go.Scatter(
            x=[center_x], y=[center_y],
            mode="markers",
            marker=dict(size=14, color="rgba(0,0,0,0)"),
            name=item["name"],
            customdata=[key],
            hovertemplate=f"<b>{item['name']}</b><br>Código: {key}<br>Tipo: {st_cfg['label']}<extra></extra>"
        ))

    fig.update_layout(
        shapes=shapes,
        xaxis=dict(visible=False, range=[0, 31]),
        yaxis=dict(visible=False, range=[0, 24], scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        height=720
    )
    return fig

# ==========================================
# 3. INTERFAZ INTERACTIVA STREAMLIT
# ==========================================
col_map, col_info = st.columns([7, 3])

with col_map:
    st.plotly_chart(render_full_layout(), use_container_width=True)

with col_info:
    st.subheader("Panel de Inspección CAD")
    selected_key = st.selectbox("Seleccionar componente activo:", list(elements.keys()))

    if selected_key:
        elem = elements[selected_key]
        type_info = styles[elem["type"]]
        
        st.markdown(f"### {elem['name']}")
        st.markdown(f"**Categoría:** `{type_info['label']}`")
        st.markdown(f"**Identificador CAD:** `{selected_key}`")
        st.divider()

        # Telemetría / Módulos de datos específicos según la categoría
        if elem["type"] == "TV_ROT":
            st.metric("Velocidad de Giro", "1.2 m/s")
            st.metric("Ángulo de Transferencia", "90° / 180°")
            st.success("Sensores de alineación: OK")
        elif elem["type"] in ["TL", "TS"]:
            st.metric("Velocidad de Cinta", "0.8 m/s")
            st.write("**Carga Promedio:** 450 kg/m")
            st.info("Banda modular sin desgaste detectado.")
        elif elem["type"] == "TV_IND":
            st.metric("Tiempo de Ciclo", "4.5 s")
            st.metric("Piezas Procesadas", "3,420 unidades")
            st.warning("Mantenimiento preventivo sugerido en 48 hrs.")
        elif elem["type"] == "TU":
            st.metric("Estado de Convertidor", "Sincronizado")
            st.write("**Modo:** Transferencia multidireccional")
        else:
            st.write("Componente operacional activo en la línea principal.")
