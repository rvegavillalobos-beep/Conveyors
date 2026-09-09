import cv2
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

st.set_page_config(layout="wide", page_title="Lector y Reconstructor de Layout CAD")

st.title("Reconstructor Automático de Layouts CAD")
st.write("Carga la imagen de tu layout con marcadores de color para generar automáticamente el mapa interactivo vectorizado.")

# ==========================================
# 1. EXPLORADOR DE ARCHIVOS (FILE UPLOADER)
# ==========================================
uploaded_file = st.file_uploader(
    "Selecciona la imagen de tu layout (PNG, JPG, JPEG):", 
    type=["png", "jpg", "jpeg"]
)

if uploaded_file is not None:
    # Cargar y convertir imagen para OpenCV
    image = Image.open(uploaded_file).convert("RGB")
    img_np = np.array(image)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    height, width, _ = img_np.shape

    # ==========================================
    # 2. CONFIGURACIÓN DE RANGOS HSV POR COLOR
    # ==========================================
    color_ranges = {
        "TV_TurningTable": {
            "lower": np.array([5, 120, 120]), "upper": np.array([25, 255, 255]),
            "color": "#E67E22", "shape": "circle", "label": "TV - Turning Table"
        },
        "TL_Longitudinal": {
            "lower": np.array([95, 120, 120]), "upper": np.array([125, 255, 255]),
            "color": "#1F77B4", "shape": "rect", "label": "TL - Longitudinal Conveyor"
        },
        "TV_IndexingTable": {
            "lower": np.array([0, 120, 120]), "upper": np.array([10, 255, 255]),
            "color": "#D62728", "shape": "rect", "label": "TV - Indexing Table"
        },
        "TU_CornerConverter": {
            "lower": np.array([100, 120, 30]), "upper": np.array([120, 255, 120]),
            "color": "#0B3C5D", "shape": "rect", "label": "TU - Corner Converter"
        },
        "LiftingDoor": {
            "lower": np.array([20, 120, 120]), "upper": np.array([35, 255, 255]),
            "color": "#D4AC0D", "shape": "rect", "label": "Lifting Conveyor / Door"
        },
        "Lifter": {
            "lower": np.array([0, 0, 0]), "upper": np.array([180, 255, 40]),
            "color": "#1C2833", "shape": "rect", "label": "LIFTER"
        }
    }

    # ==========================================
    # 3. DETECCIÓN AUTOMÁTICA CON OPENCV
    # ==========================================
    detected_elements = {}

    for label, config in color_ranges.items():
        mask = cv2.inRange(hsv, config["lower"], config["upper"])
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        count = 1
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 15: # Filtro de ruido
                x, y, w, h = cv2.boundingRect(cnt)
                
                # Convertir origen Y a sistema cartesiano (inferior izquierdo)
                y_cartesian = height - y 
                elem_id = f"{label}_{count}"
                
                detected_elements[elem_id] = {
                    "type": label,
                    "label": config["label"],
                    "x": x + w / 2.0,
                    "y": y_cartesian - h / 2.0,
                    "w": w,
                    "h": h,
                    "color": config["color"],
                    "shape": config["shape"]
                }
                count += 1

    # ==========================================
    # 4. GENERACIÓN DE LA GRÁFICA VECTORIAL
    # ==========================================
    fig = go.Figure()
    shapes = []

    for elem_id, elem in detected_elements.items():
        if elem["shape"] == "circle":
            r = max(elem["w"], elem["h"]) / 2.0
            shapes.append(dict(
                type="circle", xref="x", yref="y",
                x0=elem["x"] - r, y0=elem["y"] - r,
                x1=elem["x"] + r, y1=elem["y"] + r,
                line=dict(color=elem["color"], width=2),
                fillcolor="rgba(0,0,0,0)"
            ))
        else:
            shapes.append(dict(
                type="rect", xref="x", yref="y",
                x0=elem["x"] - elem["w"] / 2.0, y0=elem["y"] - elem["h"] / 2.0,
                x1=elem["x"] + elem["w"] / 2.0, y1=elem["y"] + elem["h"] / 2.0,
                line=dict(color=elem["color"], width=2),
                fillcolor=elem["color"]
            ))

        # Marcadores interactivos para Hover y Selección
        fig.add_trace(go.Scatter(
            x=[elem["x"]], y=[elem["y"]],
            mode="markers",
            marker=dict(size=12, color="rgba(0,0,0,0)"),
            name=elem_id,
            hovertemplate=f"<b>{elem_id}</b><br>Tipo: {elem['label']}<br>Dimensiones: {elem['w']}px x {elem['h']}px<extra></extra>"
        ))

    fig.update_layout(
        shapes=shapes,
        xaxis=dict(visible=False, range=[0, width]),
        yaxis=dict(visible=False, range=[0, height], scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        height=650
    )

    # ==========================================
    # 5. DESPLIEGUE EN LA INTERFAZ
    # ==========================================
    st.success(f"Detección completada: Se encontraron {len(detected_elements)} elementos automáticamente.")

    col_map, col_panel = st.columns([7, 3])

    with col_map:
        st.plotly_chart(fig, use_container_width=True)

    with col_panel:
        st.subheader("Panel de Inspección")
        
        if detected_elements:
            selected_id = st.selectbox("Selecciona un elemento detectado:", list(detected_elements.keys()))
            
            if selected_id:
                item = detected_elements[selected_id]
                st.markdown(f"### `{selected_id}`")
                st.write(f"**Categoría:** {item['label']}")
                st.write(f"**Centro (X, Y):** ({item['x']:.1f}, {item['y']:.1f})")
                st.write(f"**Ancho:** {item['w']} px | **Alto:** {item['h']} px")
                st.divider()
                
                # Telemetría de ejemplo
                if item["shape"] == "circle":
                    st.metric("Velocidad de Giro", "1.2 m/s")
                    st.metric("Estado", "Operativo")
                else:
                    st.metric("Estado de Línea", "Activo")
                    st.metric("Carga Detectada", " Normal")
        else:
            st.warning("No se detectaron formas con los rangos de color predeterminados.")

else:
    st.info("Por favor, sube una imagen de layout para comenzar el procesamiento.")
