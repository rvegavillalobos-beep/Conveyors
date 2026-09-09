import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go

# Initialize the Dash app
app = dash.Dash(__name__, title="Layout Interactivo de Conveyors")

# ==========================================
# 1. BASE DE DATOS Y TOPOLOGÍA DEL SEGMENTO
# ==========================================
# Coordenadas aproximadas tomadas de tu segmento de imagen (eje X, eje Y)
nodes = {
    # Mesas Giratorias / Intersecciones (Orange Circles)
    "TR_01": {"x": 1, "y": 1, "type": "TR", "name": "Turning Table 1 (TR-01)", "status": "Operativo", "speed": "1.2 m/s"},
    "TR_02": {"x": 6, "y": 1, "type": "TR", "name": "Turning Table 2 (TR-02)", "status": "Operativo", "speed": "1.2 m/s"},
    "TR_03": {"x": 8, "y": 1, "type": "TR", "name": "Turning Table 3 (TR-03)", "status": "Operativo", "speed": "1.2 m/s"},
    
    # Rectángulos Azules Grandes (TL)
    "TL_01": {"x": 2, "y": 1, "type": "TL", "name": "Conveyor TL 01", "length": "2.5m", "load": "85%"},
    "TL_02": {"x": 4, "y": 1, "type": "TL", "name": "Conveyor TL 02", "length": "2.5m", "load": "40%"},
    "TL_03": {"x": 6, "y": 3, "type": "TL", "name": "Conveyor TL 03 (Vertical)", "length": "2.0m", "load": "0%"},
    "TL_04": {"x": 8, "y": 5, "type": "TL", "name": "Conveyor TL 04 (Superior)", "length": "3.0m", "load": "12%"},

    # Rectángulos Azules Claro Chicos (TS)
    "TS_01": {"x": 7, "y": 1, "type": "TS", "name": "Conveyor Short TS 01", "length": "0.8m", "sensor": "OK"},
    "TS_02": {"x": 8, "y": 4, "type": "TS", "name": "Conveyor Short TS 02", "length": "0.8m", "sensor": "OK"},

    # Rectángulos Rojos (Indexing Tables)
    "IT_01": {"x": 3, "y": 1, "type": "Indexing Table", "name": "Indexing Table 01", "cycle_time": "4.5s", "parts_count": 1420},
    "IT_02": {"x": 8, "y": 3, "type": "Indexing Table", "name": "Indexing Table 02", "cycle_time": "4.8s", "parts_count": 1395},
}

# Conexiones físicas (Conveyors/Líneas grises de fondo)
connections = [
    ("TR_01", "TL_01"),
    ("TL_01", "IT_01"),
    ("IT_01", "TL_02"),
    ("TL_02", "TR_02"),
    ("TR_02", "TS_01"),
    ("TS_01", "TR_03"),
    ("TR_02", "TL_03"),  # Rama vertical 1
    ("TR_03", "IT_02"),  # Rama vertical 2
    ("IT_02", "TS_02"),
    ("TS_02", "TL_04")
]

# Definición de Estilos Visuales según el tipo
styles = {
    "TR": {"color": "#E67E22", "symbol": "circle", "size": 28, "label": "Turning Table (TR)"},
    "TL": {"color": "#1F77B4", "symbol": "square", "size": 32, "label": "Conveyor TL"},
    "TS": {"color": "#17BECF", "symbol": "square-open", "size": 20, "label": "Conveyor Short (TS)"},
    "Indexing Table": {"color": "#D62728", "symbol": "square", "size": 28, "label": "Indexing Table"}
}

# ==========================================
# 2. FUNCIÓN PARA GENERAR LA GRÁFICA INTERACTIVA
# ==========================================
def build_layout_figure():
    fig = go.Figure()

    # 1. Dibujar líneas de conexión (Conveyors base)
    for start, end in connections:
        fig.add_trace(go.Scatter(
            x=[nodes[start]["x"], nodes[end]["x"]],
            y=[nodes[start]["y"], nodes[end]["y"]],
            mode="lines",
            line=dict(color="#BDC3C7", width=12),
            hoverinfo="none",
            showlegend=False
        ))

    # 2. Dibujar cada nodo/componente
    for node_id, data in nodes.items():
        st = styles[data["type"]]
        fig.add_trace(go.Scatter(
            x=[data["x"]],
            y=[data["y"]],
            mode="markers+text",
            marker=dict(
                color=st["color"],
                symbol=st["symbol"],
                size=st["size"],
                line=dict(color="black", width=2)
            ),
            text=[node_id],
            textposition="bottom center",
            name=data["name"],
            customdata=[node_id], # Guardamos el ID para el evento de clic
            hovertemplate=f"<b>{data['name']}</b><br>ID: {node_id}<br>Tipo: {data['type']}<extra></extra>"
        ))

    fig.update_layout(
        title="<b>Layout de Planta - Segmento Interactivo</b>",
        xaxis=dict(visible=False, range=[0, 10]),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1, range=[0, 7]),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=20, r=20, t=50, b=20),
        clickmode="event+select",
        showlegend=False
    )
    return fig

# ==========================================
# 3. DISEÑO DE LA INTERFAZ WEB (LAYOUT)
# ==========================================
app.layout = html.Div(style={"fontFamily": "Segoe UI, sans-serif", "backgroundColor": "#F8F9FA", "padding": "20px"}, children=[
    
    html.H2("Plano Esquemático Interactivo de Conveyors", style={"textAlign": "center", "color": "#2C3E50"}),
    html.P("Haz clic en cualquier elemento del plano para inspeccionar sus detalles técnicos.", style={"textAlign": "center", "color": "#7F8C8D"}),

    # Contenedor principal de dos columnas
    html.Div(style={"display": "flex", "gap": "20px", "marginTop": "20px"}, children=[
        
        # Columna Izquierda: El Plano Interactivo (Plotly)
        html.Div(style={"flex": "7", "backgroundColor": "white", "borderRadius": "8px", "padding": "10px", "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}, children=[
            dcc.Graph(id="layout-graph", figure=build_layout_figure(), style={"height": "600px"})
        ]),

        # Columna Derecha: Panel de Inspección (Dinámico al hacer Clic)
        html.Div(id="details-panel", style={"flex": "3", "backgroundColor": "white", "borderRadius": "8px", "padding": "20px", "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}, children=[
            html.H3("Panel de Inspección", style={"color": "#34495E", "borderBottom": "2px solid #ECF0F1", "paddingBottom": "10px"}),
            html.Div(id="panel-content", children=[
                html.P("👈 Haz clic sobre una mesa, conveyor o estación para ver los datos.", style={"color": "#95A5A6", "fontStyle": "italic"})
            ])
        ])
    ])
])

# ==========================================
# 4. CALLBACK DE INTERACTIVIDAD (LÓGICA)
# ==========================================
@app.callback(
    Output("panel-content", "children"),
    Input("layout-graph", "clickData")
)
def display_click_data(clickData):
    if not clickData:
        return html.P("👈 Haz clic sobre una mesa, conveyor o estación para ver los datos.", style={"color": "#95A5A6", "fontStyle": "italic"})

    # Obtener ID del elemento seleccionado
    point = clickData["points"][0]
    node_id = point.get("customdata", None)

    if not node_id or node_id not in nodes:
        return html.P("Selecciona un elemento válido.")

    item = nodes[node_id]
    item_type = item["type"]

    # --- PANELES ESPECÍFICOS SEGÚN EL TIPO DE ELEMENTO ---
    
    if item_type == "TR": # Turning Tables (Círculos)
        return html.Div([
            html.H4(f"🟠 {item['name']}", style={"color": "#E67E22"}),
            html.Ul([
                html.Li([html.B("Tipo: "), "Turning Table (Mesa Giratoria)"]),
                html.Li([html.B("Estado: "), item["status"]]),
                html.Li([html.B("Velocidad Giro: "), item["speed"]]),
                html.Li([html.B("Ejes Disponibles: "), "0°, 90°, 180°"]),
            ]),
            html.Hr(),
            html.Button("Mantenimiento Preventivo", style={"padding": "8px 12px", "backgroundColor": "#E67E22", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"})
        ])

    elif item_type == "Indexing Table": # Rectángulos Rojos
        return html.Div([
            html.H4(f"🔴 {item['name']}", style={"color": "#D62728"}),
            html.Ul([
                html.Li([html.B("Tipo: "), "Indexing Table (Mesa de Indexado)"]),
                html.Li([html.B("Tiempo de Ciclo: "), item["cycle_time"]]),
                html.Li([html.B("Piezas Procesadas hoy: "), str(item["parts_count"])]),
                html.Li([html.B("Parada de Emergencia: "), "OK"]),
            ]),
            html.Hr(),
            html.Button("Ver Historial de Fallas", style={"padding": "8px 12px", "backgroundColor": "#D62728", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"})
        ])

    elif item_type in ["TL", "TS"]: # Conveyors Azules
        color = "#1F77B4" if item_type == "TL" else "#17BECF"
        return html.Div([
            html.H4(f"🔷 {item['name']}", style={"color": color}),
            html.Ul([
                html.Li([html.B("Tipo: "), f"Conveyor ({item_type})"]),
                html.Li([html.B("Longitud: "), item["length"]]),
                html.Li([html.B("Carga Actual: "), item.get("load", "N/A")]),
                html.Li([html.B("Sensor Fotoeléctrico: "), item.get("sensor", "Activo")]),
            ]),
            html.Hr(),
            html.Button("Ajustar Velocidad Banda", style={"padding": "8px 12px", "backgroundColor": color, "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"})
        ])

if __name__ == "__main__":
    app.run(debug=True)
