"""Central design system for every authenticated (inner) page.

The pre-login landing page (soulmatch/landing.py) established the brand:
ivory / deep maroon / gold / soft saffron, Playfair Display headings, Inter
body. This module carries that same language into the app shell so every
page inherits it automatically:

- ``apply()``      — inject the app-wide CSS. Called once in app.py before
                     st.navigation runs, so individual pages never need to.
- ``page_header``  — branded page title block (kicker / Playfair title /
                     subtitle + gold rule). Replaces st.title on every page.
- ``section``      — branded section heading. Replaces st.subheader.
- ``empty_state``  — friendly branded placeholder for "nothing here yet".
- Plotly template  — a "soulmatch" template registered at import time;
                     ``brand_chart(fig)`` applies it plus transparent bg.

Palette values are duplicated from landing.py deliberately: the landing CSS
is scoped to the marketing page (it hides the sidebar), while this is the
product chrome. Both read from the same named constants below.
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---- brand palette (single source of truth for the app shell) -------------
IVORY = "#FFFCF7"
CREAM = "#F8EFE3"
MAROON = "#5C1630"
MAROON_2 = "#7A1E3F"
MAROON_3 = "#A8476F"
GOLD = "#C9A227"
GOLD_SOFT = "#E8C55B"
SAFFRON = "#F4A950"
INK = "#2B2024"
MUTED = "#7A6E66"
LINE = "#F0E4D2"

# Single-hue maroon ramp for charts (gold fails 3:1 contrast on ivory, so it
# is an accent, never a data color — validated with the dataviz palette tool).
CHART_SEQUENCE = [MAROON_2, MAROON_3, "#C77E9B", "#DFAEC2"]

# Two-series categorical pair for Bride-vs-Groom charts: rose-maroon + bronze.
# Passes all palette checks (lightness band, chroma, CVD ΔE 28+, 3:1 contrast)
# on the ivory surface — bright gold does not, hence the darker bronze.
BRIDE_COLOR = "#A8476F"
GROOM_COLOR = "#8A6D1B"

# V5-5-2: self-hosted variable fonts (static/fonts/, OFL licenses alongside)
# instead of a render-blocking Google Fonts @import that fails offline.
FONT_FACE_CSS = """
@font-face { font-family: 'Inter'; font-style: normal; font-weight: 400 800;
    font-display: swap; src: url('/app/static/fonts/Inter-var.woff2') format('woff2'); }
@font-face { font-family: 'Playfair Display'; font-style: normal; font-weight: 600 800;
    font-display: swap; src: url('/app/static/fonts/PlayfairDisplay-var.woff2') format('woff2'); }
"""

_CSS = f"""
<style>
{FONT_FACE_CSS}

:root {{
    --sm-ivory: {IVORY};
    --sm-cream: {CREAM};
    --sm-maroon: {MAROON};
    --sm-maroon-2: {MAROON_2};
    --sm-gold: {GOLD};
    --sm-gold-soft: {GOLD_SOFT};
    --sm-ink: {INK};
    --sm-muted: {MUTED};
    --sm-line: {LINE};
}}

.stApp {{ background: var(--sm-ivory); }}
html, body, [class*="css"], .stApp {{ font-family: 'Inter', sans-serif; }}

/* ---------- header bar ---------- */
[data-testid="stHeader"] {{
    background: rgba(255,252,247,0.85);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid var(--sm-line);
}}

/* ---------- sidebar: deep maroon, gold accents ---------- */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, var(--sm-maroon) 0%, #3D0E22 100%);
    border-right: 1px solid rgba(201,162,39,0.25);
}}
[data-testid="stSidebar"] * {{ color: #FFF3E4; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: #FFF3E4; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {{
    color: rgba(255,243,228,0.65);
}}
[data-testid="stSidebar"] a span {{ color: rgba(255,243,228,0.88) !important; }}
/* material line icons in the nav render in brand gold */
[data-testid="stSidebar"] a [data-testid="stIconMaterial"] {{
    color: var(--sm-gold-soft) !important;
    font-size: 1.15rem;
}}
[data-testid="stSidebar"] a:hover {{ background: rgba(255,255,255,0.08); border-radius: 10px; }}
[data-testid="stSidebar"] a[aria-current="page"] {{
    background: rgba(201,162,39,0.18);
    border-radius: 10px;
}}
[data-testid="stSidebar"] a[aria-current="page"] span {{
    color: var(--sm-gold-soft) !important;
    font-weight: 700;
}}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.15); }}
/* !important: the generic button-kind rules further down otherwise tie on
   specificity and win by source order, painting these white-on-white. */
[data-testid="stSidebar"] .stButton button,
[data-testid="stSidebar"] .stFormSubmitButton button {{
    background: rgba(255,255,255,0.06) !important;
    color: #FFF3E4 !important;
    border: 1px solid rgba(255,243,228,0.35) !important;
    border-radius: 10px;
}}
[data-testid="stSidebar"] .stButton button p,
[data-testid="stSidebar"] .stFormSubmitButton button p {{ color: #FFF3E4 !important; }}
[data-testid="stSidebar"] .stButton button:hover,
[data-testid="stSidebar"] .stFormSubmitButton button:hover {{
    border-color: var(--sm-gold-soft) !important;
    color: var(--sm-gold-soft) !important;
}}
[data-testid="stSidebar"] .stButton button:hover p,
[data-testid="stSidebar"] .stFormSubmitButton button:hover p {{ color: var(--sm-gold-soft) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 12px;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{ color: var(--sm-gold-soft); }}
[data-testid="stSidebar"] [data-testid="stForm"] {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: none;
}}
[data-testid="stSidebar"] input {{ color: var(--sm-ink) !important; }}
[data-testid="stSidebar"] input::placeholder {{ color: var(--sm-muted) !important; }}
img[data-testid="stLogo"] {{ height: 46px !important; }}

/* ---------- typography ---------- */
h1, h2, h3 {{ font-family: 'Playfair Display', Georgia, serif !important; color: var(--sm-maroon) !important; }}
h4, h5, h6 {{ font-family: 'Inter', sans-serif !important; color: var(--sm-maroon) !important; }}
/* Streamlit's fixed header bar is ~3.75rem tall; content scrolls under it,
   so the container needs enough top padding to clear it. !important because
   Streamlit ships its own .block-container padding rule. */
.block-container,
[data-testid="stMainBlockContainer"] {{ padding-top: 5rem !important; max-width: 1200px; }}

/* branded page header */
.sm-page-kicker {{
    font: 700 0.72rem/1 'Inter', sans-serif;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--sm-gold);
    margin-bottom: 8px;
}}
.sm-page-title {{
    font: 700 2.15rem/1.2 'Playfair Display', Georgia, serif;
    color: var(--sm-maroon);
    margin: 0;
}}
.sm-page-sub {{
    font: 400 0.98rem/1.6 'Inter', sans-serif;
    color: var(--sm-muted);
    margin: 8px 0 0 0;
    max-width: 720px;
}}
.sm-page-rule {{
    width: 64px; height: 3px; border-radius: 2px;
    background: linear-gradient(90deg, var(--sm-gold-soft), var(--sm-gold));
    margin: 16px 0 6px 0;
}}

/* branded section heading */
.sm-sec {{ display: flex; align-items: baseline; gap: 10px; margin: 10px 0 2px 0; }}
.sm-sec .tick {{ width: 10px; height: 10px; border-radius: 3px; background: linear-gradient(135deg, var(--sm-gold-soft), var(--sm-gold)); align-self: center; }}
.sm-sec h3 {{ font: 700 1.25rem/1.3 'Playfair Display', Georgia, serif; color: var(--sm-maroon); margin: 0; }}
.sm-sec-cap {{ font: 400 0.9rem/1.5 'Inter', sans-serif; color: var(--sm-muted); margin: 4px 0 8px 20px; }}

/* ---------- metrics as brand cards ---------- */
[data-testid="stMetric"] {{
    background: #fff;
    border: 1px solid var(--sm-line);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 6px 22px rgba(92,22,48,0.05);
}}
[data-testid="stMetric"] [data-testid="stMetricLabel"] p {{
    font: 600 0.74rem/1.3 'Inter', sans-serif !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--sm-muted) !important;
}}
[data-testid="stMetricValue"] {{
    font-family: 'Inter', sans-serif !important;
    font-weight: 800 !important;
    color: var(--sm-maroon-2) !important;
}}

/* ---------- buttons ---------- */
.stButton button, .stFormSubmitButton button, .stDownloadButton button, .stLinkButton a {{
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    transition: transform .12s ease, box-shadow .12s ease;
}}
.stButton button:hover, .stFormSubmitButton button:hover {{ transform: translateY(-1px); }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
    background: linear-gradient(135deg, var(--sm-maroon-2), var(--sm-maroon));
    border: none;
    box-shadow: 0 6px 18px rgba(92,22,48,0.28);
}}
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {{
    box-shadow: 0 10px 24px rgba(92,22,48,0.36);
}}
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"] {{
    background: #fff;
    border: 1px solid #E4D3B8;
    color: var(--sm-maroon-2);
}}
.stButton button[kind="secondary"]:hover {{
    border-color: var(--sm-gold);
    color: var(--sm-maroon);
}}

/* ---------- containers: expanders, forms, dialogs, popovers ---------- */
[data-testid="stExpander"] {{
    background: #fff;
    border: 1px solid var(--sm-line) !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 16px rgba(92,22,48,0.04);
}}
[data-testid="stForm"] {{
    background: #fff;
    border: 1px solid var(--sm-line);
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(92,22,48,0.04);
}}
div[role="dialog"] {{ border-radius: 16px; border-top: 4px solid var(--sm-gold); }}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid var(--sm-line); }}
.stTabs [data-baseweb="tab"] {{
    font: 600 0.92rem/1 'Inter', sans-serif;
    color: var(--sm-muted);
    border-radius: 10px 10px 0 0;
    padding: 10px 14px;
}}
.stTabs [aria-selected="true"] {{ color: var(--sm-maroon) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--sm-gold) !important; height: 3px; border-radius: 2px; }}

/* ---------- dataframes / tables ---------- */
[data-testid="stDataFrame"] {{
    border: 1px solid var(--sm-line);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(92,22,48,0.04);
}}

/* ---------- inputs ---------- */
[data-baseweb="input"], [data-baseweb="select"] > div, .stTextArea textarea {{
    border-radius: 10px !important;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {{
    border-color: var(--sm-maroon-2) !important;
}}

/* ---------- alerts ---------- */
[data-testid="stAlert"] {{ border-radius: 12px; }}

/* ---------- misc chrome ---------- */
hr {{ border: none; border-top: 1px dashed #EBDCC5; margin: 1.6rem 0; }}
[data-testid="stCaptionContainer"] {{ color: var(--sm-muted); }}
[data-testid="stProgress"] > div > div {{
    background: linear-gradient(90deg, var(--sm-gold-soft), var(--sm-gold)) !important;
}}

/* journey stepper (V4-2-2) — horizontal progress strip on the Dashboard */
.sm-stepper {{
    display: flex;
    align-items: stretch;
    gap: 10px;
    margin: 4px 0 18px 0;
}}
.sm-step {{
    flex: 1 1 0;
    display: flex;
    align-items: center;
    gap: 10px;
    background: #fff;
    border: 1px solid var(--sm-line);
    border-radius: 12px;
    padding: 12px 14px;
    box-shadow: 0 4px 16px rgba(92,22,48,0.04);
}}
.sm-step.done {{ border-color: #D9C79A; background: #FFFDF9; }}
.sm-step.current {{ border-color: var(--sm-gold); box-shadow: 0 6px 20px rgba(201,162,39,0.18); }}
.sm-step .badge {{
    flex: 0 0 auto;
    width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font: 700 0.85rem/1 'Inter', sans-serif;
}}
.sm-step.done .badge {{ background: var(--sm-gold); color: #fff; }}
.sm-step.current .badge {{ background: var(--sm-maroon-2); color: #fff; }}
.sm-step.todo .badge {{ background: var(--sm-cream); color: var(--sm-muted); border: 1px solid var(--sm-line); }}
.sm-step .label {{ font: 700 0.85rem/1.3 'Inter', sans-serif; color: var(--sm-ink); }}
.sm-step.todo .label {{ color: var(--sm-muted); }}

/* ---------- mobile (V5-3-1) ----------
   The landing page has its own breakpoints in landing.py; this covers the
   authenticated app shell. 640px ~ phones, 1000px ~ small tablets. */
@media (max-width: 1000px) {{
    .block-container,
    [data-testid="stMainBlockContainer"] {{ padding-left: 1.2rem !important; padding-right: 1.2rem !important; }}
}}
@media (max-width: 640px) {{
    .block-container,
    [data-testid="stMainBlockContainer"] {{
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
        padding-top: 4.2rem !important;
    }}
    .sm-page-title {{ font-size: 1.6rem; }}
    .sm-page-sub {{ font-size: 0.92rem; }}
    /* stepper: 4-across squeezes to unreadable slivers — wrap into a 2x2 grid */
    .sm-stepper {{ flex-wrap: wrap; }}
    .sm-step {{ flex: 1 1 45%; padding: 10px 12px; }}
    .sm-step .label {{ font-size: 0.8rem; }}
    [data-testid="stMetric"] {{ padding: 12px 14px; }}
    .sm-empty {{ padding: 24px 16px; }}
    /* Streamlit stacks columns full-width on phones; buttons that shared a
       row with text (Dashboard "Go" actions) otherwise render as tiny
       left-aligned stubs under it. */
    .stButton button, .stFormSubmitButton button, .stDownloadButton button {{ width: 100%; }}
    .stTabs [data-baseweb="tab"] {{ padding: 8px 10px; font-size: 0.85rem; }}
}}

/* branded empty state */
.sm-empty {{
    text-align: center;
    background: #fff;
    border: 1px dashed #E4D3B8;
    border-radius: 16px;
    padding: 40px 28px;
    margin: 10px 0;
}}
.sm-empty .ico {{ font-size: 1.9rem; margin-bottom: 10px; }}
.sm-empty .t {{ font: 700 1.05rem/1.4 'Playfair Display', Georgia, serif; color: var(--sm-maroon); }}
.sm-empty .h {{ font: 400 0.9rem/1.6 'Inter', sans-serif; color: var(--sm-muted); margin-top: 6px; }}
</style>
"""


def apply() -> None:
    """Inject the app-wide brand CSS. Call once per run, before pages render."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str | None = None, kicker: str = "AI-SoulMatch") -> None:
    """Branded page title block — use instead of st.title on every page."""
    sub = f'<p class="sm-page-sub">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="sm-page-kicker">{kicker}</div>'
        f'<h1 class="sm-page-title">{title}</h1>{sub}'
        f'<div class="sm-page-rule"></div>',
        unsafe_allow_html=True,
    )


def section(title: str, caption: str | None = None) -> None:
    """Branded section heading — use instead of st.subheader."""
    st.markdown(
        f'<div class="sm-sec"><span class="tick"></span><h3>{title}</h3></div>',
        unsafe_allow_html=True,
    )
    if caption:
        st.markdown(f'<div class="sm-sec-cap">{caption}</div>', unsafe_allow_html=True)


def journey_stepper(steps: list[tuple[bool, str]]) -> None:
    """V4-2-2: horizontal 4-step progress strip for the Dashboard — one entry
    per (done, label). The first not-done step is marked "current"; every
    step after it is "todo". All-done renders every step as "done" (no
    current highlight needed once the journey is complete)."""
    current_index = next((i for i, (done, _) in enumerate(steps) if not done), None)
    html = ['<div class="sm-stepper">']
    for i, (done, label) in enumerate(steps):
        if done:
            state, badge = "done", "✓"
        elif i == current_index:
            state, badge = "current", str(i + 1)
        else:
            state, badge = "todo", str(i + 1)
        html.append(
            f'<div class="sm-step {state}"><span class="badge">{badge}</span>'
            f'<span class="label">{label}</span></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def help_link(anchor: str, label: str = "❓ How does this work?") -> None:
    """V5-2-2: a small caption-style link to the Guide page that auto-expands
    the given section (see soulmatch/guide_content.py for valid anchors).
    Use on any page whose flow benefits from a "why"/"how" explanation
    without cluttering the page itself with paragraphs of copy."""
    from soulmatch.nav import GUIDE_PAGE  # local import: avoids a nav<->theme cycle

    if st.button(label, key=f"_help_link_{anchor}", type="tertiary"):
        st.session_state["guide_anchor"] = anchor
        st.switch_page(GUIDE_PAGE)


def empty_state(title: str, hint: str = "", icon: str = "✦") -> None:
    """Friendly branded placeholder for empty lists/tables."""
    st.markdown(
        f'<div class="sm-empty"><div class="ico">{icon}</div>'
        f'<div class="t">{title}</div><div class="h">{hint}</div></div>',
        unsafe_allow_html=True,
    )


# ---- plotly brand template -------------------------------------------------
pio.templates["soulmatch"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, sans-serif", color=INK, size=13),
        title_font=dict(family="Playfair Display, Georgia, serif", color=MAROON, size=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=CHART_SEQUENCE,
        xaxis=dict(gridcolor="#F1E7D7", zerolinecolor="#E8DAC3", linecolor="#E8DAC3"),
        yaxis=dict(gridcolor="#F1E7D7", zerolinecolor="#E8DAC3", linecolor="#E8DAC3"),
        margin=dict(t=30, r=10, b=40, l=40),
        hoverlabel=dict(
            bgcolor="#fff", bordercolor=LINE,
            font=dict(family="Inter, sans-serif", color=INK),
        ),
    )
)


# plotly.express resolves colors at figure creation, not at render — a template
# applied afterwards restyles axes/fonts but NOT trace colors. Making the brand
# template and colorway the px defaults (theme is imported before any page runs)
# is what actually turns the bars maroon.
px.defaults.template = "soulmatch"
px.defaults.color_discrete_sequence = CHART_SEQUENCE


def brand_chart(fig: go.Figure) -> go.Figure:
    """Apply the brand template to a plotly figure. Returns the figure."""
    fig.update_layout(template="soulmatch")
    return fig
