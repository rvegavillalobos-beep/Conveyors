import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

st.set_page_config(layout="wide", page_title="Lector y Reconstructor de Layout CAD")

st.title("Reconstructor Automático de Layouts CAD")
st.write("Carga la imagen de tu layout para vectorizar las formas (sin relleno) y obtener el inventario automático.")

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
                
                # Convertir origen Y a sistema cartesiano
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
    # 4. GENERACIÓN DE LA GRÁFICA (SIN RELLENO)
    # ==========================================
    fig = go.Figure()
    shapes = []

    for elem_id, elem in detected_elements.items():
        # Relleno 100% transparente para distinguir mejor las líneas/fondos
        transparent_fill = "rgba(0, 0, 0, 0)"

        if elem["shape"] == "circle":
            r = max(elem["w"], elem["h"]) / 2.0
            shapes.append(dict(
                type="circle", xref="x", yref="y",
                x0=elem["x"] - r, y0=elem["y"] - r,
                x1=elem["x"] + r, y1=elem["y"] + r,
                line=dict(color=elem["color"], width=3),
                fillcolor=transparent_fill
            ))
        else:
            shapes.append(dict(
                type="rect", xref="x", yref="y",
                x0=elem["x"] - elem["w"] / 2.0, y0=elem["y"] - elem["h"] / 2.0,
                x1=elem["x"] + elem["w"] / 2.0, y1=elem["y"] + elem["h"] / 2.0,
                line=dict(color=elem["color"], width=3),
                fillcolor=transparent_fill
            ))

        # Marcadores interactivos para Hover/Clics
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
        height=680
    )

    # ==========================================
    # 5. TABLA Y MÉTRICAS DE CONTEO
    # ==========================================
    counts_by_label = {}
    for elem in detected_elements.values():
        lbl = elem["label"]
        counts_by_label[lbl] = counts_by_label.get(lbl, 0) + 1

    df_summary = pd.DataFrame(
        list(counts_by_label.items()), 
        columns=["Tipo de Elemento", "Cantidad"]
    ).sort_values(by="Cantidad", ascending=False)

    total_count = len(detected_elements)

    # ==========================================
    # 6. DESPLIEGUE EN LA INTERFAZ
    # ==========================================
    col_map, col_panel = st.columns([7, 3])

    with col_map:
        st.plotly_chart(fig, use_container_width=True)

    with col_panel:
        st.subheader("Resumen de Componentes")
        
        # Métrica global
        st.metric("Total de Elementos Detectados", total_count)
        
        # Tabla detallada por tipo
        st.write("### Conteo por Categoría")
        st.dataframe(df_summary, use_container_width=True, hide_index=True)

        st.divider()

        # Inspección individual
        if detected_elements:
            st.write("### Inspección Individual")
            selected_id = st.selectbox("Seleccionar elemento:", list(detected_elements.keys()))
            if selected_id:
                item = detected_elements[selected_id]
                st.markdown(f"**ID:** `{selected_id}`")
                st.write(f"**Categoría:** {item['label']}")
                st.write(f"**Centro X, Y:** ({item['x']:.1f}, {item['y']:.1f})")
                st.write(f"**Ancho x Alto:** {item['w']}px x {item['h']}px")

else:
    st.info("Por favor, sube una imagen de layout para comenzar el procesamiento.")
