import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import plotly.graph_objects as go

load_dotenv()

from db_utils import (
    load_articles, load_flight_states, load_deviations,
    load_flight_prices, load_sentiment_trend, load_deviation_trend,
    load_fuel_history, load_summary_metrics,
)
from map_visualizations import (
    build_global_map, build_deviation_heatmap,
    build_price_comparison_chart, build_fuel_trend_chart,
    build_sentiment_trend_chart, ZONE_LABELS, RISK_COLORS,
)
from news_fetcher import fetch_live_news, render_news_card, GEOPOLITICAL_TOPICS
from analytics import (
    correlate_news_with_routes, build_price_distribution,
    build_price_by_route, build_deviation_timeline,
    build_sentiment_by_zone,
)

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GeoPulse Flight Intelligence",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme CSS ────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap');

    html, body, [class*="css"] {
        background-color: #0d1117;
        color: #e6edf3;
        font-family: 'Syne', sans-serif;
    }
    .stApp { background-color: #0d1117; }
    .stSidebar { background-color: #161b2e !important; }
    .stSidebar [data-testid="stSidebarNav"] { background-color: #161b2e; }

    h1, h2, h3 { font-family: 'Syne', sans-serif; font-weight: 700; }
    h1 { font-size: 2rem; letter-spacing: -0.5px; }

    .metric-card {
        background: #161b2e;
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        color: #58a6ff;
    }
    .metric-label {
        font-size: 0.75rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 4px;
    }
    .risk-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
    }
    .alert-banner {
        background: rgba(226,75,74,0.1);
        border: 1px solid #E24B4A;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
    }
    div[data-testid="stMetric"] {
        background: #161b2e;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 16px;
    }
    div[data-testid="stMetric"] label { color: #8b949e !important; font-size: 0.75rem; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #58a6ff !important;
        font-family: 'JetBrains Mono', monospace;
    }
    div[data-testid="stContainer"] {
        background: #161b2e;
        border-color: #2d3748 !important;
    }
    .stDataFrame { background: #161b2e; }
    .stSelectbox > div, .stMultiSelect > div {
        background: #161b2e;
        border-color: #2d3748;
    }
    .section-header {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #58a6ff;
        margin-bottom: 8px;
    }
    .geopulse-logo {
        font-family: 'Syne', sans-serif;
        font-weight: 800;
        font-size: 1.4rem;
        color: #58a6ff;
        letter-spacing: -0.5px;
    }
    .geopulse-sub {
        font-size: 0.7rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="geopulse-logo">GeoPulse</div>', unsafe_allow_html=True)
    st.markdown('<div class="geopulse-sub">Flight Intelligence</div>', unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "Navigate",
        [
            "🌍 Overview",
            "✈ Global flight map",
            "⚠ Detour analysis",
            "💷 Price analysis",
            "📰 Geopolitical news",
            "🔗 News + flight correlation",
            "📊 Data insights",
            "🔬 Validation",
        ],
        label_visibility="collapsed"
    )

    st.divider()

    metrics = load_summary_metrics()
    st.markdown('<div class="section-header">Live signals</div>', unsafe_allow_html=True)
    st.metric("Fuel price", f"${metrics['latest_fuel_price']}/gal")
    st.metric("7-day sentiment", f"{metrics['avg_sentiment_7d']}")
    st.metric("Total violations", f"{metrics['total_deviations']:,}")

    st.divider()
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Load shared data ──────────────────────────────────────────────────────────

articles_df      = load_articles()
flight_states_df = load_flight_states()
deviations_df    = load_deviations()
prices_df        = load_flight_prices()
sentiment_trend  = load_sentiment_trend()
deviation_trend  = load_deviation_trend()
fuel_df          = load_fuel_history()

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from geopulse.analysis.price_predictor import predict_all_routes
    predictions = predict_all_routes(os.getenv("DB_PATH", "data/geopulse.db"))
except Exception:
    predictions = []

# ── Page: Overview ────────────────────────────────────────────────────────────

if page == "🌍 Overview":
    st.markdown("# 🌍 GeoPulse Flight Intelligence")
    st.caption("Real-time geopolitical risk analysis for global flight routes")

    high_risk = [p for p in predictions if p.get("risk_level") in ("HIGH", "CRITICAL")]
    if high_risk:
        routes_str = ", ".join(p["label"] for p in high_risk[:3])
        st.markdown(
            f'<div class="alert-banner">⚠ <strong>{len(high_risk)} routes at elevated risk</strong> — {routes_str}</div>',
            unsafe_allow_html=True
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Articles ingested", f"{metrics['total_articles']:,}")
    with c2:
        st.metric("Flight states", f"{metrics['total_flight_states']:,}")
    with c3:
        st.metric("Zone violations", f"{metrics['total_deviations']:,}")
    with c4:
        st.metric("Jet fuel ($/gal)", f"${metrics['latest_fuel_price']}")
    with c5:
        st.metric("Routes at HIGH+", len(high_risk))

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Sentiment trend (90 days)")
        st.plotly_chart(build_sentiment_trend_chart(sentiment_trend),
                        use_container_width=True)

    with col2:
        st.markdown("#### Jet fuel price history")
        st.plotly_chart(build_fuel_trend_chart(fuel_df),
                        use_container_width=True)

    st.divider()
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("#### Violations by zone")
        st.plotly_chart(build_deviation_heatmap(deviations_df),
                        use_container_width=True)

    with col4:
        st.markdown("#### Sentiment by region")
        st.plotly_chart(build_sentiment_by_zone(articles_df),
                        use_container_width=True)

    if predictions:
        st.divider()
        st.markdown("#### Current route risk summary")
        cols = st.columns(len(predictions))
        for i, p in enumerate(predictions):
            with cols[i]:
                risk  = p.get("risk_level", "LOW")
                color = RISK_COLORS.get(risk, "#888")
                route = p["label"].replace("London → ", "→")
                st.markdown(
                    f'<div style="background:#161b2e;border:1px solid #2d3748;'
                    f'border-radius:10px;padding:14px;text-align:center">'
                    f'<div style="font-size:0.8rem;color:#8b949e">{route}</div>'
                    f'<div style="font-size:1.4rem;font-weight:700;'
                    f'font-family:JetBrains Mono;color:{color}">'
                    f'£{p["estimated_price_gbp"]:,.0f}</div>'
                    f'<div style="background:{color};color:white;'
                    f'border-radius:20px;padding:2px 10px;font-size:0.7rem;'
                    f'margin-top:6px;display:inline-block">{risk}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

# ── Page: Global flight map ───────────────────────────────────────────────────

elif page == "✈ Global flight map":
    st.markdown("# ✈ Global Flight Map")
    st.caption("Live airspace violations, monitored routes and no-fly zones")

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        show_nfz    = st.toggle("No-fly zones", value=True)
    with col_f2:
        show_routes = st.toggle("Route lines", value=True)
    with col_f3:
        show_viols  = st.toggle("Violations", value=True)
    with col_f4:
        show_live   = st.toggle("Live aircraft", value=True)

    with st.spinner("Rendering map..."):
        fig = build_global_map(
            predictions=predictions,
            deviations_df=deviations_df,
            flight_states_df=flight_states_df,
            show_no_fly_zones=show_nfz,
            show_routes=show_routes,
            show_violations=show_viols,
            show_live_flights=show_live,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Recent violations (last 2 hours)")
        recent_viols = deviations_df[
            deviations_df["detected_at"] >= pd.Timestamp.utcnow().strftime("%Y-%m-%d")
        ] if not deviations_df.empty else deviations_df
        if not recent_viols.empty:
            display = recent_viols[["callsign","zones","altitude_m","detected_at"]].head(15)
            display["zones"] = display["zones"].map(
                lambda z: ZONE_LABELS.get(z.strip(), z)
            )
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.info("No recent violations")

    with col2:
        st.markdown("#### Violation trend by zone")
        st.plotly_chart(build_deviation_timeline(deviation_trend),
                        use_container_width=True)

# ── Page: Detour analysis ─────────────────────────────────────────────────────

elif page == "⚠ Detour analysis":
    st.markdown("# ⚠ Detour Route Analysis")
    st.caption("How geopolitical no-fly zones are forcing airlines to reroute")

    DETOUR_IMPACT = {
        "LHR→DXB (via Iran avoidance)": {
            "original_km": 5500, "detour_km": 6100,
            "original_hrs": 7.0, "detour_hrs": 7.8,
            "extra_fuel_cost": 42, "zones": ["Iranian airspace", "Red Sea corridor"]
        },
        "LHR→DEL (via Russia avoidance)": {
            "original_km": 6700, "detour_km": 8200,
            "original_hrs": 8.5, "detour_hrs": 10.3,
            "extra_fuel_cost": 89, "zones": ["Russian airspace"]
        },
        "LHR→BKK (via Russia avoidance)": {
            "original_km": 9500, "detour_km": 11200,
            "original_hrs": 11.0, "detour_hrs": 13.0,
            "extra_fuel_cost": 127, "zones": ["Russian airspace"]
        },
        "LHR→HKG (via Russia avoidance)": {
            "original_km": 9600, "detour_km": 11800,
            "original_hrs": 12.0, "detour_hrs": 14.5,
            "extra_fuel_cost": 159, "zones": ["Russian airspace"]
        },
        "LHR→NRT (via Russia avoidance)": {
            "original_km": 9600, "detour_km": 12100,
            "original_hrs": 12.0, "detour_hrs": 15.0,
            "extra_fuel_cost": 191, "zones": ["Russian airspace"]
        },
    }

    import plotly.graph_objects as pgo

    selected_route = st.selectbox("Select route", list(DETOUR_IMPACT.keys()))
    impact = DETOUR_IMPACT[selected_route]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Original distance", f"{impact['original_km']:,} km")
    with c2:
        st.metric("Detour distance",
                  f"{impact['detour_km']:,} km",
                  delta=f"+{impact['detour_km']-impact['original_km']:,} km",
                  delta_color="inverse")
    with c3:
        st.metric("Extra flight time",
                  f"+{impact['detour_hrs']-impact['original_hrs']:.1f}h")
    with c4:
        st.metric("Est. extra fuel cost", f"+£{impact['extra_fuel_cost']}/passenger")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Distance comparison")
        fig_dist = go.Figure(go.Bar(
            x=["Original route", "Detour route"],
            y=[impact["original_km"], impact["detour_km"]],
            marker_color=["#1D9E75", "#E24B4A"],
            text=[f"{impact['original_km']:,} km", f"{impact['detour_km']:,} km"],
            textposition="auto",
        ))
        fig_dist.update_layout(
            paper_bgcolor="#0d1117", plot_bgcolor="#161b2e",
            font=dict(color="white"), margin=dict(l=0,r=0,t=10,b=0),
            height=280, yaxis=dict(gridcolor="#2d3748", title="Distance (km)"),
            xaxis=dict(gridcolor="#2d3748"),
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with col2:
        st.markdown("#### Flight time comparison")
        fig_time = go.Figure(go.Bar(
            x=["Original route", "Detour route"],
            y=[impact["original_hrs"], impact["detour_hrs"]],
            marker_color=["#1D9E75", "#EF9F27"],
            text=[f"{impact['original_hrs']}h", f"{impact['detour_hrs']}h"],
            textposition="auto",
        ))
        fig_time.update_layout(
            paper_bgcolor="#0d1117", plot_bgcolor="#161b2e",
            font=dict(color="white"), margin=dict(l=0,r=0,t=10,b=0),
            height=280, yaxis=dict(gridcolor="#2d3748", title="Hours"),
            xaxis=dict(gridcolor="#2d3748"),
        )
        st.plotly_chart(fig_time, use_container_width=True)

    st.divider()
    st.markdown("#### All route detour impact summary")
    rows = []
    for route, d in DETOUR_IMPACT.items():
        extra_km  = d["detour_km"] - d["original_km"]
        extra_hrs = round(d["detour_hrs"] - d["original_hrs"], 1)
        rows.append({
            "Route":            route,
            "Original (km)":    f"{d['original_km']:,}",
            "Detour (km)":      f"{d['detour_km']:,}",
            "Extra distance":   f"+{extra_km:,} km",
            "Extra time":       f"+{extra_hrs}h",
            "Extra fuel cost":  f"+£{d['extra_fuel_cost']}/pax",
            "Avoided zones":    ", ".join(d["zones"]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Price impact vs detour distance")
    import plotly.express as px
    scatter_df = pd.DataFrame([{
        "Route": r.split("(")[0].strip(),
        "Extra distance (km)": d["detour_km"] - d["original_km"],
        "Extra fuel cost (£/pax)": d["extra_fuel_cost"],
    } for r, d in DETOUR_IMPACT.items()])

    fig_scatter = px.scatter(
        scatter_df, x="Extra distance (km)", y="Extra fuel cost (£/pax)",
        text="Route", size="Extra fuel cost (£/pax)",
        color="Extra fuel cost (£/pax)",
        color_continuous_scale=["#1D9E75", "#EF9F27", "#E24B4A"],
    )
    fig_scatter.update_traces(textposition="top center")
    fig_scatter.update_layout(
        paper_bgcolor="#0d1117", plot_bgcolor="#161b2e",
        font=dict(color="white"), margin=dict(l=0,r=0,t=10,b=0),
        height=340, coloraxis_showscale=False,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748"),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# ── Page: Price analysis ──────────────────────────────────────────────────────

elif page == "💷 Price analysis":
    st.markdown("# 💷 Flight Price Analysis")

    if predictions:
        st.markdown("#### Model price estimates vs baseline")
        st.plotly_chart(build_price_comparison_chart(predictions),
                        use_container_width=True)

        st.divider()
        st.markdown("#### Route risk table")
        risk_rows = []
        for p in predictions:
            risk_rows.append({
                "Route":          p["label"],
                "Base fare":      f"£{p['base_fare_gbp']:,.0f}",
                "Est. price":     f"£{p['estimated_price_gbp']:,.0f}",
                "Above baseline": f"+{p['pct_above_base']}%",
                "Risk level":     p["risk_level"],
                "Active zones":   ", ".join(
                    ZONE_LABELS.get(z, z) for z in p.get("triggered_zones", [])
                ) or "None",
                "Fuel price":     f"${p.get('fuel_price', 0):.3f}/gal",
            })
        st.dataframe(pd.DataFrame(risk_rows),
                     use_container_width=True, hide_index=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Aviationstack price distribution")
        st.plotly_chart(build_price_distribution(prices_df),
                        use_container_width=True)
    with col2:
        st.markdown("#### Average price by route")
        st.plotly_chart(build_price_by_route(prices_df),
                        use_container_width=True)

    st.divider()
    st.markdown("#### Jet fuel price trend")
    st.plotly_chart(build_fuel_trend_chart(fuel_df), use_container_width=True)

# ── Page: Geopolitical news ───────────────────────────────────────────────────

elif page == "📰 Geopolitical news":
    st.markdown("# 📰 Geopolitical News")

    col1, col2, col3 = st.columns(3)
    with col1:
        topic = st.selectbox("Topic", ["geopolitics aviation"] + GEOPOLITICAL_TOPICS)
    with col2:
        days = st.slider("Days back", 1, 30, 7)
    with col3:
        n_results = st.slider("Results", 5, 50, 20)

    with st.spinner("Fetching live news from Guardian..."):
        live_articles = fetch_live_news(query=topic, days_back=days,
                                        page_size=n_results)

    if live_articles:
        st.caption(f"Showing {len(live_articles)} articles · Live from Guardian API")
        st.divider()
        for article in live_articles:
            sentiment_label = "neutral"
            badge_color = "#8b949e"
            title_lower = article.get("webTitle", "").lower()
            if any(w in title_lower for w in ["war","attack","strike","kill","bomb","crisis"]):
                badge_color = "#E24B4A"
                sentiment_label = "negative"
            elif any(w in title_lower for w in ["peace","deal","agreement","ceasefire"]):
                badge_color = "#1D9E75"
                sentiment_label = "positive"
            render_news_card(article, badge_color)
    else:
        st.warning("No live articles fetched — showing scraped articles from database")
        if not articles_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                sent_filter = st.selectbox(
                    "Sentiment", ["All", "Negative", "Neutral", "Positive"]
                )
            with col2:
                sections = ["All"] + sorted(articles_df["section"].dropna().unique().tolist())
                sec_filter = st.selectbox("Section", sections)

            filtered = articles_df.copy()
            if sent_filter != "All":
                filtered = filtered[filtered["sentiment_label"] == sent_filter.lower()]
            if sec_filter != "All":
                filtered = filtered[filtered["section"] == sec_filter]

            st.caption(f"Showing {len(filtered)} articles from database")
            st.divider()

            for _, row in filtered.head(30).iterrows():
                score = row["sentiment_score"]
                label = row["sentiment_label"]
                badge_color = ("#E24B4A" if label == "negative"
                               else "#1D9E75" if label == "positive"
                               else "#8b949e")
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"**{row['title']}**")
                        if row.get("first_paragraph"):
                            st.caption(str(row["first_paragraph"])[:200] + "...")
                        st.caption(f"{row['section']} · {str(row['published_at'])[:10]}")
                    with c2:
                        st.markdown(
                            f'<div style="background:{badge_color};color:white;'
                            f'padding:4px 10px;border-radius:6px;text-align:center;'
                            f'font-size:12px;font-family:monospace">{score:.2f}</div>',
                            unsafe_allow_html=True
                        )

# ── Page: News + flight correlation ──────────────────────────────────────────

elif page == "🔗 News + flight correlation":
    st.markdown("# 🔗 News + Flight Correlation")
    st.caption(
        "Articles containing conflict, sanctions or airspace keywords "
        "matched to affected routes"
    )

    corr_df = correlate_news_with_routes(articles_df)

    if corr_df.empty:
        st.info("No correlations found — run the pipeline to ingest more articles")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Correlated articles", len(corr_df))
        with c2:
            conflict_count = corr_df["impact_tags"].str.contains("conflict").sum()
            st.metric("Conflict-tagged", int(conflict_count))
        with c3:
            airspace_count = corr_df["impact_tags"].str.contains("airspace").sum()
            st.metric("Airspace-tagged", int(airspace_count))

        st.divider()

        impact_filter = st.multiselect(
            "Filter by impact type",
            ["conflict", "sanctions", "airspace"],
            default=["conflict", "airspace"]
        )

        if impact_filter:
            mask = corr_df["impact_tags"].apply(
                lambda t: any(f in t for f in impact_filter)
            )
            filtered_corr = corr_df[mask]
        else:
            filtered_corr = corr_df

        st.caption(f"Showing {len(filtered_corr)} correlated articles")
        st.divider()

        for _, row in filtered_corr.head(25).iterrows():
            score = row["sentiment_score"]
            badge_color = "#E24B4A" if score < -0.2 else "#1D9E75" if score > 0.2 else "#8b949e"
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 2, 1])
                with c1:
                    st.markdown(f"**{row['title']}**")
                    st.caption(str(row["published_at"])[:10])
                with c2:
                    st.caption(f"**Affected routes:** {row['affected_routes']}")
                    st.caption(f"**Impact:** {row['impact_tags']}")
                with c3:
                    st.markdown(
                        f'<div style="background:{badge_color};color:white;'
                        f'padding:4px 10px;border-radius:6px;text-align:center;'
                        f'font-size:12px;font-family:monospace">{score:.2f}</div>',
                        unsafe_allow_html=True
                    )

# ── Page: Data insights ───────────────────────────────────────────────────────

elif page == "📊 Data insights":
    st.markdown("# 📊 Data Insights")

    tab1, tab2, tab3 = st.tabs(["Flight states", "Articles", "Prices"])

    with tab1:
        st.markdown("#### Live flight states")
        if not flight_states_df.empty:
            st.dataframe(
                flight_states_df[["callsign","origin_country","lat","lon",
                                   "altitude_m","velocity_ms","recorded_at"]].head(200),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("No flight state data")

    with tab2:
        st.markdown("#### Scraped articles")
        if not articles_df.empty:
            display = articles_df[["title","section","sentiment_label",
                                    "sentiment_score","published_at"]].copy()
            display["sentiment_score"] = display["sentiment_score"].round(3)
            st.dataframe(display.head(200), use_container_width=True, hide_index=True)
        else:
            st.info("No article data")

    with tab3:
        st.markdown("#### Flight prices")
        if not prices_df.empty:
            has_prices = prices_df[prices_df["price_usd"] > 0]
            if has_prices.empty:
                st.warning(
                    "Aviationstack free tier returns route/airline data but "
                    "not live prices. Price estimates are generated by the "
                    "mechanistic model on the Route forecasts page instead."
                )
                st.caption("Airlines operating these routes:")
                st.dataframe(
                    prices_df[["origin","destination","airline","fetched_at"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.dataframe(has_prices, use_container_width=True, hide_index=True)
        else:
            st.info("No price data")

# ── Page: Validation ──────────────────────────────────────────────────────────

elif page == "🔬 Validation":
    st.markdown("# 🔬 Model Validation")
    st.caption(
        "Three independent validation approaches confirming "
        "the model's geopolitical price signal."
    )

    try:
        from geopulse.analysis.validator import run_full_validation
        from geopulse.analysis.spot_check import get_spot_check_summary
        from geopulse.analysis.backtester import summarise_backtest, run_backtest

        with st.spinner("Running validation suite..."):
            report     = run_full_validation(os.getenv("DB_PATH", "data/geopulse.db"))
            spot_check = get_spot_check_summary(os.getenv("DB_PATH", "data/geopulse.db"))
            bt_summary = summarise_backtest(os.getenv("DB_PATH", "data/geopulse.db"))
            bt_df      = run_backtest(os.getenv("DB_PATH", "data/geopulse.db"))

        verdict = report.get("overall_verdict", "")
        if "STRONG" in verdict:
            st.success(f"Overall verdict: {verdict}")
        elif "MODERATE" in verdict:
            st.warning(f"Overall verdict: {verdict}")
        else:
            st.info(f"Overall verdict: {verdict}")

        st.divider()

        # Validation 1 — Backtesting
        st.subheader("Validation 1 — Automated backtesting")
        if bt_summary.get("status") == "complete":
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Events detected", bt_summary["total_events"])
            with c2: st.metric("Avg price uplift", f"+{bt_summary['avg_uplift_pct']}%")
            with c3: st.metric("Max uplift", f"+{bt_summary['max_uplift_pct']}%")
            with c4: st.metric("Most affected", bt_summary["max_uplift_route"].replace("London → ","LHR→"))

            if not bt_df.empty:
                import plotly.express as px
                zone_summary = bt_df.groupby("zone").agg(
                    avg_uplift=("uplift_pct","mean")
                ).reset_index()
                zone_summary["zone"] = zone_summary["zone"].map(
                    lambda z: ZONE_LABELS.get(z, z)
                )
                fig = px.bar(
                    zone_summary.sort_values("avg_uplift"),
                    x="avg_uplift", y="zone", orientation="h",
                    color_discrete_sequence=["#EF9F27"],
                    labels={"avg_uplift":"Avg uplift (%)","zone":""},
                )
                fig.update_layout(
                    paper_bgcolor="#0d1117", plot_bgcolor="#161b2e",
                    font=dict(color="white"), margin=dict(l=0,r=0,t=10,b=0), height=250,
                )
                st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Validation 2 — Directional accuracy
        st.subheader("Validation 2 — Directional accuracy")
        directional = report.get("validation_2_directional", {})
        if directional.get("status") == "complete":
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Directional accuracy",
                          f"{directional['directional_accuracy_pct']}%")
            with c2:
                st.metric("Correct predictions",
                          f"{directional['correct_direction']}/{directional['total_predictions']}")
            with c3:
                interp = directional["interpretation"]
                if interp == "STRONG":
                    st.success(f"Signal: {interp}")
                else:
                    st.warning(f"Signal: {interp}")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**By zone**")
                for zone, acc in directional["by_zone"].items():
                    st.progress(int(acc)/100,
                                text=f"{ZONE_LABELS.get(zone,zone)}: {acc}%")
            with col2:
                st.markdown("**By route**")
                for route, acc in directional["by_route"].items():
                    st.progress(int(acc)/100, text=f"{route}: {acc}%")

        st.divider()

        # Validation 3 — Fuel correlation
        st.subheader("Validation 3 — Sentiment vs fuel price correlation")
        fuel_corr = report.get("validation_3_fuel_correlation", {})
        if fuel_corr.get("status") == "complete":
            c1, c2, c3 = st.columns(3)
            r_change = fuel_corr["negative_news_vs_fuel_change"]["pearson_r"]
            p_change = fuel_corr["negative_news_vs_fuel_change"]["p_value"]
            r_level  = fuel_corr["sentiment_vs_fuel_level"]["pearson_r"]
            p_level  = fuel_corr["sentiment_vs_fuel_level"]["p_value"]
            with c1:
                st.metric("Neg. news vs fuel change",
                          f"r = {r_change}",
                          delta=f"p = {p_change:.3f}")
            with c2:
                st.metric("Sentiment vs fuel level",
                          f"r = {r_level}",
                          delta=f"p = {p_level:.3f}")
            with c3:
                st.metric("Data points", fuel_corr["data_points"])
                st.caption(fuel_corr["date_range"])

        st.divider()

        # Validation 4 — Spot checks
        st.subheader("Validation 4 — Google Flights spot check")
        if spot_check.get("status") == "no_data":
            st.warning("No spot checks yet — record your first below.")
        elif spot_check.get("status") == "complete":
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Total checks", spot_check["total_checks"])
            with c2: st.metric("Avg error", f"{spot_check['avg_abs_error_pct']}%")
            with c3: st.metric("Within 15%", f"{spot_check['pct_within_15']}%")
            if spot_check.get("recent_checks"):
                st.dataframe(pd.DataFrame(spot_check["recent_checks"]),
                             use_container_width=True, hide_index=True)

        with st.form("spot_check_form"):
            st.markdown("**Record Google Flights prices (economy, 30 days out)**")
            c1, c2 = st.columns(2)
            with c1:
                dxb  = st.number_input("London → Dubai (£)",    min_value=0.0, step=10.0)
                tlv  = st.number_input("London → Tel Aviv (£)", min_value=0.0, step=10.0)
                del_ = st.number_input("London → Delhi (£)",    min_value=0.0, step=10.0)
            with c2:
                bkk  = st.number_input("London → Bangkok (£)",    min_value=0.0, step=10.0)
                hkg  = st.number_input("London → Hong Kong (£)",  min_value=0.0, step=10.0)
                nrt  = st.number_input("London → Tokyo (£)",      min_value=0.0, step=10.0)
            submitted = st.form_submit_button("Save spot check", use_container_width=True)
            if submitted:
                from geopulse.analysis.spot_check import record_spot_check
                prices = {}
                if dxb  > 0: prices["London → Dubai"]    = dxb
                if tlv  > 0: prices["London → Tel Aviv"]  = tlv
                if del_ > 0: prices["London → Delhi"]     = del_
                if bkk  > 0: prices["London → Bangkok"]   = bkk
                if hkg  > 0: prices["London → Hong Kong"] = hkg
                if nrt  > 0: prices["London → Tokyo"]     = nrt
                if prices:
                    record_spot_check(os.getenv("DB_PATH", "data/geopulse.db"), prices)
                    st.success(f"Saved {len(prices)} spot checks!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Enter at least one price.")

    except Exception as e:
        st.error(f"Validation error: {e}")
        st.info("Make sure the pipeline has been run at least once.")