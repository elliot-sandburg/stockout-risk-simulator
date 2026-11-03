"""
Stockout Risk Simulator & Working Capital Engine (v2)
- Tab 1: Single-SKU Monte Carlo Simulator & Distribution Chart
- Tab 2: Department Catalog & Automated Vendor Purchase Order Generator
"""

from datetime import datetime
import math
import sqlite3
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
    page_title="Stockout Risk & Working Capital Simulator (v2)",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Stockout Risk & Working Capital Simulator (v2)")
st.markdown(
    "Enterprise replenishment policy engine combining **Monte Carlo simulation**, **working-capital optimization**, and **automated purchase order generation**."
)

tab1, tab2 = st.tabs(
    [
        "🔬 Single-SKU Deep Dive Simulator",
        "📋 Department Catalog & PO Generator",
    ]
)

# =============================================================================
# TAB 1: Single-SKU Deep Dive Simulator (v1 Foundation)
# =============================================================================
with tab1:
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
    lead_min = st.sidebar.number_input(
        "Minimum Transit Days", min_value=1, value=18
    )
    lead_max = st.sidebar.number_input(
        "Maximum Transit Days", min_value=int(lead_min), value=22
    )

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

    # Computations
    eff_mean, eff_sd = daily_demand_moments(
        base_mean, base_sd, spike_prob, spike_size
    )
    expected_lead_demand = eff_mean * lead_mean

    rop_static = static_reorder_point(eff_mean, eff_sd, lead_mean, csl_target)
    rop_closed = closed_form_reorder_point(
        eff_mean, eff_sd, lead_mean, lead_sd, csl_target
    )

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

    # KPI Row
    st.subheader("Policy Comparison & Commercial Impact")
    col1, col2, col3 = st.columns(3)

    def format_card(col, title, rop, sim_result, badge):
        with col:
            st.markdown(f"### {title} {badge}")
            st.metric(label="Calculated ROP", value=f"{int(round(rop)):,} units")
            snapped = math.ceil(rop / pack_size) * pack_size
            st.write(f"📦 **Snapped to Pack ({pack_size}u):** `{snapped:,}` units")
            st.write(
                f"🎯 **Delivered CSL:** `{sim_result.cycle_service_level*100:.1f}%`"
            )
            st.write(
                f"🚚 **Delivered Fill Rate:** `{sim_result.fill_rate*100:.1f}%`"
            )
            safety = max(0.0, rop - expected_lead_demand)
            st.write(
                f"💰 **Safety Stock Capital:** `${safety * unit_cost:,.2f}`"
            )

    format_card(
        col1, "Static Formula", rop_static, sim_results_static, "⚠️ Shortcut"
    )
    format_card(
        col2, "Closed-Form", rop_closed, sim_results_closed, "📐 Textbook"
    )
    format_card(
        col3, "Simulated Quantile", rop_sim, sim_results_sim, "🎯 Optimal"
    )

    static_drop = (csl_target - sim_results_static.cycle_service_level) * 100
    if static_drop > 2.0:
        st.error(
            f"🚨 **The Hidden Risk:** The Static Formula under-delivers by **{static_drop:.1f} percentage points** because it assumes fixed transit times."
        )

    # Plotly Chart
    st.subheader("Simulated Lead-Time Demand Distribution")
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
    fig.add_trace(
        go.Histogram(
            x=sim_demand_samples,
            nbinsx=60,
            marker_color="#94a3b8",
            opacity=0.75,
            name="Simulated Demand",
        )
    )
    fig.add_vline(
        x=rop_static,
        line_dash="dash",
        line_color="#ef4444",
        annotation_text="Static",
    )
    fig.add_vline(
        x=rop_closed,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text="Closed-Form",
    )
    fig.add_vline(
        x=rop_sim,
        line_dash="solid",
        line_color="#10b981",
        annotation_text="Simulated",
    )
    fig.update_layout(
        xaxis_title="Units Demanded During Lead Time",
        yaxis_title="Frequency",
        template="plotly_white",
        height=450,
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB 2: Multi-SKU Department Catalog & Automated PO Generator (v2)
# =============================================================================
with tab2:
    st.subheader("📋 Department Inventory Catalog & Replenishment Monitor")
    st.markdown(
        "Live view of trade-desk SKUs loaded from `inventory.db`. Computes dynamic Reorder Points, evaluates stockout risks, and generates consolidated vendor Purchase Orders."
    )

    # Connect to SQLite
    try:
        conn = sqlite3.connect("inventory.db")
        catalog_df = pd.read_sql_query(
            "SELECT * FROM inventory_catalog", conn
        )
        conn.close()
    except Exception as e:
        st.error(
            f"Could not load database. Make sure you ran `python init_db.py`. Error: {e}"
        )
        st.stop()

    # Calculate policy for each SKU in the database
    analysis_records = []
    po_line_items = []

    for _, row in catalog_df.iterrows():
        # Compute Closed-Form ROP using its specific lead-time and demand variance
        rop = closed_form_reorder_point(
            row["daily_mean"],
            row["daily_sd"],
            row["lead_mean"],
            row["lead_sd"],
            csl_target,
        )
        rop_int = int(round(rop))

        # Expected lead demand and safety stock
        exp_lead_demand = row["daily_mean"] * row["lead_mean"]
        safety_stock = max(0.0, rop - exp_lead_demand)
        safety_cap = safety_stock * row["unit_cost"]

        # Stock Status Logic
        on_hand = row["on_hand"]
        if on_hand <= rop_int:
            status = "🚨 Reorder Now"
            # Snapping to full vendor pallet / pack
            deficit = (exp_lead_demand * 1.5) + safety_stock - on_hand
            units_to_order = (
                math.ceil(max(deficit, row["pack_size"]) / row["pack_size"])
                * row["pack_size"]
            )
            packs = int(units_to_order / row["pack_size"])
            line_cost = units_to_order * row["unit_cost"]

            po_line_items.append(
                {
                    "Vendor": row["vendor"],
                    "SKU": row["sku"],
                    "Description": row["description"],
                    "Units_Ordered": units_to_order,
                    "Packs_Ordered": packs,
                    "Pack_Size": row["pack_size"],
                    "Unit_Cost": f"${row['unit_cost']:.2f}",
                    "Total_Cost": f"${line_cost:,.2f}",
                    "Raw_Cost": line_cost,
                }
            )
        elif on_hand <= rop_int * 1.2:
            status = "⚠️ Warning (Low)"
            units_to_order = 0
        else:
            status = "🟢 Healthy"
            units_to_order = 0

        analysis_records.append(
            {
                "Status": status,
                "SKU": row["sku"],
                "Description": row["description"],
                "Vendor": row["vendor"],
                "On-Hand": on_hand,
                "ROP Target": rop_int,
                "Daily Sales (Avg)": row["daily_mean"],
                "Lead Time (Avg)": f"{row['lead_mean']:.0f}d",
                "Pack Size": row["pack_size"],
                "Safety Stock ($)": f"${safety_cap:,.2f}",
            }
        )

    summary_df = pd.DataFrame(analysis_records)

    # Department KPI Top Row
    reorder_count = sum(1 for r in analysis_records if "Reorder" in r["Status"])
    total_po_spend = sum(item["Raw_Cost"] for item in po_line_items)

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Catalog SKUs Monitored", len(catalog_df))
    kpi2.metric(
        "Critical Reorder Alerts",
        f"{reorder_count} SKUs",
        delta=f"-{reorder_count} holds" if reorder_count > 0 else "Optimal",
        delta_color="inverse",
    )
    kpi3.metric("Recommended PO Spend", f"${total_po_spend:,.2f}")

    # Display Catalog Table
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # PO Generator Section
    st.markdown("---")
    st.subheader("📦 Automated Vendor Purchase Order Generator")

    if po_line_items:
        po_df = pd.DataFrame(po_line_items).drop(columns=["Raw_Cost"])
        st.write(
            "The following items have dropped to or below their Reorder Point. Quantities have been automatically snapped to vendor master-carton and pallet multiples:"
        )
        st.table(po_df)

        # Convert to downloadable CSV
        csv_data = po_df.to_csv(index=False).encode("utf-8")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"Vendor_Replenishment_PO_{timestamp}.csv"

        st.download_button(
            label="📥 Download Approved Vendor PO (.csv)",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
        )
    else:
        st.success(
            "🟢 All SKUs are currently above their Reorder Points. No purchase orders required today!"
        )