import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json


ZONE_LABELS = {
    "russian_airspace":      "Russian airspace",
    "ukrainian_airspace":    "Ukrainian airspace",
    "iranian_airspace":      "Iranian airspace",
    "iraqi_syrian_airspace": "Iraqi/Syrian airspace",
    "red_sea_corridor":      "Red Sea corridor",
}

ROUTE_COORDS = {
    "LHR": {"lat": 51.477, "lon": -0.461,  "name": "London Heathrow"},
    "DXB": {"lat": 25.252, "lon": 55.364,  "name": "Dubai"},
    "TLV": {"lat": 32.011, "lon": 34.887,  "name": "Tel Aviv"},
    "DEL": {"lat": 28.556, "lon": 77.100,  "name": "Delhi"},
    "BKK": {"lat": 13.681, "lon": 100.747, "name": "Bangkok"},
    "HKG": {"lat": 22.308, "lon": 113.918, "name": "Hong Kong"},
    "NRT": {"lat": 35.764, "lon": 140.386, "name": "Tokyo Narita"},
}

NO_FLY_ZONES = {
    "Russian airspace": {
        "lats": [68.0, 68.0, 41.0, 41.0, 68.0],
        "lons": [27.0, 180.0, 180.0, 27.0, 27.0],
        "color": "rgba(226,75,74,0.15)",
        "line_color": "#E24B4A"
    },
    "Ukrainian airspace": {
        "lats": [52.5, 52.5, 44.0, 44.0, 52.5],
        "lons": [22.0, 40.0, 40.0, 22.0, 22.0],
        "color": "rgba(239,159,39,0.2)",
        "line_color": "#EF9F27"
    },
    "Iranian airspace": {
        "lats": [39.5, 39.5, 25.0, 25.0, 39.5],
        "lons": [44.0, 63.5, 63.5, 44.0, 44.0],
        "color": "rgba(226,75,74,0.15)",
        "line_color": "#E24B4A"
    },
    "Iraqi/Syrian airspace": {
        "lats": [37.5, 37.5, 29.0, 29.0, 37.5],
        "lons": [35.5, 48.5, 48.5, 35.5, 35.5],
        "color": "rgba(239,159,39,0.15)",
        "line_color": "#EF9F27"
    },
    "Red Sea corridor": {
        "lats": [30.0, 30.0, 12.0, 12.0, 30.0],
        "lons": [32.0, 45.0, 45.0, 32.0, 32.0],
        "color": "rgba(55,138,221,0.15)",
        "line_color": "#378ADD"
    },
}

ROUTE_PAIRS = [
    ("LHR", "DXB"), ("LHR", "TLV"), ("LHR", "DEL"),
    ("LHR", "BKK"), ("LHR", "HKG"), ("LHR", "NRT"),
]

RISK_COLORS = {
    "CRITICAL": "#E24B4A",
    "HIGH":     "#EF9F27",
    "MEDIUM":   "#378ADD",
    "LOW":      "#1D9E75",
}

def build_global_map(
    predictions: list[dict] = None,
    deviations_df: pd.DataFrame = None,
    flight_states_df: pd.DataFrame = None,
    show_no_fly_zones: bool = True,
    show_routes: bool = True,
    show_violations: bool = True,
    show_live_flights: bool = True,
) -> go.Figure:

    fig = go.Figure()

    # No-fly zones — filled polygons with clearer colours
    if show_no_fly_zones:
        zone_styles = {
            "Russian airspace":      {"fill": "rgba(226,75,74,0.12)",  "line": "#E24B4A", "dash": "dot"},
            "Ukrainian airspace":    {"fill": "rgba(239,159,39,0.15)", "line": "#EF9F27", "dash": "dash"},
            "Iranian airspace":      {"fill": "rgba(226,75,74,0.12)",  "line": "#F09595", "dash": "dot"},
            "Iraqi/Syrian airspace": {"fill": "rgba(239,159,39,0.12)", "line": "#FAC775", "dash": "dash"},
            "Red Sea corridor":      {"fill": "rgba(55,138,221,0.18)", "line": "#378ADD", "dash": "dot"},
        }
        for zone_name, zone in NO_FLY_ZONES.items():
            style = zone_styles.get(zone_name, {"fill": "rgba(128,128,128,0.1)", "line": "#888", "dash": "dot"})
            fig.add_trace(go.Scattergeo(
                lat=zone["lats"],
                lon=zone["lons"],
                mode="lines",
                fill="toself",
                fillcolor=style["fill"],
                line=dict(color=style["line"], width=1.8, dash=style["dash"]),
                name=zone_name,
                hovertemplate=f"<b>⛔ {zone_name}</b><br>Restricted airspace<extra></extra>",
                showlegend=True,
            ))

    # Route lines — risk-coloured with curved great circle paths
    if show_routes and predictions:
        pred_map = {}
        for p in predictions:
            dest = p["label"].replace("London → ", "")
            for iata, info in ROUTE_COORDS.items():
                if iata != "LHR" and (dest in info["name"] or info["name"].startswith(dest)):
                    pred_map[iata] = p
                    break

        # Build a label→iata map for better matching
        label_to_dest = {
            "London → Dubai":     "DXB",
            "London → Tel Aviv":  "TLV",
            "London → Delhi":     "DEL",
            "London → Bangkok":   "BKK",
            "London → Hong Kong": "HKG",
            "London → Tokyo":     "NRT",
        }
        pred_by_dest = {label_to_dest.get(p["label"]): p
                        for p in (predictions or [])
                        if label_to_dest.get(p["label"])}

        for origin, destination in ROUTE_PAIRS:
            o = ROUTE_COORDS.get(origin)
            d = ROUTE_COORDS.get(destination)
            if not o or not d:
                continue

            pred  = pred_by_dest.get(destination, {})
            risk  = pred.get("risk_level", "LOW")
            color = RISK_COLORS.get(risk, "#1D9E75")
            price = pred.get("estimated_price_gbp", 0)
            pct   = pred.get("pct_above_base", 0)
            zones = ", ".join(pred.get("triggered_zones", [])) or "None"

            # Generate curved arc with intermediate points
            import numpy as np
            n_points = 50
            lats = [o["lat"] + (d["lat"] - o["lat"]) * i / n_points
                    for i in range(n_points + 1)]
            lons = [o["lon"] + (d["lon"] - o["lon"]) * i / n_points
                    for i in range(n_points + 1)]

            # Add slight arc curvature
            mid = n_points // 2
            for i in range(n_points + 1):
                arc = 4 * (i / n_points) * (1 - i / n_points)
                lats[i] += arc * 8

            fig.add_trace(go.Scattergeo(
                lat=lats,
                lon=lons,
                mode="lines",
                line=dict(width=2.5, color=color),
                opacity=0.85,
                name=f"{origin}→{destination} ({risk})",
                hovertemplate=(
                    f"<b>✈ {origin} → {destination}</b><br>"
                    f"Est. price: <b>£{price:,.0f}</b><br>"
                    f"Above baseline: <b>+{pct}%</b><br>"
                    f"Risk level: <b>{risk}</b><br>"
                    f"Active zones: {zones}<extra></extra>"
                ),
                showlegend=True,
            ))

            # Destination marker with risk colour
            fig.add_trace(go.Scattergeo(
                lat=[d["lat"]],
                lon=[d["lon"]],
                mode="markers",
                marker=dict(size=10, color=color,
                            line=dict(width=2, color="white")),
                hoverinfo="skip",
                showlegend=False,
            ))

    # Violation markers — pulsing red crosses
    if show_violations and deviations_df is not None and not deviations_df.empty:
        recent = deviations_df.head(300)
        if "lat" in recent.columns:
            fig.add_trace(go.Scattergeo(
                lat=recent["lat"],
                lon=recent["lon"],
                mode="markers",
                marker=dict(
                    size=7,
                    color="#E24B4A",
                    symbol="x",
                    opacity=0.8,
                    line=dict(width=1, color="#FF6B6B"),
                ),
                name="⚠ Zone violations",
                hovertemplate=(
                    "<b>⚠ %{customdata[0]}</b><br>"
                    "Zone: %{customdata[1]}<br>"
                    "Alt: %{customdata[2]:.0f}m<br>"
                    "Speed: %{customdata[3]:.0f} m/s<extra></extra>"
                ),
                customdata=recent[["callsign","zones","altitude_m","velocity_ms"]].fillna("").values,
                showlegend=True,
            ))

    # Live flight states — subtle green dots
    if show_live_flights and flight_states_df is not None and not flight_states_df.empty:
        airborne = flight_states_df[flight_states_df["on_ground"] == 0] \
            if "on_ground" in flight_states_df.columns else flight_states_df
        sample = airborne.sample(min(400, len(airborne)))
        fig.add_trace(go.Scattergeo(
            lat=sample["lat"],
            lon=sample["lon"],
            mode="markers",
            marker=dict(
                size=3,
                color="#5DCAA5",
                opacity=0.45,
            ),
            name="Live aircraft",
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Alt: %{customdata[2]:.0f}m<extra></extra>"
            ),
            customdata=sample[["callsign","origin_country","altitude_m"]].fillna("").values,
            showlegend=True,
        ))

    # Origin airport — LHR
    lhr = ROUTE_COORDS["LHR"]
    fig.add_trace(go.Scattergeo(
        lat=[lhr["lat"]],
        lon=[lhr["lon"]],
        mode="markers+text",
        marker=dict(size=14, color="#58a6ff",
                    symbol="circle",
                    line=dict(width=2.5, color="white")),
        text=["LHR"],
        textposition="top right",
        textfont=dict(size=13, color="white", family="JetBrains Mono"),
        name="London Heathrow",
        hovertemplate="<b>London Heathrow (LHR)</b><br>Origin airport<extra></extra>",
        showlegend=False,
    ))

    # Destination airports
    for iata, info in ROUTE_COORDS.items():
        if iata == "LHR":
            continue
        fig.add_trace(go.Scattergeo(
            lat=[info["lat"]],
            lon=[info["lon"]],
            mode="text",
            text=[iata],
            textposition="top right",
            textfont=dict(size=11, color="#8b949e", family="JetBrains Mono"),
            hoverinfo="skip",
            showlegend=False,
        ))

    fig.update_layout(
        geo=dict(
            showland=True,
            landcolor="#1a2035",
            showocean=True,
            oceancolor="#0d1117",
            showlakes=True,
            lakecolor="#0d1420",
            showcountries=True,
            countrycolor="#252d3d",
            countrywidth=0.5,
            showcoastlines=True,
            coastlinecolor="#252d3d",
            coastlinewidth=0.5,
            showframe=False,
            projection_type="natural earth",
            bgcolor="#0d1117",
            center=dict(lat=38, lon=55),
            projection_scale=2.0,
            lataxis=dict(range=[0, 75]),
            lonaxis=dict(range=[-20, 160]),
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        margin=dict(l=0, r=0, t=0, b=0),
        height=640,
        legend=dict(
            bgcolor="rgba(13,17,23,0.92)",
            bordercolor="#2d3748",
            borderwidth=1,
            font=dict(color="#c9d1d9", size=11,
                      family="JetBrains Mono"),
            x=0.01, y=0.99,
            itemsizing="constant",
            tracegroupgap=2,
        ),
        font=dict(color="white"),
        hoverlabel=dict(
            bgcolor="#161b2e",
            bordercolor="#2d3748",
            font=dict(color="white", size=12),
        ),
    )

    return fig

def build_deviation_heatmap(deviations_df: pd.DataFrame) -> go.Figure:
    if deviations_df.empty:
        return go.Figure()

    zone_counts = deviations_df["zones"].value_counts().reset_index()
    zone_counts.columns = ["zone", "count"]

    ZONE_LABELS = {
        "russian_airspace":      "Russian airspace",
        "ukrainian_airspace":    "Ukrainian airspace",
        "iranian_airspace":      "Iranian airspace",
        "iraqi_syrian_airspace": "Iraqi/Syrian airspace",
        "red_sea_corridor":      "Red Sea corridor",
    }
    zone_counts["zone"] = zone_counts["zone"].map(
        lambda z: ZONE_LABELS.get(z.strip(), z)
    )

    fig = px.bar(
        zone_counts.sort_values("count"),
        x="count", y="zone",
        orientation="h",
        color="count",
        color_continuous_scale=["#1D9E75", "#EF9F27", "#E24B4A"],
        labels={"count": "Violations", "zone": ""},
    )
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        coloraxis_showscale=False,
    )
    return fig

def build_price_comparison_chart(predictions: list[dict]) -> go.Figure:
    if not predictions:
        return go.Figure()

    labels     = [p["label"].replace("London → ", "") for p in predictions]
    base_fares = [p["base_fare_gbp"] for p in predictions]
    estimates  = [p["estimated_price_gbp"] for p in predictions]
    risks      = [p["risk_level"] for p in predictions]
    colors     = [RISK_COLORS.get(r, "#888") for r in risks]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Baseline price",
        x=labels, y=base_fares,
        marker_color="#2d3748",
        hovertemplate="Baseline: £%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Estimated price",
        x=labels, y=estimates,
        marker_color=colors,
        hovertemplate="Estimated: £%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        barmode="group",
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="white")),
        margin=dict(l=0, r=0, t=10, b=0),
        height=320,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748", title="Price (£)"),
    )
    return fig

def build_fuel_trend_chart(fuel_df: pd.DataFrame) -> go.Figure:
    if fuel_df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fuel_df["week_date"],
        y=fuel_df["price_usd_per_gallon"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(239,159,39,0.15)",
        line=dict(color="#EF9F27", width=2),
        name="Jet fuel $/gal",
        hovertemplate="%{x|%b %Y}: $%{y:.3f}/gal<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748", title="USD/gallon"),
    )
    return fig

def build_sentiment_trend_chart(sentiment_df: pd.DataFrame) -> go.Figure:
    if sentiment_df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sentiment_df["date"],
        y=sentiment_df["avg_sentiment"],
        mode="lines",
        fill="tozeroy",
        fillcolor="rgba(55,138,221,0.15)",
        line=dict(color="#378ADD", width=2),
        name="Avg sentiment",
        hovertemplate="%{x|%b %d}: %{y:.3f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash",
                  line_color="rgba(255,255,255,0.2)", line_width=1)
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748", title="Sentiment score"),
    )
    return fig