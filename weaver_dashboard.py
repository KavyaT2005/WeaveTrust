import streamlit as st
import pandas as pd
import os
from datetime import datetime
import matplotlib.pyplot as plt

FILE_NAME = "weaver_orders.xlsx"

st.set_page_config(page_title="Weaver Dashboard", layout="wide")
st.title("🧵 Weaver Production Dashboard")

# -----------------------------
# Load or create Excel
# -----------------------------
if os.path.exists(FILE_NAME):
    df = pd.read_excel(FILE_NAME)
else:
    df = pd.DataFrame(columns=["Date", "Weaver", "Order_ID", "Status"])
    df.to_excel(FILE_NAME, index=False)

# -----------------------------
# Add New Order
# -----------------------------
st.subheader("➕ Add New Order")

col1, col2 = st.columns(2)

with col1:
    weaver = st.text_input("Weaver Name")

with col2:
    order_id = st.text_input("Order ID")

if st.button("Add Order"):
    if weaver and order_id:
        new_row = {
            "Date": datetime.now().date(),
            "Weaver": weaver,
            "Order_ID": order_id,
            "Status": "Pending"
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(FILE_NAME, index=False)
        st.success("Order Added ✅")

# -----------------------------
# Mark Order Completed
# -----------------------------
st.subheader("✅ Complete Order")

pending_orders = df[df["Status"] == "Pending"]["Order_ID"].tolist()

if pending_orders:
    selected_order = st.selectbox("Select Order", pending_orders)

    if st.button("Mark Completed"):
        df.loc[df["Order_ID"] == selected_order, "Status"] = "Completed"
        df.to_excel(FILE_NAME, index=False)
        st.success("Order Completed & Excel Updated 📊")
else:
    st.info("No Pending Orders")

# -----------------------------
# Show Data
# -----------------------------
st.subheader("📋 All Orders")
st.dataframe(df, use_container_width=True)

# -----------------------------
# DAILY PRODUCTION ANALYTICS
# -----------------------------
st.subheader("📈 Daily Production Analytics")

completed_df = df[df["Status"] == "Completed"]

if not completed_df.empty:
    completed_df["Date"] = pd.to_datetime(completed_df["Date"])

    daily_counts = (
        completed_df.groupby("Date")
        .size()
        .reset_index(name="Production_Count")
        .sort_values("Date")
    )

    # Chart
    fig, ax = plt.subplots()
    ax.plot(daily_counts["Date"], daily_counts["Production_Count"], marker="o")
    ax.set_title("Daily Production Trend")
    ax.set_xlabel("Date")
    ax.set_ylabel("Orders Completed")

    st.pyplot(fig)

    # Trend logic
    if len(daily_counts) >= 2:
        today = daily_counts.iloc[-1]["Production_Count"]
        yesterday = daily_counts.iloc[-2]["Production_Count"]

        if today > yesterday:
            st.success("📈 Production is UP — Give more orders 🚀")
        elif today < yesterday:
            st.warning("📉 Production is DOWN — Monitor weaver ⚠️")
        else:
            st.info("➡️ Production Stable")

else:
    st.info("No completed orders yet")

# -----------------------------
# WEAVER PERFORMANCE
# -----------------------------
st.subheader("🏆 Weaver Performance")

if not completed_df.empty:
    weaver_perf = (
        completed_df.groupby("Weaver")
        .size()
        .reset_index(name="Completed_Orders")
        .sort_values("Completed_Orders", ascending=False)
    )

    st.dataframe(weaver_perf, use_container_width=True)

    top_weaver = weaver_perf.iloc[0]["Weaver"]
    st.success(f"🔥 Best Performer: {top_weaver} — Give more orders!")

else:
    st.info("No performance data yet")
