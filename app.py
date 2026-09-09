import streamlit as st
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Layout Interactivo CAD - Segmento Fiel")

# ==========================================
# 1. DICCIONARIO CON LA GEOMETRÍA EXACTA
# ==========================================
# Mapeo preciso (x, y, ancho, alto) extraído directamente del segmento de imagen:
# - Línea principal horizontal (de izquierda a derecha): TR_1 -> TL_1 -> IT_1 -> TL_2 -> TR_2 -> TS_1 -> TR_3
# - Ramal Vertical 1 (sobre TR_2): TL_3
# - Ramal Vertical 2 (sobre TR_3): IT_2 -> TS_2 -> TL_4

elements = {
    # --- MESAS GIRATORIAS (Turning Tables - Círculos Naranjas) ---
    "TR_1": {"type": "TR", "shape": "circle", "x": 1.5, "y": 2.0, "r": 0.5, "name": "Mesa Giratoria TR-1", "status": "Operativo", "rpm": "15 RPM"},
    "TR_2": {"type": "TR", "shape": "circle", "x": 6.5, "y": 2.0, "r": 0.5, "name": "Mesa Giratoria TR-2", "status": "Operativo", "rpm": "15 RPM"},
    "TR_3": {"type": "TR", "shape": "circle", "x": 8.0, "y": 2.0, "r": 0.5, "name": "Mesa Giratoria TR-3", "status": "Operativo", "rpm": "15 RPM"},

    # --- TRAMO HORIZONTAL PRINCIPAL ---
    "TL_1": {"type": "TL", "shape": "rect", "x0": 2.2, "y0": 1.65, "x1": 3.2, "y1": 2.35, "name": "Conveyor TL-1 (Largo)", "longitud": "1.0 m", "speed": "0.8 m/s"},
    "IT_1": {"type": "IT", "shape": "rect", "x0": 3.4, "y0": 1.6, "x1": 4.6, "y1": 2.4, "name": "Indexing Table IT-1", "ciclo": "4.2 s", "piezas": 1280},
    "TL_2": {"type": "TL", "shape": "rect", "x0": 4.8, "y0": 1.65, "x1": 5.8, "y1": 2.35, "name": "Conveyor TL-2 (Largo)", "longitud": "1.0 m", "speed": "0.8 m/s"},
    "TS_1": {"type": "TS", "shape": "rect", "x0": 7.1, "y0": 1.75, "x1": 7.4, "y1": 2.25, "name": "Conveyor TS-1 (Corto)", "longitud": "0.3 m", "speed": "0.5 m/s"},

    # --- RAMAL VERTICAL 1 (Sobre TR_2) ---
    "TL_3": {"type": "TL", "shape": "rect", "x0": 6.15, "y0": 2.7, "x1": 6.85, "y1": 4.1, "name": "Conveyor TL-3 (Vertical)", "longitud": "1.4 m", "speed": "0.8 m/s"},

    # --- RAMAL VERTICAL 2 (Sobre TR_3) ---
    "IT_2": {"type": "IT", "shape": "rect", "x0": 7.55, "y0": 2.7, "x1": 8.45, "y1": 3.9, "name": "Indexing Table IT-2", "ciclo": "4.5 s", "piezas": 1150},
    "TS_2": {"type": "TS", "shape": "rect", "x0": 7.6, "y0": 4.1, "x1": 8.4, "y1": 4.5, "name": "Conveyor TS-2 (Corto)", "longitud": "0.4 m", "speed": "0.5 m/s"},
    "TL_4": {"type": "TL", "shape": "rect", "x0": 7.55, "y0": 4.7, "x1": 8.45, "y1": 6.1, "name": "Conveyor TL-4 (Largo Superior)", "longitud": "1.4 m", "speed": "0.8 m/s"},
}

# Configuración gráfica de colores (coincidentes con tu imagen)
style_config = {
    "TR": {"line": "#E67E22", "fill": "rgba(0,0,0,0)", "width": 4},           # Círculo naranja
    "TL": {"line": "#1D70B8", "fill": "#E5E7E9", "width": 3},                 # Azul grande con relleno gris
    "TS": {"line": "#00A4E4", "fill": "#CBD5E1", "width": 3},                 # Azul claro chico
    "IT": {"line": "#B00000", "fill": "#FADBD8", "width": 3}                  # Rojo/Mesa Indexado (relleno salmón)
}

# ==========================================
# 2. CONSTRUCCIÓN DE LA GRÁFICA VECTORIAL
# ==========================================
def build_layout():
    fig = go.Figure()

    shapes_list = []

    # 1. Trazado de Conveyor Físico Base (Gris/Estructura de fondo)
    # Eje horizontal principal
    shapes_list.append(dict(type="rect", x0=0.8, y0=1.8, x1=8.7, y1=2.2, fillcolor="#D5D8DC", line=dict(color="#7F8C8D", width=2), layer="below"))
    # Ramal vertical 1
    shapes_list.append(dict(type="rect", x0=6.3, y0=2.0, x1=6.7, y1=4.3, fillcolor="#D5D8DC", line=dict(color="#7F8C8D", width=2), layer="below"))
    # Ramal vertical 2
    shapes_list.append(dict(type="rect", x0=7.8, y0=2.0, x1=8.2, y1=6.3, fillcolor="#D5D8DC", line=dict(color="#7F8C8D", width=2), layer="below"))

    # 2. Trazado de Componentes (TL, TS, TR, IT)
    for key, item in elements.items():
        st_cfg = style_config[item["type"]]

        if item["shape"] == "circle":
            r = item["r"]
            shapes_list.append(dict(
                type="circle",
                xref="x", yref="y",
                x0=item["x"] - r, y0=item["y"] - r,
                x1=item["x"] + r, y1=item["y"] + r,
                line=dict(color=st_cfg["line"], width=st_cfg["width"]),
                fillcolor=st_cfg["fill"]
            ))
            center_x, center_y = item["x"], item["y"]
        else:
            shapes_list.append(dict(
                type="rect",
                xref="x", yref="y",
                x0=item["x0"], y0=item["y0"],
                x1=item["x1"], y1=item["y1"],
                line=dict(color=st_cfg["line"], width=st_cfg["width"]),
                fillcolor=st_cfg["fill"]
            ))
            center_x = (item["x0"] + item["x1"]) / 2
            center_y = (item["y0"] + item["y1"]) / 2

        # Puntos invisibles sobre cada figura para capturar 'Hover' y clics con precisión
        fig.add_trace(go.Scatter(
            x=[center_x],
            y=[center_y],
            mode="markers+text",
            marker=dict(size=20, color="rgba(0,0,0,0)"),
            text=[key],
            textposition="middle center",
            name=item["name"],
            hovertemplate=f"<b>{item['name']}</b><br>Código: {key}<extra></extra>"
        ))

    # Ajustes visuales de la vista de planta
    fig.update_layout(
        shapes=shapes_list,
        xaxis=dict(visible=False, range=[0, 9.5]),
        yaxis=dict(visible=False, range=[0.5, 7.0], scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        height=520
    )
    return fig

# ==========================================
# 3. INTERFAZ EN STREAMLIT
# ==========================================
st.title("Plano CAD Interactivo - Segmento de Conveyors")
st.write("Demostración de reconstrucción exacta del segmento mediante elementos vectoriales en Python.")

col_grafica, col_panel = st.columns([7, 3])

with col_grafica:
    st.plotly_chart(build_layout(), use_container_width=True)

with col_panel:
    st.subheader("Panel de Inspección")
    selected_id = st.selectbox("Selecciona un elemento para inspeccionar sus temas específicos:", list(elements.keys()))

    if selected_id:
        data = elements[selected_id]
        
        # Formato dinámico según tipo de elemento
        if data["type"] == "TR":
            st.markdown(f"### 🟠 {data['name']}")
            st.metric("Estado", data["status"])
            st.write(f"**Velocidad de Giro:** {data['rpm']}")
            st.info("Configuración de transferencias de flujo a 90° y 180° activas.")

        elif data["type"] == "IT":
            st.markdown(f"### 🔴 {data['name']}")
            st.metric("Tiempo de Ciclo", data["ciclo"])
            st.metric("Piezas Procesadas", data["piezas"])
            st.warning("Próximo mantenimiento de mesa de indexado en 120 horas.")

        elif data["type"] in ["TL", "TS"]:
            st.markdown(f"### 🔷 {data['name']}")
            st.write(f"**Longitud del segmento:** {data['longitud']}")
            st.write(f"**Velocidad de Banda:** {data['speed']}")
            st.success("Sensores de presencia alineados correctamente.")
