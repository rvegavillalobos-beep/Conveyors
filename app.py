import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Trolley Availability & Trolley Capacity Ramp-Up", layout="wide")

st.title("📦 Trolley Availability & Trolley Capacity vs. Production Demand")
st.markdown("Interactive simulation of trolley availability and trolley-based capacity constrained by the mechanical adjustment rate (Paused during CW52 & CW1 Shutdown).")

# --- SIDEBAR CONTROLS (Interactivity) ---
st.sidebar.header("⚙️ Simulation Parameters")
adjustment_rate = st.sidebar.slider("Mechanical Adjustment Rate (units/week)", min_value=1, max_value=10, value=2, step=1)
target_trolleys_for_30_uph = st.sidebar.slider("Trolleys required for 30 UPH", min_value=60, max_value=200, value=90, step=5)
base_fleet = st.sidebar.number_input("Base Fleet Initial", min_value=20, max_value=60, value=35, step=5)
batch1_qty = st.sidebar.number_input("Batch 1 Quantity (CW1)", min_value=10, max_value=50, value=24, step=2)
batch2_qty = st.sidebar.number_input("Batch 2 Quantity (CW8)", min_value=10, max_value=60, value=30, step=2)

# 1. Timeline Setup: Extended to CW13
weeks = [f"CW{i}" for i in range(46, 53)] + [f"CW{i}" for i in range(1, 14)]
n_weeks = len(weeks)

# 2. Simulation Logic for Trolleys & UPH Capacity
current_physical = base_fleet
current_operational = base_fleet

phys_stock = []
op_stock = []
uph_capacity = []

for idx, w in enumerate(weeks):
    if idx == 7:  # Starting CW1
        current_physical += batch1_qty
    if idx == 14: # Starting CW8
        current_physical += batch2_qty
        
    phys_stock.append(current_physical)
    
    # Mechanical adjustment logic: paused during Shutdown (CW52 and CW1)
    is_shutdown = (weeks[idx] in ["CW52", "CW1"])
    
    if not is_shutdown and current_operational < current_physical:
        current_operational = min(current_physical, current_operational + adjustment_rate)
        
    op_stock.append(current_operational)
    
    # Calculate available trolley-based capacity based on dynamic ratio
    calculated_uph = round((current_operational / float(target_trolleys_for_30_uph)) * 30, 1)
    uph_capacity.append(calculated_uph)

# 3. Weekly Production Data Converted to UPH (45 hrs/week: 5 days * 9 hours)
raw_production_up_to_cw8 = [49, 69, 123, 147, 184, 196, 0, 0, 176, 199, 223, 246, 206, 270, 281]
production_uph_demand = [round(p / 45.0, 1) if p > 0 else 0.0 for p in raw_production_up_to_cw8]

while len(production_uph_demand) < n_weeks:
    production_uph_demand.append(None)

df = pd.DataFrame({
    "Week": weeks,
    "Physical": phys_stock,
    "Operational": op_stock,
    "UPH_Capacity": uph_capacity,
    "Prod_UPH_Demand": production_uph_demand
})

# Índice para CW8 en nuestra lista 'weeks' (CW46=0 ... CW8 se encuentra en el índice donde weeks[i] == 'CW8')
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

# Annotate trolley numbers on top of bars
for i, v in enumerate(df["Operational"]):
    ax1.text(i, v + 0.8, str(v), ha='center', va='bottom', fontsize=7.5, fontweight='semibold', color='#333333')


# --- TOP CHART: SECONDARY AXIS (TROLLEY CAPACITY LINE & PRODUCTION DEMAND LINE) ---
coral_color = '#D96852'
prod_line_color = '#27AE60'  # Green line for production UPH demand

ax_uph = ax1.twinx()

# Line 1: Trolley-Based Capacity (UPH)
ax_uph.plot(x, df["UPH_Capacity"], color=coral_color, marker='o', linewidth=2.0, markersize=4.5, label='Trolley-Based Capacity (UPH)')

# Annotate UPH values tightly below each point on the orange line
for i, uph in enumerate(df["UPH_Capacity"]):
    ax_uph.text(i, uph - 0.8, f"{uph}", ha='center', va='top', fontsize=6.5, fontweight='bold', color=coral_color)

# Line 2: Production Demand (UPH)
ax_uph.plot(x, df["Prod_UPH_Demand"], color=prod_line_color, marker='s', linewidth=2.2, markersize=5, label='Production Demand (UPH)')

ax_uph.set_ylabel('Trolley Capacity & Demand (UPH)', fontsize=11, fontweight='bold', color=coral_color)
ax_uph.tick_params(axis='y', labelcolor=coral_color)
ax_uph.set_ylim(0, 35)
ax_uph.spines['top'].set_visible(False)
ax_uph.spines['left'].set_visible(False)
ax_uph.spines['right'].set_color(coral_color)
ax_uph.grid(False)

# Annotate Production UPH values near markers up to CW8
for i, val in enumerate(df["Prod_UPH_Demand"]):
    if val is not None and val > 0:
        ax_uph.text(i, val + 1.2, f"{val}", ha='center', va='bottom', fontsize=6.5, fontweight='bold', color=prod_line_color)

# Combine legends cleanly on top left
lines_1, labels_1 = ax1.get_legend_handles_labels()
lines_2, labels_2 = ax_uph.get_legend_handles_labels()
ax1.legend(lines_1 + lines_2, labels_1 + labels_2, frameon=False, loc='upper left', fontsize=8.5)


# --- BOTTOM TRACKER: TIMELINE MILESTONES (Batch and Customs only) ---
ax2.set_ylabel('Additional Shipments', fontsize=10, fontweight='bold', color='#1F4E79', rotation=90, labelpad=20, va='center')

# Row 1: Batch 1
ax2.barh(y=1, width=4, left=1, height=0.5, color='#FFF2CC', edgecolor='#D6B656', hatch='//')
ax2.text(3, 1, f'BATCH 1 Shipment +{batch1_qty}', ha='center', va='center', fontsize=7.5, fontweight='bold', color='#7F6000')

ax2.barh(y=1, width=2, left=5, height=0.5, color='#FFE599', edgecolor='#D6B656')
ax2.text(6, 1, 'CUSTOMS', ha='center', va='center', fontsize=7, fontweight='bold', color='#7F6000')

# Row 2: Batch 2
ax2.barh(y=0, width=4, left=8, height=0.5, color='#FFF2CC', edgecolor='#D6B656', hatch='//')
ax2.text(10, 0, f'BATCH 2 Shipment +{batch2_qty}', ha='center', va='center', fontsize=7.5, fontweight='bold', color='#7F6000')

ax2.barh(y=0, width=2, left=12, height=0.5, color='#FFE599', edgecolor='#D6B656')
ax2.text(13, 0, 'CUSTOMS', ha='center', va='center', fontsize=7, fontweight='bold', color='#7F6000')

# Styling bottom timeline tracker
ax2.set_yticks([])
ax2.set_xlim(-0.5, n_weeks - 0.5)
ax2.set_ylim(-0.5, 1.5)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.spines['left'].set_visible(False)
ax2.spines['bottom'].set_color('#BFBFBF')
ax2.grid(axis='x', linestyle=':', alpha=0.5)

plt.tight_layout()

# 4. Render in Streamlit
st.pyplot(fig)
plt.close(fig)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Base Fleet", value=f"{base_fleet} Units")
with col2:
    st.metric(label="Max Operational (CW8)", value=f"{op_stock[cw8_index]} Units")
with col3:
    st.metric(label="Trolley Capacity at CW8", value=f"{uph_capacity[cw8_index]} UPH")
with col4:
    st.metric(label="Adjustment Rate", value=f"{adjustment_rate} u/wk")
