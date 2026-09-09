import streamlit as st
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Layout Interactivo - Streamlit")

st.title("Plano Esquemático Interactivo de Conveyors")

# Base de datos simplificada
nodes = {
    "TR_01": {"x": 1, "y": 1, "type": "TR", "name": "Turning Table 1", "status": "Operativo"},
    "TL_01": {"x": 2, "y": 1, "type": "TL", "name": "Conveyor TL 01", "length": "2.5m"},
    "IT_01": {"x": 3, "y": 1, "type": "Indexing Table", "name": "Indexing Table 01", "cycle_time": "4.5s"},
}

connections = [("TR_01", "TL_01"), ("TL_01", "IT_01")]

# Crear gráfica Plotly
fig = go.Figure()

for start, end in connections:
    fig.add_trace(go.Scatter(
        x=[nodes[start]["x"], nodes[end]["x"]],
        y=[nodes[start]["y"], nodes[end]["y"]],
        mode="lines",
        line=dict(color="#BDC3C7", width=10),
        hoverinfo="none",
        showlegend=False
    ))

for node_id, data in nodes.items():
    color = "#E67E22" if data["type"] == "TR" else ("#1F77B4" if data["type"] == "TL" else "#D62728")
    fig.add_trace(go.Scatter(
        x=[data["x"]],
        y=[data["y"]],
        mode="markers+text",
        marker=dict(color=color, size=25),
        text=[node_id],
        textposition="bottom center",
        name=data["name"]
    ))

fig.update_layout(
    xaxis=dict(visible=False),
    yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
    plot_bgcolor="white",
    height=400,
    margin=dict(l=10, r=10, t=10, b=10)
)

# Layout en 2 Columnas
col1, col2 = st.columns([7, 3])

with col1:
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Panel de Control")
    selected_node = st.selectbox("Selecciona un elemento para inspeccionar:", list(nodes.keys()))
    
    if selected_node:
        item = nodes[selected_node]
        st.write(f"**Nombre:** {item['name']}")
        st.write(f"**Tipo:** {item['type']}")
        for k, v in item.items():
            if k not in ["x", "y", "type", "name"]:
                st.write(f"**{k.capitalize()}:** {v}")
