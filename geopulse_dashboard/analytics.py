import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json

ZONE_LABELS = {
    "russian_airspace":      "Russian airspace",
    "ukrainian_airspace":    "Ukrainian airspace",
    "iranian_airspace":      "Iranian airspace",
    "iraqi_syrian_airspace": "Iraqi/Syrian airspace",
    "red_sea_corridor":      "Red Sea corridor",
}

RISK_COLORS = {
    "CRITICAL": "#E24B4A",
    "HIGH":     "#EF9F27",
    "MEDIUM":   "#378ADD",
    "LOW":      "#1D9E75",
}

WAR_KEYWORDS    = ["war", "attack", "strike", "conflict", "missile", "bomb", "kill"]
SANCTION_KEYWORDS = ["sanctions", "embargo", "ban", "restrict"]
AIRSPACE_KEYWORDS = ["airspace", "flight ban", "no-fly", "reroute", "divert", "aviation"]


def tag_news_impact(title: str, summary: str = "") -> list[str]:
    text = f"{title} {summary}".lower()
    tags = []
    if any(k in text for k in WAR_KEYWORDS):
        tags.append("conflict")
    if any(k in text for k in SANCTION_KEYWORDS):
        tags.append("sanctions")
    if any(k in text for k in AIRSPACE_KEYWORDS):
        tags.append("airspace")
    return tags


def correlate_news_with_routes(articles_df: pd.DataFrame) -> pd.DataFrame:
    ZONE_ROUTE_MAP = {
        "russian_airspace":      ["LHR→DEL", "LHR→BKK", "LHR→HKG", "LHR→NRT"],
        "ukrainian_airspace":    ["LHR→DEL", "LHR→HKG", "LHR→NRT"],
        "iranian_airspace":      ["LHR→DXB", "LHR→DEL"],
        "iraqi_syrian_airspace": ["LHR→TLV", "LHR→DXB"],
        "red_sea_corridor":      ["LHR→DXB", "LHR→BKK"],
    }

    if articles_df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in articles_df.iterrows():
        tags = []
        try:
            tags = json.loads(row.get("geo_tags", "[]") or "[]")
        except Exception:
            pass

        impact_tags = tag_news_impact(
            row.get("title", ""),
            row.get("first_paragraph", "")
        )

        if not impact_tags:
            continue

        affected_routes = []
        for zone in tags:
            affected_routes.extend(ZONE_ROUTE_MAP.get(zone, []))

        if affected_routes:
            rows.append({
                "title":           row.get("title", ""),
                "published_at":    row.get("published_at", ""),
                "sentiment_score": row.get("sentiment_score", 0),
                "affected_routes": ", ".join(set(affected_routes)),
                "impact_tags":     ", ".join(impact_tags),
                "zones":           ", ".join(tags),
            })

    return pd.DataFrame(rows)


def build_price_distribution(prices_df: pd.DataFrame) -> go.Figure:
    if prices_df.empty:
        return go.Figure()

    fig = px.histogram(
        prices_df[prices_df["price_usd"] > 0],
        x="price_usd",
        nbins=30,
        color_discrete_sequence=["#378ADD"],
        labels={"price_usd": "Price (USD)", "count": "Flights"},
    )
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748"),
        bargap=0.1,
    )
    return fig


def build_price_by_route(prices_df: pd.DataFrame) -> go.Figure:
    if prices_df.empty or prices_df[prices_df["price_usd"] > 0].empty:
        return go.Figure()

    df = prices_df[prices_df["price_usd"] > 0].copy()
    df["route"] = df["origin"] + "→" + df["destination"]
    summary = df.groupby("route")["price_usd"].agg(["mean", "min", "max"]).reset_index()
    summary.columns = ["route", "avg", "min", "max"]
    summary = summary.sort_values("avg", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=summary["avg"],
        y=summary["route"],
        orientation="h",
        marker_color="#EF9F27",
        name="Avg price",
        hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        xaxis=dict(gridcolor="#2d3748", title="Price (USD)"),
        yaxis=dict(gridcolor="#2d3748"),
    )
    return fig


def build_deviation_timeline(deviation_trend: pd.DataFrame) -> go.Figure:
    if deviation_trend.empty:
        return go.Figure()

    main_zones = list(ZONE_LABELS.keys())
    df = deviation_trend[deviation_trend["zones"].isin(main_zones)].copy()
    df["zone_label"] = df["zones"].map(ZONE_LABELS)

    color_map = {
        "Russian airspace":      "#E24B4A",
        "Ukrainian airspace":    "#EF9F27",
        "Iranian airspace":      "#F09595",
        "Iraqi/Syrian airspace": "#FAC775",
        "Red Sea corridor":      "#378ADD",
    }

    fig = px.line(
        df, x="date", y="count",
        color="zone_label",
        color_discrete_map=color_map,
        labels={"count": "Violations", "date": "", "zone_label": "Zone"},
    )
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="white")),
        margin=dict(l=0, r=0, t=10, b=0),
        height=320,
        xaxis=dict(gridcolor="#2d3748"),
        yaxis=dict(gridcolor="#2d3748"),
    )
    return fig


def build_sentiment_by_zone(articles_df: pd.DataFrame) -> go.Figure:
    if articles_df.empty:
        return go.Figure()

    rows = []
    for _, row in articles_df.iterrows():
        try:
            tags = json.loads(row.get("geo_tags", "[]") or "[]")
        except Exception:
            tags = []
        for zone in tags:
            if zone in ZONE_LABELS:
                rows.append({
                    "zone":  ZONE_LABELS[zone],
                    "score": row.get("sentiment_score", 0)
                })

    if not rows:
        return go.Figure()

    df = pd.DataFrame(rows)
    summary = df.groupby("zone")["score"].mean().reset_index()
    summary.columns = ["zone", "avg_sentiment"]
    summary = summary.sort_values("avg_sentiment")

    colors = ["#E24B4A" if s < -0.3 else "#EF9F27"
              if s < 0 else "#1D9E75" for s in summary["avg_sentiment"]]

    fig = go.Figure(go.Bar(
        x=summary["avg_sentiment"],
        y=summary["zone"],
        orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_dash="dash",
                  line_color="rgba(255,255,255,0.3)", line_width=1)
    fig.update_layout(
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b2e",
        font=dict(color="white"),
        margin=dict(l=0, r=0, t=10, b=0),
        height=280,
        xaxis=dict(gridcolor="#2d3748", title="Avg sentiment score"),
        yaxis=dict(gridcolor="#2d3748"),
    )
    return fig