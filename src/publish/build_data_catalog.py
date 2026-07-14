#!/usr/bin/env python3
"""Build a self-contained HTML data catalog for the enriched study panel.

Produces one static HTML file (no server, opens in any browser) that groups every
column by enrichment layer with a plain-language definition (from the codebook),
coverage %, value range / top categories, sample values, and a mini histogram.
A personal tool to see what the dataset holds and understand each column.

Run
---
    .venv/bin/python src/publish/build_data_catalog.py
    open reports/hurp_data_catalog.html
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean_enriched.parquet"
CODEBOOK = ROOT / "docs" / "CODEBOOK.md"
OUT = ROOT / "reports" / "hurp_data_catalog.html"

# (matcher, layer label, accent hex). First match wins; order matters. Warm palette.
LAYERS: list[tuple] = [
    (lambda c: c in {"district_id", "iso3", "district_name", "admin_level", "year", "continent", "region"},
     "Keys & geography", "#c9a227"),
    (lambda c: c.startswith(("n_events_", "deaths_")), "Conflict — UCDP fatal violence", "#c0603a"),
    (lambda c: c.startswith("coups_"), "Coups (Powell & Thyne)", "#b5552f"),
    (lambda c: c.startswith("acled_"), "Political violence & unrest — ACLED", "#a8482a"),
    (lambda c: c.startswith("wb_") or c.startswith("income_group"), "Socioeconomic — World Bank", "#7d8a4a"),
    (lambda c: c in {"precip_mm"} or c.startswith(("yield_", "cropland", "price_shock")),
     "Agriculture base (GDHY / SPAM / prices)", "#6f8f4f"),
    (lambda c: c.startswith(("colonizer", "coldat_", "col_", "legal_origin", "civil_vs_common", "independence_year", "years_since_independence")),
     "Colonial legacy", "#a86f3c"),
    (lambda c: c.startswith(("faw_", "dl_")), "Pest shocks — fall armyworm / locust (Africa)", "#8a6d3b"),
    (lambda c: c.startswith("grd_"), "State capacity (fiscal — GRD)", "#9c7a4d"),
    (lambda c: c.startswith("vdem_") or c in {"polity2", "anocracy_flag"}, "Regime & democracy (V-Dem / Polity)", "#b08948"),
    (lambda c: c.startswith("pts_"), "Repression (Political Terror Scale)", "#8f5b45"),
    (lambda c: c.startswith(("refugees_", "asylum_", "idp_", "returned_", "new_disp_", "stateless")),
     "Displacement (UNHCR / IDMC)", "#a35a4a"),
    (lambda c: c.startswith("temp_"), "Temperature (CRU)", "#c77b3d"),
    (lambda c: c.startswith(("travel_time", "market_access")), "Market access (travel time)", "#9a8352"),
    (lambda c: c.startswith(("has_oil", "n_oil", "has_gas", "oil_gas", "has_diamond", "n_diamond", "has_lootable", "n_mineral")),
     "Natural resources (oil / diamonds / minerals)", "#8c7a3f"),
    (lambda c: c.startswith(("share_area_excluded", "any_excluded", "n_groups", "ethnic_fract")),
     "Ethnic exclusion (EPR)", "#b06a4e"),
    (lambda c: c.startswith("ipc_") or c == "fews_covered", "Food insecurity (FEWS / IPC)", "#c46a3a"),
    (lambda c: c.startswith("fao_"), "Agricultural output — FAOSTAT", "#6d9152"),
]


def layer_of(col: str) -> tuple[str, str]:
    for match, label, hex_ in LAYERS:
        if match(col):
            return label, hex_
    return "Other", "#888"


def codebook_defs() -> dict[str, str]:
    """Extract `col` -> definition from the codebook markdown tables."""
    defs: dict[str, str] = {}
    for line in CODEBOOK.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        cols = re.findall(r"`([a-z0-9_]+)`", cells[0])
        # expand brace patterns like fao_{maize,rice}_prod_t
        brace = re.match(r"`?([a-z0-9_]*)\{([a-z0-9_,]+)\}([a-z0-9_]*)`?", cells[0])
        if brace:
            pre, mids, post = brace.groups()
            cols += [f"{pre}{m}{post}" for m in mids.split(",")]
        d = re.sub(r"`", "", cells[1]).strip()
        for c in cols:
            defs.setdefault(c, d)
    return defs


def spark(values: np.ndarray, accent: str) -> str:
    """Inline SVG histogram (12 bins) for numeric values."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return ""
    if np.nanmin(v) == np.nanmax(v):
        counts = np.array([v.size]); edges = np.array([v[0], v[0]])
    else:
        counts, edges = np.histogram(v, bins=12)
    h = np.log1p(counts); h = h / h.max() if h.max() > 0 else h
    w, H, gap = 9, 34, 2
    bars = "".join(
        f'<rect x="{i*(w+gap)}" y="{H-max(2,int(hi*H))}" width="{w}" height="{max(2,int(hi*H))}" fill="{accent}" opacity="0.85"/>'
        for i, hi in enumerate(h))
    return f'<svg width="{12*(w+gap)}" height="{H}" class="spark">{bars}</svg>'


def col_stats(s: pd.Series, accent: str) -> dict:
    cov = float(s.notna().mean())
    out = {"coverage": cov, "dtype": str(s.dtype), "n_unique": int(s.nunique(dropna=True))}
    nn = s.dropna()
    if pd.api.types.is_numeric_dtype(s) and s.dtype != bool and out["n_unique"] > 12:
        out["kind"] = "numeric"
        out["min"], out["max"] = float(nn.min()), float(nn.max())
        out["mean"], out["median"] = float(nn.mean()), float(nn.median())
        out["spark"] = spark(nn.to_numpy(dtype="float64"), accent)
    else:
        out["kind"] = "categorical"
        vc = nn.value_counts().head(6)
        out["top"] = [(str(k), int(v)) for k, v in vc.items()]
    return out


def fmt(x: float) -> str:
    if abs(x) >= 1e6:
        return f"{x/1e6:,.2f}M"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if abs(x) >= 1 or x == 0:
        return f"{x:,.2f}"
    return f"{x:.4g}"


def main() -> None:
    df = pd.read_parquet(PANEL)
    defs = codebook_defs()
    n_rows, n_cols = df.shape
    n_ctry = df["iso3"].nunique()
    y0, y1 = int(df["year"].min()), int(df["year"].max())
    reg = df.drop_duplicates("iso3")["region"].value_counts().to_dict()

    # group columns by layer, preserving panel order
    groups: dict[str, dict] = {}
    for col in df.columns:
        label, accent = layer_of(col)
        groups.setdefault(label, {"accent": accent, "cols": []})
        groups[label]["cols"].append(col)
    # order groups by the LAYERS list
    order = [lab for _, lab, _ in LAYERS] + ["Other"]
    ordered = [(lab, groups[lab]) for lab in order if lab in groups]

    def rows_html(cols, accent):
        out = []
        for col in cols:
            st = col_stats(df[col], accent)
            definition = html.escape(defs.get(col, "—"))
            covpct = round(st["coverage"] * 100)
            if st["kind"] == "numeric":
                stat = (f'range <b>{fmt(st["min"])}</b> – <b>{fmt(st["max"])}</b> · '
                        f'median {fmt(st["median"])}')
                viz = st.get("spark", "")
            else:
                chips = " ".join(f'<span class="chip">{html.escape(k)} <em>{v:,}</em></span>' for k, v in st["top"])
                stat = f'{st["n_unique"]} distinct · {chips}'
                viz = ""
            out.append(f"""
      <div class="col" data-name="{col}" data-def="{definition.lower()}">
        <div class="cn"><span class="dot" style="background:{accent}"></span>{col}</div>
        <div class="cd">{definition}</div>
        <div class="cs">{stat}</div>
        <div class="cv">{viz}</div>
        <div class="cc"><div class="bar"><i style="width:{covpct}%;background:{accent}"></i></div><span>{covpct}%</span></div>
      </div>""")
        return "".join(out)

    sections = "".join(f"""
    <section class="layer" id="L{i}" data-layer="{html.escape(lab)}">
      <h2 style="border-color:{g['accent']}"><span>{html.escape(lab)}</span><em>{len(g['cols'])} cols</em></h2>
      <div class="cols">{rows_html(g['cols'], g['accent'])}</div>
    </section>""" for i, (lab, g) in enumerate(ordered))

    chips = "".join(f'<div class="stat"><b>{v}</b><span>{html.escape(k)}</span></div>'
                    for k, v in [("rows", f"{n_rows:,}"), ("columns", str(n_cols)),
                                 ("countries", str(n_ctry)), ("years", f"{y0}–{y1}"),
                                 ("layers", str(len(ordered)))])
    regline = " · ".join(f"{k} {v}" for k, v in reg.items())

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HURP Data Catalog</title>
<style>
:root{{--bg:#0e1013;--pan:#16191e;--ink:#e7e3d8;--dim:#9a958a;--line:#2a2e35;--amber:#e0a53d}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
.wrap{{max-width:1120px;margin:0 auto;padding:28px 22px 80px}}
header h1{{font-size:24px;margin:0 0 4px;letter-spacing:-.3px}}
header p{{margin:0;color:var(--dim)}}
.stats{{display:flex;gap:26px;flex-wrap:wrap;margin:22px 0 8px;padding:16px 20px;background:var(--pan);border:1px solid var(--line);border-radius:12px}}
.stat b{{display:block;font-size:22px;color:var(--amber);font-variant-numeric:tabular-nums}}
.stat span{{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
.tools{{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0;margin-top:10px}}
#q{{width:100%;padding:12px 14px;background:var(--pan);border:1px solid var(--line);border-radius:10px;color:var(--ink);font-size:15px;outline:none}}
#q:focus{{border-color:var(--amber)}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
.nav a{{font-size:12px;color:var(--dim);text-decoration:none;padding:3px 9px;border:1px solid var(--line);border-radius:20px}}
.nav a:hover{{color:var(--ink);border-color:var(--amber)}}
.layer{{margin-top:26px}}
.layer h2{{display:flex;justify-content:space-between;align-items:center;font-size:15px;margin:0 0 8px;padding:6px 0 6px 12px;border-left:3px solid;letter-spacing:.2px}}
.layer h2 em{{color:var(--dim);font-style:normal;font-size:12px}}
.col{{display:grid;grid-template-columns:230px 1fr 150px;gap:14px;align-items:start;padding:11px 12px;border-bottom:1px solid var(--line)}}
.col:hover{{background:#12151a}}
.cn{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:var(--ink);word-break:break-all;display:flex;gap:7px;align-items:baseline}}
.dot{{width:7px;height:7px;border-radius:2px;flex:none;display:inline-block}}
.cd{{color:var(--ink);font-size:13px}}
.cs{{grid-column:2;color:var(--dim);font-size:12px;margin-top:2px}}
.cs b{{color:var(--ink);font-variant-numeric:tabular-nums}}
.chip{{display:inline-block;background:#1d2128;border:1px solid var(--line);border-radius:5px;padding:0 6px;margin:2px 3px 0 0;font-size:11px}}
.chip em{{color:var(--amber);font-style:normal}}
.cv{{grid-column:3;grid-row:1/3}}
.cc{{grid-column:3;grid-row:1;display:flex;align-items:center;gap:8px;justify-self:end}}
.bar{{width:96px;height:7px;background:#22262d;border-radius:4px;overflow:hidden}}
.bar i{{display:block;height:100%}}
.cc span{{color:var(--dim);font-size:11px;font-variant-numeric:tabular-nums;width:32px;text-align:right}}
.cv .spark{{margin-top:6px;opacity:.9}}
.hide{{display:none!important}}
footer{{margin-top:40px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);padding-top:16px}}
mark{{background:rgba(224,165,61,.28);color:inherit}}
</style></head><body><div class="wrap">
<header>
  <h1>HURP — Conflict × Agriculture Data Catalog</h1>
  <p>Africa · South America · Caribbean study panel &nbsp;·&nbsp; {regline}</p>
</header>
<div class="stats">{chips}</div>
<div class="tools">
  <input id="q" placeholder="Search {n_cols} columns — name or definition (e.g. cassava, colonial, excluded, temperature)…" autocomplete="off">
  <div class="nav">{"".join(f'<a href="#L{i}">{html.escape(lab)}</a>' for i,(lab,_) in enumerate(ordered))}</div>
</div>
{sections}
<footer>Generated {date.today().isoformat()} from panel_africa_samerica_caribbean_enriched.parquet ({n_rows:,}×{n_cols}). Definitions from docs/CODEBOOK.md. Full detail & every crop: docs/CODEBOOK.md, docs/DATA_SOURCES.md.</footer>
</div>
<script>
const q=document.getElementById('q'), cols=[...document.querySelectorAll('.col')], secs=[...document.querySelectorAll('.layer')];
q.addEventListener('input',()=>{{
  const t=q.value.trim().toLowerCase();
  cols.forEach(c=>{{
    const hit=!t||c.dataset.name.includes(t)||c.dataset.def.includes(t);
    c.classList.toggle('hide',!hit);
  }});
  secs.forEach(s=>{{const any=[...s.querySelectorAll('.col')].some(c=>!c.classList.contains('hide'));s.classList.toggle('hide',!any);}});
}});
</script></body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB) — {n_cols} columns across {len(ordered)} layers")


if __name__ == "__main__":
    main()
