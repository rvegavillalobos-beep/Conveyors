import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Trolley Availability & Trolley Capacity Ramp-Up", layout="wide")

# --- SIDEBAR CONTROLS (Interactivity) ---
st.sidebar.header("⚙️ Simulation Parameters")

# Unit selection format
unit_mode = st.sidebar.selectbox(
    "Unit Display Format", 
    ["UPH (Units / Hour)", "Units / Week", "Units / Day"]
)

adjustment_rate = st.sidebar.slider("Mechanical Adjustment Rate (units/week)", min_value=1, max_value=10, value=2, step=1)
target_trolleys_for_30_uph = st.sidebar.slider("Trolleys required for 30 UPH", min_value=60, max_value=200, value=90, step=5)
base_fleet = st.sidebar.number_input("Base Fleet Initial", min_value=20, max_value=60, value=35, step=5)

st.sidebar.subheader("📦 Shipments & Customs Configuration")
transit_weeks = 4  # 4 semanas estándar de tránsito fijo

batch1_qty = st.sidebar.number_input("Batch 1 Quantity", min_value=10, max_value=50, value=24, step=2)
batch1_start_week = st.sidebar.selectbox("Batch 1 Shipment Start Week", [f"CW{i}" for i in range(46, 53)] + [f"CW{i}" for i in range(1, 14)], index=0)
batch1_customs = st.sidebar.slider("Batch 1 Customs Duration (weeks)", min_value=1, max_value=2, value=2, key="b1_customs")

batch2_qty = st.sidebar.number_input("Batch 2 Quantity", min_value=10, max_value=60, value=30, step=2)
batch2_start_week = st.sidebar.selectbox("Batch 2 Shipment Start Week", [f"CW{i}" for i in range(46, 53)] + [f"CW{i}" for i in range(1, 14)], index=7, key="b2_start")
batch2_customs = st.sidebar.slider("Batch 2 Customs Duration (weeks)", min_value=1, max_value=2, value=2, key="b2_customs")

# --- SCRAP CONFIGURATION ---
st.sidebar.subheader("🗑️ Scrap Line Configuration")
enable_scrap = st.sidebar.checkbox("Activate Scrap Line", value=False)
scrap_pct = st.sidebar.slider("Scrap Percentage (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.5)

# 1. Timeline Setup: Extended to CW13
weeks = [f"CW{i}" for i in range(46, 53)] + [f"CW{i}" for i in range(1, 14)]
n_weeks = len(weeks)

# Determine arrival indices: 4 weeks of transit + customs duration
b1_start_idx = weeks.index(batch1_start_week)
b1_arrival_idx = min(b1_start_idx + transit_weeks + batch1_customs, n_weeks - 1)

b2_start_idx = weeks.index(batch2_start_week)
b2_arrival_idx = min(b2_start_idx + transit_weeks + batch2_customs, n_weeks - 1)

# 2. Simulation Logic for Trolleys & Capacity
current_physical = base_fleet
current_operational = base_fleet

phys_stock = []
op_stock = []
uph_capacity = []

for idx, w in enumerate(weeks):
    if idx == b1_arrival_idx:
        current_physical += batch1_qty
    if idx == b2_arrival_idx:
        current_physical += batch2_qty
        
    phys_stock.append(current_physical)
    
    # Mechanical adjustment logic: paused during Shutdown (CW52 and CW1)
    is_shutdown = (w in ["CW52", "CW1"])
    
    if not is_shutdown and current_operational < current_physical:
        current_operational = min(current_physical, current_operational + adjustment_rate)
        
    op_stock.append(current_operational)
    
    # Base calculation in UPH (30 UPH per target trolleys)
    calculated_uph = round((current_operational / float(target_trolleys_for_30_uph)) * 30, 1)
    uph_capacity.append(calculated_uph)

# 3. Weekly Production Raw Data (Units / Week) & Unit Conversion Scaling Factor
raw_production_up_to_cw8 = [49, 69, 123, 147, 184, 196, 0, 0, 176, 199, 223, 246, 206, 270, 281]

if unit_mode == "UPH (Units / Hour)":
    scale_factor = 1.0  
    demand_divisor = 45.0
    y_label_secondary = "Trolley Capacity, Demand & Scrap (UPH)"
    max_y_secondary = 35
elif unit_mode == "Units / Week":
    scale_factor = 45.0  
    demand_divisor = 1.0
    y_label_secondary = "Trolley Capacity, Demand & Scrap (Units / Week)"
    max_y_secondary = 1500
else:  
    scale_factor = 45.0 / 5.0  
    demand_divisor = 5.0
    y_label_secondary = "Trolley Capacity, Demand & Scrap (Units / Day)"
    max_y_secondary = 300

scaled_uph_capacity = [round(val * scale_factor, 1) for val in uph_capacity]
production_demand_converted = [round(p / demand_divisor, 1) if p > 0 else 0.0 for p in raw_production_up_to_cw8]

while len(production_demand_converted) < n_weeks:
    production_demand_converted.append(None)

# Calculate Scrap Series based on Converted Demand and Selected Percentage
scrap_converted = [
    round(val * (scrap_pct / 100.0), 1) if val is not None and val > 0 else 0.0 
    for val in production_demand_converted
]

df = pd.DataFrame({
    "Week": weeks,
    "Physical": phys_stock,
    "Operational": op_stock,
    "Capacity_Converted": scaled_uph_capacity,
    "Demand_Converted": production_demand_converted,
    "Scrap_Converted": scrap_converted
})

cw8_index = weeks.index("CW8")

# 4. Professional Matplotlib Figure with Dual Axes
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 6.5), gridspec_kw={'height_ratios': [3, 0.7], 'hspace': 0.05}, sharex=True)

x = np.arange(n_weeks)
width = 0.65

# --- TOP CHART: PRIMARY AXIS (TROLLEYS BARS) ---
ax1.bar(x, df["Operational"], width, label='Operational Available Trolleys', color='#1F4E79')
ax1.bar(x, df["Physical"] - df["Operational"], width, bottom=df["Operational"], 
        label='Pending Adjustment', color='#D9E1F2', alpha=0.8)

ax1.set_ylabel('Available Trolleys', fontsize=11, fontweight='bold', color='#1F4E79')
ax1.set_title('Trolley Availability & Trolley Capacity vs. Production Demand (Up to CW8)', fontsize=13, fontweight='bold', pad=15, color='#1F4E79')
ax1.set_xticks(x)
ax1.set_xticklabels(weeks, rotation=45, ha='right', fontsize=9)

ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.spines['left'].set_color('#BFBFBF')
ax1.spines['bottom'].set_color('#BFBFBF')
ax1.grid(axis='y', linestyle='--', alpha=0.4)

max_limit = max(df["Physical"]) + 15
ax1.set_ylim(0, max_limit)
ax1.set_yticks(range(0, int(max_limit) + 1, 15))

for i, v in enumerate(df["Operational"]):
    ax1.text(i, v + 0.8, str(v), ha='center', va='bottom', fontsize=7.5, fontweight='semibold', color='#333333')


# --- TOP CHART: SECONDARY AXIS (CAPACITY, DEMAND & SCRAP) ---
coral_color = '#D96852'
prod_line_color = '#27AE60'
scrap_line_color = '#E67E22'

ax_uph = ax1.twinx()

# Capacity Line
ax_uph.plot(x, df["Capacity_Converted"], color=coral_color, marker='o', linewidth=2.0, markersize=4.5, label=f'Capacity ({unit_mode.split()[0]})')
for i, val in enumerate(df["Capacity_Converted"]):
    ax_uph.text(i, val - (max_y_secondary * 0.03), f"{val}", ha='center', va='top', fontsize=6.5, fontweight='bold', color=coral_color)

# Production Demand Line
ax_uph.plot(x, df["Demand_Converted"], color=prod_line_color, marker='s', linewidth=2.2, markersize=5, label=f'Production Demand ({unit_mode.split()[0]})')
for i, val in enumerate(df["Demand_Converted"]):
    if val is not None and val > 0:
        ax_uph.text(i, val + (max_y_secondary * 0.03), f"{val}", ha='center', va='bottom', fontsize=6.5, fontweight='bold', color=prod_line_color)

# Optional Scrap Line
if enable_scrap:
    ax_uph.plot(x, df["Scrap_Converted"], color=scrap_line_color, marker='^', linestyle='--', linewidth=1.8, markersize=4.5, label=f'Scrap ({scrap_pct}%)')
    for i, val in enumerate(df["Scrap_Converted"]):
        if val is not None and val > 0:
            ax_uph.text(i, val + (max_y_secondary * 0.07), f"{val}", ha='center', va='bottom', fontsize=6, fontweight='bold', color=scrap_line_color)

ax_uph.set_ylabel(y_label_secondary, fontsize=11, fontweight='bold', color=coral_color)
ax_uph.tick_params(axis='y', labelcolor=coral_color)
ax_uph.set_ylim(0, max_y_secondary)
ax_uph.spines['top'].set_visible(False)
ax_uph.spines['left'].set_visible(False)
ax_uph.spines['right'].set_color(coral_color)
ax_uph.grid(False)

lines_1, labels_1 = ax1.get_legend_handles_labels()
lines_2, labels_2 = ax_uph.get_legend_handles_labels()
ax1.legend(lines_1 + lines_2, labels_1 + labels_2, frameon=False, loc='upper left', fontsize=8)


# --- BOTTOM TRACKER: TIMELINE WITH BATCH 1 & BATCH 2 LABELS ---
ax2.set_ylabel('Additional Shipments', fontsize=10, fontweight='bold', color='#1F4E79', rotation=90, labelpad=20, va='center')

# Batch 1 Tracker Rendering (Transit 4W + Customs)
b1_s_idx = weeks.index(batch1_start_week)
ax2.barh(y=1, width=transit_weeks, left=b1_s_idx, height=0.5, color='#FFF2CC', edgecolor='#D6B656', hatch='//')
ax2.text(b1_s_idx + (transit_weeks / 2.0), 1, f'BATCH 1 (+{batch1_qty})', ha='center', va='center', fontsize=6.5, fontweight='bold', color='#7F6000')

ax2.barh(y=1, width=batch1_customs, left=b1_s_idx + transit_weeks, height=0.5, color='#FFE599', edgecolor='#D6B656')
ax2.text(b1_s_idx + transit_weeks + (batch1_customs / 2.0), 1, 'CUSTOMS', ha='center', va='center', fontsize=6.5, fontweight='bold', color='#7F6000')

# Batch 2 Tracker Rendering (Transit 4W + Customs)
b2_s_idx = weeks.index(batch2_start_week)
ax2.barh(y=0, width=transit_weeks, left=b2_s_idx, height=0.5, color='#FFF2CC', edgecolor='#D6B656', hatch='//')
ax2.text(b2_s_idx + (transit_weeks / 2.0), 0, f'BATCH 2 (+{batch2_qty})', ha='center', va='center', fontsize=6.5, fontweight='bold', color='#7F6000')

ax2.barh(y=0, width=batch2_customs, left=b2_s_idx + transit_weeks, height=0.5, color='#FFE599', edgecolor='#D6B656')
ax2.text(b2_s_idx + transit_weeks + (batch2_customs / 2.0), 0, 'CUSTOMS', ha='center', va='center', fontsize=6.5, fontweight='bold', color='#7F6000')

ax2.set_yticks([])
ax2.set_xlim(-0.5, n_weeks - 0.5)
ax2.set_ylim(-0.5, 1.5)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.spines['left'].set_visible(False)
ax2.spines['bottom'].set_color('#BFBFBF')
ax2.grid(axis='x', linestyle=':', alpha=0.5)

plt.tight_layout()

# Render Matplotlib Figure in Streamlit
st.pyplot(fig)
plt.close(fig)

# --- METRICS ROW (CW8) ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Base Fleet", value=f"{base_fleet} Units")
with col2:
    st.metric(label="Max Operational (CW8)", value=f"{op_stock[cw8_index]} Units")
with col3:
    st.metric(label=f"Capacity at CW8 ({unit_mode.split()[0]})", value=f"{scaled_uph_capacity[cw8_index]}")
with col4:
    st.metric(label="Adjustment Rate", value=f"{adjustment_rate} u/wk")

st.markdown("---")

# --- INFORMATIVE TROLLEY IMAGE AT THE VERY BOTTOM ---
st.image("table.jpg", use_container_width=True)
