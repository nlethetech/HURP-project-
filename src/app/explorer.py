#!/usr/bin/env python3
"""Interactive data explorer for the enriched HURP study panel.

A local Streamlit app to BROWSE full rows and run data analytics on the
583,490 x 173 conflict x agriculture study panel: a filterable data table,
country profiles, time series, distributions, the conflict<->agriculture
scatter, correlations, and group-by aggregates.

Run
---
    .venv/bin/streamlit run src/app/explorer.py
    # then open http://localhost:8501
"""
from __future__ import annotations

import re
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean_enriched.parquet"
CODEBOOK = ROOT / "docs" / "CODEBOOK.md"

st.set_page_config(page_title="HURP Data Explorer", layout="wide", page_icon="🌍")

# --- column -> layer mapping (matcher, label, accent) ---
LAYERS = [
    (lambda c: c in {"district_id", "iso3", "district_name", "admin_level", "year", "continent", "region"}, "Keys & geography", "#c9a227"),
    (lambda c: c.startswith(("n_events_", "deaths_")), "Conflict — UCDP", "#c0603a"),
    (lambda c: c.startswith("coups_"), "Coups", "#b5552f"),
    (lambda c: c.startswith("acled_"), "ACLED unrest", "#a8482a"),
    (lambda c: c.startswith("wb_") or c.startswith("income_group"), "World Bank socioeconomic", "#7d8a4a"),
    (lambda c: c == "precip_mm" or c.startswith(("yield_", "cropland", "price_shock")), "Agriculture base", "#6f8f4f"),
    (lambda c: c.startswith(("colonizer", "coldat_", "col_", "legal_origin", "civil_vs_common", "independence_year", "years_since_independence")), "Colonial legacy", "#a86f3c"),
    (lambda c: c.startswith(("faw_", "dl_")), "Pest shocks (Africa)", "#8a6d3b"),
    (lambda c: c.startswith("grd_"), "State capacity", "#9c7a4d"),
    (lambda c: c.startswith("vdem_") or c in {"polity2", "anocracy_flag"}, "Regime & democracy", "#b08948"),
    (lambda c: c.startswith("pts_"), "Repression", "#8f5b45"),
    (lambda c: c.startswith(("refugees_", "asylum_", "idp_", "returned_", "new_disp_", "stateless")), "Displacement", "#a35a4a"),
    (lambda c: c.startswith("temp_"), "Temperature", "#c77b3d"),
    (lambda c: c.startswith(("travel_time", "market_access")), "Market access", "#9a8352"),
    (lambda c: c.startswith(("has_oil", "n_oil", "has_gas", "oil_gas", "has_diamond", "n_diamond", "has_lootable", "n_mineral")), "Natural resources", "#8c7a3f"),
    (lambda c: c.startswith(("share_area_excluded", "any_excluded", "n_groups", "ethnic_fract")), "Ethnic exclusion", "#b06a4e"),
    (lambda c: c.startswith("ipc_") or c == "fews_covered", "Food insecurity", "#c46a3a"),
    (lambda c: c.startswith("fao_"), "FAOSTAT agriculture", "#6d9152"),
]


def layer_of(col: str) -> str:
    for match, label, _ in LAYERS:
        if match(col):
            return label
    return "Other"


@st.cache_data(show_spinner="Loading the 583k-row panel…")
def load() -> pd.DataFrame:
    return pd.read_parquet(PANEL)


@st.cache_data
def definitions() -> dict[str, str]:
    defs: dict[str, str] = {}
    for line in CODEBOOK.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        cols = re.findall(r"`([a-z0-9_]+)`", cells[0])
        brace = re.match(r"`?([a-z0-9_]*)\{([a-z0-9_,]+)\}([a-z0-9_]*)`?", cells[0])
        if brace:
            pre, mids, post = brace.groups()
            cols += [f"{pre}{m}{post}" for m in mids.split(",")]
        for c in cols:
            defs.setdefault(c, re.sub("`", "", cells[1]).strip())
    return defs


df = load()
DEFS = definitions()
NUM = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool and c != "year"]
CAT = [c for c in df.columns if c not in NUM and c != "year"]
LAYER_COLS: dict[str, list[str]] = {}
for c in df.columns:
    LAYER_COLS.setdefault(layer_of(c), []).append(c)


@st.cache_data
def iso_labels(isos: tuple[str, ...]) -> dict[str, str]:
    names = coco.CountryConverter().convert(list(isos), src="ISO3", to="name_short", not_found=None)
    return {i: f"{(n if n and n != 'not found' else i)} — {i}" for i, n in zip(isos, names)}


LAB = iso_labels(tuple(sorted(df["iso3"].unique())))   # iso3 -> "Country name — ISO3"
LAB2ISO = {v: k for k, v in LAB.items()}


def country_picker(container, label: str, options_iso: list[str], default_iso: list[str] | None = None, multi=True):
    """A country selector that shows full names but returns iso3 codes."""
    opts = sorted(LAB[i] for i in options_iso)
    defaults = [LAB[i] for i in (default_iso or []) if i in LAB]
    if multi:
        sel = container.multiselect(label, opts, default=defaults)
        return [LAB2ISO[s] for s in sel]
    idx = opts.index(LAB[default_iso[0]]) if default_iso and default_iso[0] in LAB else 0
    return LAB2ISO[container.selectbox(label, opts, index=idx)]


# --- district -> country-year aggregation, per column, so numbers stay interpretable ---
@st.cache_data(show_spinner="Indexing columns…")
def broadcast_set() -> frozenset:
    """Columns that are already NATIONAL (constant across a country's districts)."""
    g = df.groupby(["iso3", "year"])
    return frozenset(c for c in NUM if g[c].nunique(dropna=True).max() <= 1)


BCAST = broadcast_set()
_COUNT_PREFIX = ("deaths_", "n_events_", "coups_", "acled_events_", "refugees_", "asylum_",
                 "idp_", "returned_", "new_disp_", "n_diamond", "n_oil", "n_mineral",
                 "faw_n_trap", "faw_confirmed", "faw_suspconf", "dl_swarm", "dl_band", "dl_gregarious")
_COUNT_EXACT = {"acled_fatalities", "cropland_ha", "dl_area_treated_ha", "stateless"}


def agg_of(col: str) -> str:
    """national value for broadcast cols; national TOTAL for district counts; else average."""
    if col in BCAST:
        return "mean"                       # constant across districts == the national value
    if col.startswith(_COUNT_PREFIX) or col in _COUNT_EXACT or col.endswith(("_prod_t", "_area_ha")):
        return "sum"                        # district counts -> national total
    return "mean"


def country_year(data: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    aggmap = {c: (agg_of(c) if c in NUM else "first") for c in cols}
    return data.groupby(["iso3", "year"]).agg(aggmap).reset_index()


def agg_note(col: str) -> str:
    return {"sum": "national total", "mean": "national value" if col in BCAST else "district average"}[agg_of(col)]

# ---------------- Sidebar filters ----------------
st.sidebar.title("🌍 Filters")
regions = st.sidebar.multiselect("Region", sorted(df["region"].unique()), default=sorted(df["region"].unique()))
d0 = df[df["region"].isin(regions)] if regions else df
st.sidebar.caption("Country — search by full name or code (empty = all)")
countries = country_picker(st.sidebar, "Country", sorted(d0["iso3"].unique()))
ymin, ymax = int(df["year"].min()), int(df["year"].max())
yr = st.sidebar.slider("Year range", ymin, ymax, (ymin, ymax))
f = d0[d0["year"].between(*yr)]
if countries:
    f = f[f["iso3"].isin(countries)]
st.sidebar.markdown(f"**{len(f):,}** of {len(df):,} rows · **{f['iso3'].nunique()}** countries")
AGG_HELP = "District rows are collapsed to country-year. mean = per-district average (right for rates/indices/broadcast national values); sum = national total (right for counts like deaths or production)."

# ---------------- Header ----------------
st.markdown("### HURP — Conflict × Agriculture Data Explorer")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Rows (filtered)", f"{len(f):,}")
c2.metric("Columns", df.shape[1])
c3.metric("Countries", f["iso3"].nunique())
c4.metric("Years", f"{yr[0]}–{yr[1]}")
c5.metric("Districts", f"{f['district_id'].nunique():,}")

tabs = st.tabs(["📋 Data table", "🗺️ Country profile", "📈 Time series", "📊 Distribution",
                "🔗 Conflict ↔ Agriculture", "🌡️ Correlations", "📦 Group & aggregate", "📚 Columns"])

# ---------------- 1. Data table ----------------
with tabs[0]:
    st.caption("Browse the actual rows. Pick columns by layer, sort by clicking a header, and download the filtered slice.")
    pick_layers = st.multiselect("Column groups to show", list(LAYER_COLS),
                                 default=["Keys & geography", "Conflict — UCDP", "FAOSTAT agriculture"])
    cols = [c for lyr in pick_layers for c in LAYER_COLS[lyr]] or ["district_id", "iso3", "year"]
    extra = st.multiselect("…or add specific columns", df.columns.tolist(), default=[])
    show = list(dict.fromkeys(["iso3", "year", "district_name"] + cols + extra))
    view = f[show]
    max_rows = st.slider("Rows to preview", 100, 20000, 1000, step=100,
                         help="A capped preview — no browser can render all 583k rows. Filter (sidebar) to narrow, or download for the full filtered slice.")
    st.caption(f"Showing **{min(len(view), max_rows):,}** of **{len(view):,}** filtered rows · {len(show)} columns.")
    st.dataframe(view.head(max_rows), use_container_width=True, height=560, hide_index=True)
    if len(view) <= 200_000:
        import io
        buf = io.BytesIO()
        view.to_csv(buf, index=False, compression="gzip")
        st.download_button("⬇︎ Download filtered data (.csv.gz)", buf.getvalue(),
                           "hurp_filtered.csv.gz", "application/gzip")
    else:
        st.info("Narrow the filters (region / country / year) to enable a download here — "
                "or use the full export at `data/published/hurp_study_panel_full.csv.gz`.")

# ---------------- 2. Country profile ----------------
with tabs[1]:
    ctry = country_picker(st, "Country", sorted(df["iso3"].unique()),
                          default_iso=["NGA"] if "NGA" in df["iso3"].values else None, multi=False)
    cc = df[(df["iso3"] == ctry) & (df["year"].between(*yr))]
    st.caption(f"{LAB.get(ctry, ctry)} · {cc['district_id'].nunique()} districts · each metric aggregated to the country appropriately (national total for counts, national value for country-level data, average for rates).")
    default_metrics = [m for m in ["deaths_best_total", "fao_cereal_prod_t", "temp_anomaly", "share_area_excluded", "grd_tax_pct_gdp"] if m in df.columns]
    metrics = st.multiselect("Metrics to chart", NUM, default=default_metrics)
    if metrics:
        cy = country_year(cc, metrics)
        for m in metrics:
            fig = px.area(cy, x="year", y=m, title=f"{LAB.get(ctry, ctry)} — {m}  ·  {agg_note(m)}")
            fig.update_traces(line_color="#e0a53d", fillcolor="rgba(224,165,61,.15)")
            st.plotly_chart(fig, use_container_width=True)

# ---------------- 3. Time series ----------------
with tabs[2]:
    m = st.selectbox("Metric", NUM, index=NUM.index("fao_cereal_prod_t") if "fao_cereal_prod_t" in NUM else 0)
    st.caption(f"Aggregated per country as: **{agg_note(m)}**.")
    default_c = [c for c in ["NGA", "ETH", "COD", "COL"] if c in f["iso3"].values][:4]
    cs = country_picker(st, "Countries", sorted(f["iso3"].unique()), default_iso=default_c)
    g = f[f["iso3"].isin(cs)] if cs else f
    ts = country_year(g, [m]).replace([np.inf, -np.inf], np.nan)
    ts["country"] = ts["iso3"].map(LAB)
    st.plotly_chart(px.line(ts, x="year", y=m, color="country", markers=True, title=f"{m} over time"),
                    use_container_width=True)

# ---------------- 4. Distribution ----------------
with tabs[3]:
    col = st.selectbox("Column", NUM + CAT)
    st.caption(DEFS.get(col, ""))
    s = f[col].dropna()
    if col in NUM:
        a, b = st.columns([2, 1])
        s_plot = s.sample(50000, random_state=0) if len(s) > 50000 else s
        a.plotly_chart(px.histogram(s_plot, nbins=40, title=f"Distribution of {col}"), use_container_width=True)
        b.write(s.describe().to_frame(col))
        b.metric("Coverage", f"{100*f[col].notna().mean():.0f}%")
    else:
        vc = s.value_counts().head(25).reset_index()
        vc.columns = [col, "count"]
        st.plotly_chart(px.bar(vc, x="count", y=col, orientation="h", title=f"{col} — top values"), use_container_width=True)

# ---------------- 5. Conflict <-> Agriculture (the analytics view) ----------------
with tabs[4]:
    st.caption("The two-way question. Each point is a country-year (districts aggregated). Pick any X and Y — e.g. agricultural output vs conflict deaths.")
    a, b = st.columns(2)
    x = a.selectbox("X axis", NUM, index=NUM.index("fao_cereal_prod_t") if "fao_cereal_prod_t" in NUM else 0)
    y = b.selectbox("Y axis", NUM, index=NUM.index("deaths_best_total") if "deaths_best_total" in NUM else 1)
    color = st.selectbox("Colour by", ["region", "colonizer", "civil_vs_common", "None"])
    cols = [x, y] + ([] if color == "None" else [color])
    cy = country_year(f, cols).replace([np.inf, -np.inf], np.nan).dropna(subset=[x, y])
    cy["country"] = cy["iso3"].map(LAB)
    fig = px.scatter(cy, x=x, y=y, color=None if color == "None" else color,
                     hover_data=["country", "year"], opacity=0.6,
                     title=f"{y} ({agg_note(y)}) vs {x} ({agg_note(x)}) — each point a country-year")
    st.plotly_chart(fig, use_container_width=True)
    if len(cy) > 2:
        r = cy[[x, y]].corr().iloc[0, 1]
        st.metric("Pearson correlation (X, Y)", f"{r:+.3f}", help="Raw association across country-years — not causal.")

# ---------------- 6. Correlations ----------------
with tabs[5]:
    themed = [c for c in ["deaths_best_total", "acled_events_total", "fao_cereal_prod_t", "fao_cereal_yield_kgha",
                          "temp_anomaly", "precip_mm", "share_area_excluded", "grd_tax_pct_gdp", "vdem_polyarchy",
                          "pts_score", "idp_stock_conflict", "ipc_phase_max"] if c in NUM]
    sel = st.multiselect("Columns", NUM, default=themed)
    if len(sel) >= 2:
        cy = country_year(f, sel)
        corr = cy[sel].corr()
        st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                                  aspect="auto", title="Correlation across country-years"), use_container_width=True)
    else:
        st.info("Pick at least two columns.")

# ---------------- 7. Group & aggregate ----------------
with tabs[6]:
    a, b, c = st.columns(3)
    by = a.selectbox("Group by", ["region", "colonizer", "civil_vs_common", "col_british", "anocracy_flag", "year"])
    metric = b.selectbox("Metric ", NUM, index=NUM.index("deaths_best_total") if "deaths_best_total" in NUM else 0)
    how = c.selectbox("Aggregate ", ["mean", "sum", "median", "max"])
    g = f.dropna(subset=[by]).groupby(by)[metric].agg(how).reset_index().sort_values(metric, ascending=False)
    l, r = st.columns([1, 1])
    l.plotly_chart(px.bar(g, x=by, y=metric, title=f"{how}({metric}) by {by}").update_traces(marker_color="#e0a53d"),
                   use_container_width=True)
    r.dataframe(g, use_container_width=True, hide_index=True, height=420)

# ---------------- 8. Columns (dictionary) ----------------
with tabs[7]:
    q = st.text_input("Search columns", "")
    rows = []
    for c in df.columns:
        if q and q.lower() not in c.lower() and q.lower() not in DEFS.get(c, "").lower():
            continue
        rows.append({"column": c, "layer": layer_of(c), "definition": DEFS.get(c, "—"),
                     "coverage %": round(100 * df[c].notna().mean()), "distinct": int(df[c].nunique())})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=560)
