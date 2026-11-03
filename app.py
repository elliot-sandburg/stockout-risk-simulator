"""
Stockout Risk Simulator & Working Capital Engine (v1)
An interactive supply chain dashboard comparing Static, Closed-Form,
and Simulated Reorder Points under variable demand and vendor lead times.
"""

import math
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# Import the verified mathematical engine
from replenishment import (
    closed_form_reorder_point,
    daily_demand_moments,
    simulate_cycles,
    simulated_reorder_point,
    simulate_lead_time_demand,
    static_reorder_point,
)

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Stockout Risk & Working Capital Simulator",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Stockout Risk & Working Capital Simulator")
st.markdown(
    "Compare textbook inventory policies against Monte Carlo simulation under **vendor lead-time volatility** and **contractor demand spikes**."
)

# -----------------------------------------------------------------------------
# Sidebar: Operational & Commercial Inputs
# -----------------------------------------------------------------------------
st.sidebar.header("1. Daily Demand Parameters")
base_mean = st.sidebar.number_input(
    "Average Daily Sales (Units)", min_value=1.0, value=50.0, step=5.0
)
base_sd = st.sidebar.number_input(
    "Daily Demand Volatility (Std Dev)", min_value=0.1, value=10.0, step=1.0
)

st.sidebar.subheader("Contractor Demand Spikes")
spike_prob = st.sidebar.slider(
    "Spike Probability (Days with bulk buys)", 0.0, 0.10, 0.02, 0.01
)
spike_size = st.sidebar.number_input(
    "Spike Size (Extra Units)", min_value=0.0, value=200.0, step=25.0
)

st.sidebar.header("2. Vendor Freight & Lead Time")
lead_min = st.sidebar.number_input("Minimum Transit Days", min_value=1, value=18)
lead_max = st.sidebar.number_input("Maximum Transit Days", min_value=int(lead_min), value=22)

# Build uniform discrete lead-time distribution
lead_days = list(range(int(lead_min), int(lead_max) + 1))
n_days = len(lead_days)
lead_probs = [1.0 / n_days] * n_days
lead_mean = float(np.mean(lead_days))
lead_sd = float(np.std(lead_days))

st.sidebar.header("3. Service Level & Order Rules")
csl_target = st.sidebar.slider(
    "Target Cycle Service Level (CSL)", 0.80, 0.99, 0.95, 0.01
)
order_qty = st.sidebar.number_input(
    "Replenishment Order Quantity (Q)", min_value=50.0, value=500.0, step=50.0
)

st.sidebar.header("4. Trade Desk Constraints")
unit_cost = st.sidebar.number_input(
    "Unit Cost ($)", min_value=1.0, value=20.0, step=1.0
)
pack_size = st.sidebar.number_input(
    "Pallet / Carton Pack Size (Units)", min_value=1, value=48, step=1
)

# -----------------------------------------------------------------------------
# Core Computations
# -----------------------------------------------------------------------------
# Compute demand moments (accounting for spikes)
eff_mean, eff_sd = daily_demand_moments(base_mean, base_sd, spike_prob, spike_size)
expected_lead_demand = eff_mean * lead_mean

# 1. Static Reorder Point (Ignores lead-time volatility)
rop_static = static_reorder_point(eff_mean, eff_sd, lead_mean, csl_target)

# 2. Closed-Form Reorder Point (Accounts for lead-time variance)
rop_closed = closed_form_reorder_point(
    eff_mean, eff_sd, lead_mean, lead_sd, csl_target
)

# 3. Simulated Reorder Point (Full empirical quantile with spikes)
CYCLES = 100_000
rop_sim = simulated_reorder_point(
    base_mean,
    base_sd,
    lead_days,
    lead_probs,
    csl_target,
    cycles=CYCLES,
    seed=42,
    spike_prob=spike_prob,
    spike_size=spike_size,
)

# Simulate actual performance of each policy
sim_results_static = simulate_cycles(
    base_mean,
    base_sd,
    lead_days,
    lead_probs,
    rop_static,
    order_qty,
    cycles=CYCLES,
    seed=42,
    spike_prob=spike_prob,
    spike_size=spike_size,
)

sim_results_closed = simulate_cycles(
    base_mean,
    base_sd,
    lead_days,
    lead_probs,
    rop_closed,
    order_qty,
    cycles=CYCLES,
    seed=42,
    spike_prob=spike_prob,
    spike_size=spike_size,
)

sim_results_sim = simulate_cycles(
    base_mean,
    base_sd,
    lead_days,
    lead_probs,
    rop_sim,
    order_qty,
    cycles=CYCLES,
    seed=42,
    spike_prob=spike_prob,
    spike_size=spike_size,
)

# -----------------------------------------------------------------------------
# Main Dashboard Display: Metric Cards
# -----------------------------------------------------------------------------
st.subheader("Policy Comparison & Commercial Impact")

col1, col2, col3 = st.columns(3)


def format_policy_card(col, title, rop, sim_result, status_badge):
    with col:
        st.markdown(f"### {title} {status_badge}")
        st.metric(label="Calculated ROP", value=f"{int(round(rop)):,} units")

        # Snap to pallet / master pack
        snapped_rop = math.ceil(rop / pack_size) * pack_size
        st.write(
            f"📦 **Snapped to Pack Size ({pack_size}u):** `{snapped_rop:,}` units"
        )

        # Delivered Service Levels
        delivered_csl = sim_result.cycle_service_level * 100
        delivered_fill = sim_result.fill_rate * 100
        st.write(
            f"🎯 **Delivered CSL:** `{delivered_csl:.1f}%` (Target: {csl_target*100:.0f}%)"
        )
        st.write(f"🚚 **Delivered Fill Rate:** `{delivered_fill:.1f}%`")

        # Financial Impact
        safety_stock = max(0.0, rop - expected_lead_demand)
        working_cap = safety_stock * unit_cost
        st.write(f"💰 **Safety Stock Working Capital:** `${working_cap:,.2f}`")


format_policy_card(
    col1, "Static Formula", rop_static, sim_results_static, "⚠️ Shortcut"
)
format_policy_card(
    col2, "Closed-Form", rop_closed, sim_results_closed, "📐 Textbook"
)
format_policy_card(
    col3, "Simulated Quantile", rop_sim, sim_results_sim, "🎯 Optimal"
)

# Callout banner explaining the gap
static_drop = (csl_target - sim_results_static.cycle_service_level) * 100
if static_drop > 2.0:
    st.error(
        f"🚨 **The Hidden Risk:** The Static Formula under-delivers by **{static_drop:.1f} percentage points** because it assumes the vendor always delivers in exactly {lead_mean:.1f} days. Overlooking carrier transit volatility leads directly to floor stockouts."
    )

# -----------------------------------------------------------------------------
# Lead-Time Demand Distribution Chart
# -----------------------------------------------------------------------------
st.subheader("Simulated Lead-Time Demand vs. Reorder Cutoffs")

# Generate simulated lead-time demand samples for the histogram
sim_demand_samples = simulate_lead_time_demand(
    base_mean,
    base_sd,
    lead_days,
    lead_probs,
    cycles=20_000,
    seed=42,
    spike_prob=spike_prob,
    spike_size=spike_size,
)

fig = go.Figure()

# Histogram of demand
fig.add_trace(
    go.Histogram(
        x=sim_demand_samples,
        nbinsx=60,
        name="Lead-Time Demand Distribution",
        marker_color="#94a3b8",
        opacity=0.75,
    )
)

# Add vertical cutoff lines for the 3 ROPs
fig.add_vline(
    x=rop_static,
    line_dash="dash",
    line_color="#ef4444",
    annotation_text="Static ROP (Under-protects)",
    annotation_position="top left",
)
fig.add_vline(
    x=rop_closed,
    line_dash="dash",
    line_color="#f59e0b",
    annotation_text="Closed-Form ROP",
    annotation_position="top right",
)
fig.add_vline(
    x=rop_sim,
    line_dash="solid",
    line_color="#10b981",
    annotation_text="Simulated ROP (Full Protection)",
    annotation_position="bottom right",
)

fig.update_layout(
    xaxis_title="Total Units Demanded During Vendor Transit Time",
    yaxis_title="Frequency of Simulated Cycles",
    template="plotly_white",
    height=480,
    margin=dict(l=20, r=20, t=30, b=20),
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# Technical Assumptions Drawer
# -----------------------------------------------------------------------------
with st.expander("ℹ️ System Assumptions & Model Constraints"):
    st.markdown(
        f"""
    * **Demand Model:** Daily sales modeled as normal ($\mu={base_mean}, \sigma={base_sd}$) floored at 0, with a {spike_prob*100:.0f}% chance of a {spike_size:.0f}-unit contractor bulk order.
    * **Transit Model:** Vendor freight uniformly distributed across {lead_min}–{lead_max} days ($\mu={lead_mean:.1f}, \sigma={lead_sd:.2f}$).
    * **Fill Rate Assumption:** Lost sales model (unmet demand during stockout is forfeited, not backordered).
    * **Pallet Snapping:** Orders automatically round up to multiples of {pack_size} units to meet vendor pallet/carton packaging requirements.
    """
    )