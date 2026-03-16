import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
from geopulse.db.db import get_connection
from geopulse.analysis.price_predictor import predict_all_routes
from geopulse.flights.fuel import get_fuel_price_history, get_latest_fuel_price

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/geopulse.db")

st.set_page_config(
    page_title="GeoPulse Flight",
    page_icon="✈",
    layout="wide"
)

RISK_COLOURS = {
    "CRITICAL": "#E24B4A",
    "HIGH":     "#EF9F27",
    "MEDIUM":   "#378ADD",
    "LOW":      "#1D9E75",
}

ZONE_LABELS = {
    "russian_airspace":      "Russian airspace",
    "ukrainian_airspace":    "Ukrainian airspace",
    "iranian_airspace":      "Iranian airspace",
    "iraqi_syrian_airspace": "Iraqi/Syrian airspace",
    "red_sea_corridor":      "Red Sea corridor",
}

@st.cache_data(ttl=300)
def load_predictions():
    return predict_all_routes(DB_PATH)

@st.cache_data(ttl=300)
def load_deviations():
    conn = get_connection(DB_PATH)
    df = pd.read_sql_query("""
        SELECT callsign, zones, altitude_m, velocity_ms, detected_at
        FROM route_deviations
        WHERE detected_at >= datetime('now', '-2 hours')
        ORDER BY detected_at DESC
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_articles():
    conn = get_connection(DB_PATH)
    df = pd.read_sql_query("""
        SELECT title, section, sentiment_score, sentiment_label,
               geo_tags, published_at, url
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND published_at >= datetime('now', '-7 days')
        ORDER BY published_at DESC
        LIMIT 200
    """, conn)
    conn.close()
    return df

@st.cache_data(ttl=300)
def load_sentiment_trend():
    conn = get_connection(DB_PATH)
    df = pd.read_sql_query("""
        SELECT date(published_at) as date,
               AVG(sentiment_score) as avg_sentiment,
               COUNT(*) as article_count
        FROM articles
        WHERE sentiment_score IS NOT NULL
        AND published_at >= datetime('now', '-30 days')
        GROUP BY date(published_at)
        ORDER BY date ASC
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=300)
def load_deviation_trend():
    conn = get_connection(DB_PATH)
    df = pd.read_sql_query("""
        SELECT date(detected_at) as date,
               zones,
               COUNT(*) as count
        FROM route_deviations
        GROUP BY date(detected_at), zones
        ORDER BY date ASC
    """, conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=300)
def load_fuel_history():
    return get_fuel_price_history(DB_PATH)

# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("GeoPulse Flight")
st.sidebar.caption("Geopolitical flight intelligence")
page = st.sidebar.radio(
    "Navigate",
    ["Live overview", "Route forecasts", "Flight deviations", "News feed", "Backtester"]
)
st.sidebar.divider()

fuel_price = get_latest_fuel_price(DB_PATH)
st.sidebar.metric("Jet fuel ($/gal)", f"${fuel_price:.3f}")

predictions = load_predictions()
high_risk = [p for p in predictions if p["risk_level"] in ("HIGH", "CRITICAL")]
if high_risk:
    st.sidebar.error(f"⚠ {len(high_risk)} routes at HIGH+ risk")
else:
    st.sidebar.success("All routes MEDIUM or below")

st.sidebar.divider()
st.sidebar.caption("Data refreshes every 5 minutes")
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()

# ── Page 1: Live overview ─────────────────────────────────────────────────────

if page == "Live overview":
    st.title("Live geopolitical flight overview")

    deviations = load_deviations()
    sentiment_trend = load_sentiment_trend()
    fuel_df = load_fuel_history()

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active violations", len(deviations),
                  help="Flights over restricted zones in last 2 hours")
    with col2:
        avg_sent = sentiment_trend["avg_sentiment"].iloc[-1] if not sentiment_trend.empty else 0
        st.metric("Today's sentiment", f"{avg_sent:.3f}",
                  delta=f"{avg_sent - sentiment_trend['avg_sentiment'].iloc[-2]:.3f}"
                  if len(sentiment_trend) > 1 else None)
    with col3:
        st.metric("Jet fuel price", f"${fuel_price:.3f}/gal")
    with col4:
        st.metric("Routes at HIGH+ risk", len(high_risk))

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Sentiment trend (30 days)")
        if not sentiment_trend.empty:
            fig = px.line(
                sentiment_trend, x="date", y="avg_sentiment",
                labels={"avg_sentiment": "Avg sentiment", "date": ""},
                color_discrete_sequence=["#378ADD"]
            )
            fig.add_hline(y=0, line_dash="dash",
                          line_color="gray", opacity=0.5)
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=280
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sentiment data yet")

    with col_right:
        st.subheader("Jet fuel price history")
        if not fuel_df.empty:
            fig = px.line(
                fuel_df, x="week_date", y="price_usd_per_gallon",
                labels={"price_usd_per_gallon": "USD/gallon", "week_date": ""},
                color_discrete_sequence=["#EF9F27"]
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=280
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No fuel data yet — run pipeline first")

    st.divider()
    st.subheader("Violations by zone (last 2 hours)")
    if not deviations.empty:
        zone_counts = deviations["zones"].value_counts().reset_index()
        zone_counts.columns = ["zone", "count"]
        zone_counts["zone"] = zone_counts["zone"].map(
            lambda z: ZONE_LABELS.get(z.strip(), z)
        )
        fig = px.bar(
            zone_counts, x="count", y="zone",
            orientation="h",
            color_discrete_sequence=["#E24B4A"],
            labels={"count": "Flights detected", "zone": ""}
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=280)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No violations detected in last 2 hours")

# ── Page 2: Route forecasts ───────────────────────────────────────────────────

elif page == "Route forecasts":
    st.title("Route price forecasts")
    st.caption(
        f"Based on current sentiment, {len(load_deviations())} live violations "
        f"and jet fuel at ${fuel_price:.3f}/gal"
    )

    for p in predictions:
        risk  = p["risk_level"]
        color = RISK_COLOURS.get(risk, "#888")

        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"### {p['label']}")
                if p.get("triggered_zones"):
                    zones_str = ", ".join(
                        ZONE_LABELS.get(z, z) for z in p["triggered_zones"]
                    )
                    st.caption(f"Affected by: {zones_str}")
                else:
                    st.caption("No active zone triggers on this route")
            with col2:
                st.metric(
                    "Estimated price",
                    f"£{p['estimated_price_gbp']:,.0f}",
                    delta=f"+{p['pct_above_base']}% vs baseline",
                    delta_color="inverse"
                )
            with col3:
                st.markdown(
                    f"<div style='background:{color};color:white;"
                    f"padding:8px 16px;border-radius:8px;"
                    f"text-align:center;font-weight:500'>{risk}</div>",
                    unsafe_allow_html=True
                )

    st.divider()
    st.subheader("Price multiplier breakdown")

    mult_data = []
    for p in predictions:
        mult_data.append({
            "Route":     p["label"],
            "Zone":      p["zone_multiplier"],
            "Sentiment": p["sentiment_mult"],
            "Deviation": p["deviation_mult"],
            "Days out":  p["days_mult"],
        })

    df_mult = pd.DataFrame(mult_data)
    fig = go.Figure()
    for col in ["Zone", "Sentiment", "Deviation", "Days out"]:
        fig.add_trace(go.Bar(name=col, x=df_mult["Route"], y=df_mult[col]))
    fig.update_layout(
        barmode="group",
        height=350,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Page 3: Flight deviations ────────────────────────────────────────────────

elif page == "Flight deviations":
    st.title("Live flight deviations")

    deviations = load_deviations()
    deviation_trend = load_deviation_trend()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Violations (last 2h)", len(deviations))
    with col2:
        conn = get_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM route_deviations")
        total = cursor.fetchone()["total"]
        conn.close()
        st.metric("Total recorded", total)

    st.divider()
    st.subheader("Deviation trend by zone")

    if not deviation_trend.empty:
        main_zones = ["russian_airspace", "ukrainian_airspace",
                      "red_sea_corridor", "iranian_airspace"]
        trend_filtered = deviation_trend[
            deviation_trend["zones"].isin(main_zones)
        ].copy()
        trend_filtered["zones"] = trend_filtered["zones"].map(
            lambda z: ZONE_LABELS.get(z, z)
        )
        fig = px.line(
            trend_filtered, x="date", y="count",
            color="zones",
            labels={"count": "Flights detected", "date": "", "zones": "Zone"},
            height=320
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Recent violations")

    if not deviations.empty:
        deviations["zones"] = deviations["zones"].map(
            lambda z: ZONE_LABELS.get(z.strip(), z)
        )
        deviations["altitude_km"] = (
            deviations["altitude_m"] / 1000
        ).round(1)
        deviations["speed_kmh"] = (
            deviations["velocity_ms"] * 3.6
        ).round(0)
        st.dataframe(
            deviations[["callsign", "zones", "altitude_km",
                         "speed_kmh", "detected_at"]].rename(columns={
                "callsign":    "Flight",
                "zones":       "Zone",
                "altitude_km": "Alt (km)",
                "speed_kmh":   "Speed (km/h)",
                "detected_at": "Detected at"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No violations in the last 2 hours")

# ── Page 4: News feed ────────────────────────────────────────────────────────

elif page == "News feed":
    st.title("Geopolitical news feed")

    articles = load_articles()

    if articles.empty:
        st.info("No recent articles — run the pipeline first")
    else:
        col1, col2 = st.columns(2)
        with col1:
            sentiment_filter = st.selectbox(
                "Filter by sentiment",
                ["All", "Negative", "Neutral", "Positive"]
            )
        with col2:
            section_options = ["All"] + sorted(articles["section"].dropna().unique().tolist())
            section_filter = st.selectbox("Filter by section", section_options)

        filtered = articles.copy()
        if sentiment_filter != "All":
            filtered = filtered[
                filtered["sentiment_label"] == sentiment_filter.lower()
            ]
        if section_filter != "All":
            filtered = filtered[filtered["section"] == section_filter]

        st.caption(f"Showing {len(filtered)} articles")
        st.divider()

        for _, row in filtered.head(50).iterrows():
            score = row["sentiment_score"]
            label = row["sentiment_label"]
            if label == "negative":
                badge_color = "#E24B4A"
            elif label == "positive":
                badge_color = "#1D9E75"
            else:
                badge_color = "#888780"

            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{row['title']}**")
                    if row.get("first_paragraph"):
                        st.caption(str(row["first_paragraph"])[:200] + "...")
                    st.caption(
                        f"{row['section']} · {str(row['published_at'])[:10]}"
                    )
                with col2:
                    st.markdown(
                        f"<div style='background:{badge_color};color:white;"
                        f"padding:4px 10px;border-radius:6px;"
                        f"text-align:center;font-size:12px'>"
                        f"{score:.2f}</div>",
                        unsafe_allow_html=True
                    )
# ── Page 5: Backtester ───────────────────────────────────────────────────────

elif page == "Backtester":
    st.title("Geopolitical event backtester")
    st.caption(
        "Automatically detects sentiment spikes from scraped news "
        "and shows predicted price impact on affected routes."
    )

    with st.spinner("Running backtest on scraped data..."):
        from geopulse.analysis.backtester import run_backtest, summarise_backtest
        summary = summarise_backtest(DB_PATH)
        df      = run_backtest(DB_PATH)

    if summary.get("status") == "insufficient_data":
        st.warning("Not enough data yet — run the pipeline for a few more days.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Events detected", summary["total_events"])
        with col2:
            st.metric("Avg price uplift", f"+{summary['avg_uplift_pct']}%")
        with col3:
            st.metric("Max uplift", f"+{summary['max_uplift_pct']}%")
        with col4:
            st.metric("Most affected route", summary["max_uplift_route"].replace("London → ", "LHR→"))

        st.divider()

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Uplift by zone")
            if not df.empty:
                zone_summary = df.groupby("zone").agg(
                    avg_uplift=("uplift_pct", "mean"),
                    events=("date", "count")
                ).reset_index()
                zone_summary["zone"] = zone_summary["zone"].map(
                    lambda z: ZONE_LABELS.get(z, z)
                )
                zone_summary = zone_summary.sort_values("avg_uplift", ascending=True)
                fig = px.bar(
                    zone_summary,
                    x="avg_uplift", y="zone",
                    orientation="h",
                    color_discrete_sequence=["#EF9F27"],
                    labels={"avg_uplift": "Avg price uplift (%)", "zone": ""}
                )
                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=280)
                st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("Uplift over time")
            if not df.empty:
                time_df = df.groupby("date").agg(
                    avg_uplift=("uplift_pct", "mean")
                ).reset_index()
                time_df["date"] = pd.to_datetime(time_df["date"])
                fig = px.line(
                    time_df, x="date", y="avg_uplift",
                    color_discrete_sequence=["#E24B4A"],
                    labels={"avg_uplift": "Avg uplift (%)", "date": ""}
                )
                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=280)
                st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("Detected events and price impact")

        if not df.empty:
            for _, row in df.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        st.markdown(f"**{row['date']} — {ZONE_LABELS.get(row['zone'], row['zone'])}**")
                        st.caption(row["top_headlines"][:120] + "...")
                        st.caption(
                            f"Sentiment: {row['avg_sentiment']:.3f} · "
                            f"Spike: {row['spike_magnitude']}x above average · "
                            f"{row['negative_articles']} negative articles"
                        )
                    with col2:
                        st.markdown(f"**{row['route']}**")
                        st.caption(
                            f"Baseline: £{row['baseline_price']:,.0f} → "
                            f"Event: £{row['event_price']:,.0f} "
                            f"(+£{row['price_uplift_gbp']:,.0f})"
                        )
                    with col3:
                        color = RISK_COLOURS.get(row["risk_level"], "#888")
                        st.markdown(
                            f"<div style='background:{color};color:white;"
                            f"padding:6px 12px;border-radius:8px;"
                            f"text-align:center;font-weight:500'>"
                            f"+{row['uplift_pct']}%</div>",
                            unsafe_allow_html=True
                        )