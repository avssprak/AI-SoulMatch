"""Pre-login landing page: brand CSS + marketing sections.

Rendered only on the sign-in screen (app.py). The login card itself stays a
real Streamlit form in app.py; everything here is static HTML/CSS injected
with st.markdown. Palette: ivory / deep maroon / gold / soft saffron.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import billing, config

# V3-4-3: the [HUMAN] logo file — drop it in BOTH assets/ (st.logo/page_icon
# read local paths directly) and static/ (Streamlit's static file server,
# what markdown <img> tags below actually fetch; this repo keeps the two in
# manual sync, see app.py's LOGO_PATH/MARK_PATH). Until it exists, every
# lockup below falls back to a plain text wordmark — never a broken image.
_REDPRANA_LOGO_STATIC_PATH = config.PROJECT_ROOT / "static" / "redprana-logo.svg"


def _redprana_lockup_html(*, light: bool, img_height: str = "22px") -> str:
    """'by RedPrana' wordmark, with the real logo once static/redprana-logo.svg
    exists — checked server-side so a missing file never shows a broken-image
    icon (no reliance on JS onerror)."""
    text_color = "rgba(255,248,238,0.75)" if light else "var(--sm-muted)"
    if _REDPRANA_LOGO_STATIC_PATH.exists():
        return (
            f'<span class="sm-by">by <img src="/app/static/redprana-logo.svg" '
            f'alt="RedPrana" style="height:{img_height}; vertical-align:middle; margin-left:4px;"/></span>'
        )
    return f'<span class="sm-by" style="color:{text_color};">by <b>RedPrana</b></span>'

# One source of truth for the brand palette, referenced throughout the CSS.
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --sm-ivory: #FFFCF7;
    --sm-cream: #F8EFE3;
    --sm-maroon: #5C1630;
    --sm-maroon-2: #7A1E3F;
    --sm-gold: #C9A227;
    --sm-gold-soft: #E8C55B;
    --sm-saffron: #F4A950;
    --sm-ink: #2B2024;
    --sm-muted: #7A6E66;
}

[data-testid="stSidebar"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
img[data-testid="stLogo"] { display: none; }

.stApp { background: var(--sm-ivory); }

/* Hero band: painted on a ::before of .block-container (which scrolls with
   the page, unlike the viewport container) so it stays behind the hero only.
   z-index -1 tucks it beneath every Streamlit element that follows. */
.block-container { position: relative; max-width: 1200px; padding-top: 2.5rem; }
.block-container::before {
    content: "";
    position: absolute;
    top: -3rem;
    left: 50%;
    transform: translateX(-50%);
    width: 100vw;
    height: 880px;
    background:
        linear-gradient(to bottom, rgba(56,10,28,0.82) 0%, rgba(46,10,26,0.86) 70%, var(--sm-ivory) 100%),
        url('https://images.unsplash.com/photo-1529634806980-85c3dd6d34ac?auto=format&fit=crop&w=1800&q=80') center 30% / cover no-repeat;
    z-index: 0;
    pointer-events: none;
}
/* Lift the actual page content above the hero band. */
.block-container > div { position: relative; z-index: 1; }

/* ---------- hero ---------- */
.sm-brand { display: flex; align-items: baseline; gap: 12px; margin: 0 0 40px -6px; }
.sm-brand img.sm-mark { height: 62px; }
.sm-by { font: 500 0.82rem/1 'Inter', sans-serif; }
.sm-by b { color: var(--sm-gold-soft); font-weight: 700; }

/* ---------- privacy promise strip (V3-4-3, above the fold) ---------- */
.sm-privacy-strip {
    display: inline-flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 10px 20px;
    margin-bottom: 26px;
    font: 500 0.88rem/1.4 'Inter', sans-serif;
    color: #FFF8EE;
    backdrop-filter: blur(3px);
    max-width: 560px;
}

/* ---------- pricing table ---------- */
.sm-pricing-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; margin-top: 44px; }
.sm-price-card {
    background: #fff; border: 1px solid #F0E4D2; border-radius: 16px;
    padding: 30px 26px; text-align: left;
    box-shadow: 0 8px 30px rgba(92,22,48,0.05);
}
.sm-price-card.sm-price-highlight {
    border: 2px solid var(--sm-gold);
    box-shadow: 0 16px 44px rgba(201,162,39,0.18);
    position: relative;
}
.sm-price-card.sm-price-highlight::before {
    content: "MOST POPULAR";
    position: absolute; top: -12px; left: 26px;
    background: var(--sm-gold); color: #fff;
    font: 700 0.68rem/1 'Inter', sans-serif; letter-spacing: 0.06em;
    padding: 5px 12px; border-radius: 999px;
}
.sm-price-plan { font: 700 1.1rem/1 'Playfair Display', Georgia, serif; color: var(--sm-maroon); margin-bottom: 10px; }
.sm-price-amount { font: 800 2rem/1 'Inter', sans-serif; color: var(--sm-maroon-2); margin-bottom: 4px; }
.sm-price-amount span { font: 500 0.9rem/1 'Inter', sans-serif; color: var(--sm-muted); }
.sm-price-card ul { list-style: none; padding: 0; margin: 18px 0 0 0; }
.sm-price-card li {
    font: 400 0.9rem/1.6 'Inter', sans-serif; color: var(--sm-ink);
    padding: 6px 0 6px 22px; position: relative;
}
.sm-price-card li::before { content: "✓"; position: absolute; left: 0; color: var(--sm-gold); font-weight: 700; }
div[class*="st-key-landing_currency_toggle"] { max-width: 260px; margin: 0 auto 8px auto; text-align: center; }
div[class*="st-key-landing_currency_toggle"] [data-testid="stRadio"] > div { justify-content: center; }

.sm-eyebrow {
    display: inline-block;
    font: 600 0.8rem/1 'Inter', sans-serif;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--sm-gold-soft);
    border: 1px solid rgba(232,197,91,0.45);
    border-radius: 999px;
    padding: 8px 16px;
    margin-bottom: 22px;
    backdrop-filter: blur(2px);
}
.sm-h1 {
    font: 700 3.1rem/1.18 'Playfair Display', Georgia, serif;
    color: #FFF8EE;
    max-width: 580px;
    margin: 0 0 18px 0;
    text-shadow: 0 2px 18px rgba(0,0,0,0.35);
}
.sm-h1 em { font-style: normal; color: var(--sm-gold-soft); }
.sm-hero-sub {
    font: 400 1.12rem/1.65 'Inter', sans-serif;
    color: rgba(255,248,238,0.9);
    max-width: 520px;
    margin-bottom: 30px;
}
.sm-pills { display: flex; flex-wrap: wrap; gap: 10px; max-width: 560px; }
.sm-pill {
    font: 600 0.82rem/1 'Inter', sans-serif;
    color: #FFF8EE;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.22);
    border-radius: 999px;
    padding: 9px 15px;
    backdrop-filter: blur(3px);
}
.sm-pill b { color: var(--sm-gold-soft); }

/* ---------- login card ---------- */
div[class*="st-key-login_card"] {
    background: rgba(255,252,247,0.96);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    border-top: 4px solid var(--sm-gold);
    padding: 34px 32px 22px 32px;
    box-shadow: 0 24px 70px rgba(30,6,18,0.45);
    max-width: 400px;
    margin-left: auto;
    margin-top: 30px;
}
div[class*="st-key-login_card"] h3 { font-family: 'Playfair Display', Georgia, serif; }

/* ---------- shared section chrome ---------- */
.sm-section { padding: 72px 0 12px 0; }
.sm-kicker {
    font: 700 0.78rem/1 'Inter', sans-serif;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--sm-gold);
    margin-bottom: 12px;
}
.sm-h2 {
    font: 700 2.1rem/1.25 'Playfair Display', Georgia, serif;
    color: var(--sm-maroon);
    margin: 0 0 14px 0;
}
.sm-lead { font: 400 1.05rem/1.7 'Inter', sans-serif; color: var(--sm-muted); max-width: 640px; }
.sm-center { text-align: center; }
.sm-center .sm-lead { margin: 0 auto; }

/* ---------- stats ---------- */
.sm-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; margin-top: 44px; }
.sm-stat {
    background: #fff;
    border: 1px solid #F0E4D2;
    border-radius: 16px;
    padding: 28px 26px;
    box-shadow: 0 8px 30px rgba(92,22,48,0.06);
}
.sm-stat .n { font: 800 2rem/1 'Inter', sans-serif; color: var(--sm-maroon-2); margin-bottom: 8px; }
.sm-stat .n span { color: var(--sm-gold); }
.sm-stat .t { font: 600 0.98rem/1.45 'Inter', sans-serif; color: var(--sm-ink); }
.sm-stat .d { font: 400 0.88rem/1.55 'Inter', sans-serif; color: var(--sm-muted); margin-top: 6px; }

/* ---------- feature cards ---------- */
.sm-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; margin-top: 44px; }
.sm-card {
    background: #fff;
    border: 1px solid #F0E4D2;
    border-radius: 16px;
    padding: 28px 26px;
    box-shadow: 0 8px 30px rgba(92,22,48,0.05);
    transition: transform .18s ease, box-shadow .18s ease;
}
.sm-card:hover { transform: translateY(-4px); box-shadow: 0 16px 44px rgba(92,22,48,0.12); }
.sm-ico {
    width: 46px; height: 46px;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.25rem;
    background: linear-gradient(135deg, #FBF3E2, #F6E7C8);
    border: 1px solid #EEDCB4;
    margin-bottom: 16px;
}
.sm-card h4 { font: 700 1.05rem/1.35 'Inter', sans-serif; color: var(--sm-maroon); margin: 0 0 8px 0; }
.sm-card p { font: 400 0.92rem/1.6 'Inter', sans-serif; color: var(--sm-muted); margin: 0; }

/* ---------- how it works ---------- */
.sm-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 44px; }
.sm-step { position: relative; background: #fff; border: 1px solid #F0E4D2; border-radius: 16px; padding: 26px 22px; }
.sm-step .num {
    width: 38px; height: 38px; border-radius: 50%;
    background: linear-gradient(135deg, var(--sm-gold-soft), var(--sm-gold));
    color: #4A1226;
    font: 800 1rem/38px 'Inter', sans-serif;
    text-align: center;
    margin-bottom: 14px;
}
.sm-step h4 { font: 700 1rem/1.3 'Inter', sans-serif; color: var(--sm-maroon); margin: 0 0 6px 0; }
.sm-step p { font: 400 0.88rem/1.55 'Inter', sans-serif; color: var(--sm-muted); margin: 0; }

/* ---------- split (AI + Vedic) ---------- */
.sm-split { display: grid; grid-template-columns: 1.05fr 1fr; gap: 44px; align-items: center; margin-top: 44px; }
.sm-split img { width: 100%; border-radius: 18px; box-shadow: 0 18px 50px rgba(92,22,48,0.18); display: block; }
.sm-checks { list-style: none; padding: 0; margin: 20px 0 0 0; }
.sm-checks li {
    font: 500 0.98rem/1.5 'Inter', sans-serif;
    color: var(--sm-ink);
    padding: 10px 0 10px 34px;
    position: relative;
    border-bottom: 1px dashed #EFE3D0;
}
.sm-checks li::before {
    content: "✦";
    position: absolute; left: 6px;
    color: var(--sm-gold);
    font-size: 1rem;
}

/* ---------- dashboard mock ---------- */
.sm-mock {
    margin: 44px auto 0 auto;
    max-width: 880px;
    background: #fff;
    border-radius: 18px;
    border: 1px solid #F0E4D2;
    box-shadow: 0 30px 80px rgba(92,22,48,0.16);
    overflow: hidden;
}
.sm-mock .bar { display: flex; gap: 7px; padding: 13px 18px; background: var(--sm-maroon); }
.sm-mock .bar i { width: 11px; height: 11px; border-radius: 50%; display: block; }
.sm-mock .body { padding: 26px; }
.sm-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
.sm-kpi { background: var(--sm-cream); border-radius: 12px; padding: 16px; }
.sm-kpi .v { font: 800 1.4rem/1 'Inter', sans-serif; color: var(--sm-maroon-2); }
.sm-kpi .l { font: 600 0.72rem/1.3 'Inter', sans-serif; color: var(--sm-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-top: 6px; }
.sm-bars { display: flex; align-items: flex-end; gap: 12px; height: 120px; padding: 0 6px; }
.sm-bars i { flex: 1; border-radius: 6px 6px 0 0; background: linear-gradient(to top, var(--sm-maroon-2), #A8477020); display: block; }
.sm-bars i:nth-child(2n) { background: linear-gradient(to top, var(--sm-gold), #E8C55B30); }

/* ---------- testimonials ---------- */
.sm-quotes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; margin-top: 44px; }
.sm-quote { background: #fff; border: 1px solid #F0E4D2; border-radius: 16px; padding: 26px; }
.sm-quote p { font: 400 0.95rem/1.65 'Inter', sans-serif; color: var(--sm-ink); font-style: italic; margin: 0 0 18px 0; }
.sm-quote .who { display: flex; align-items: center; gap: 12px; }
.sm-quote .av {
    width: 40px; height: 40px; border-radius: 50%;
    background: linear-gradient(135deg, var(--sm-maroon-2), var(--sm-maroon));
    color: var(--sm-gold-soft);
    font: 700 0.9rem/40px 'Inter', sans-serif;
    text-align: center;
}
.sm-quote .nm { font: 700 0.9rem/1.2 'Inter', sans-serif; color: var(--sm-ink); }
.sm-quote .rl { font: 400 0.8rem/1.3 'Inter', sans-serif; color: var(--sm-muted); }

/* ---------- CTA ---------- */
.sm-cta {
    margin-top: 80px;
    background: linear-gradient(135deg, var(--sm-maroon) 0%, #3D0E22 100%);
    border-radius: 22px;
    padding: 60px 48px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.sm-cta::before {
    content: "";
    position: absolute; inset: 0;
    background: radial-gradient(600px 200px at 50% -40px, rgba(201,162,39,0.25), transparent);
}
.sm-cta h2 { font: 700 2rem/1.3 'Playfair Display', Georgia, serif; color: #FFF8EE; margin: 0 0 12px 0; position: relative; }
.sm-cta p { font: 400 1rem/1.6 'Inter', sans-serif; color: rgba(255,248,238,0.85); margin: 0 0 26px 0; position: relative; }
.sm-cta a {
    display: inline-block;
    background: linear-gradient(135deg, var(--sm-gold-soft), var(--sm-gold));
    color: #3D0E22 !important;
    font: 700 1rem/1 'Inter', sans-serif;
    padding: 15px 34px;
    border-radius: 999px;
    text-decoration: none !important;
    box-shadow: 0 10px 30px rgba(201,162,39,0.4);
    position: relative;
    transition: transform .15s ease;
}
.sm-cta a:hover { transform: translateY(-2px); }

/* ---------- footer ---------- */
.sm-footer {
    margin-top: 60px;
    border-top: 1px solid #EFE3D0;
    padding: 38px 6px 20px 6px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 30px;
    flex-wrap: wrap;
}
.sm-footer img { height: 40px; margin-bottom: 10px; }
.sm-footer .tag { font: 400 0.86rem/1.5 'Inter', sans-serif; color: var(--sm-muted); max-width: 320px; }
.sm-footer .col h5 { font: 700 0.8rem/1 'Inter', sans-serif; letter-spacing: 0.1em; text-transform: uppercase; color: var(--sm-maroon); margin: 0 0 12px 0; }
.sm-footer .col div { font: 400 0.88rem/2 'Inter', sans-serif; color: var(--sm-muted); }
.sm-copy { text-align: center; font: 400 0.8rem/1.5 'Inter', sans-serif; color: #B4A79B; padding: 18px 0 6px 0; border-top: 1px solid #F4EBDD; margin-top: 26px; }

/* ---------- responsive ---------- */
@media (max-width: 1000px) {
    .sm-h1 { font-size: 2.2rem; }
    .sm-stats, .sm-grid, .sm-quotes { grid-template-columns: 1fr 1fr; }
    .sm-steps { grid-template-columns: 1fr 1fr; }
    .sm-split { grid-template-columns: 1fr; }
    div[class*="st-key-login_card"] { margin: 20px auto; }
}
@media (max-width: 640px) {
    .sm-h1 { font-size: 1.8rem; }
    .sm-stats, .sm-grid, .sm-quotes, .sm-steps, .sm-kpis { grid-template-columns: 1fr; }
    .sm-cta { padding: 44px 24px; }
    .block-container::before { height: 1150px; }
}
</style>
"""

def _hero_html() -> str:
    return f"""
<div class="sm-brand"><img class="sm-mark" src="/app/static/logo-white.svg" alt="SoulMatch"/>{_redprana_lockup_html(light=True)}</div>
<div class="sm-eyebrow">The Private CRM for Your Child's Marriage Search</div>
<div class="sm-h1">Find your son or daughter's <em>soul match</em> — the organized way.</div>
<div class="sm-hero-sub">
  SoulMatch helps parents manage their child's marriage search: the biodatas
  arriving on WhatsApp become clean, comparable profiles — scored on practical
  fit and Vedic compatibility, and tracked from first phone call to wedding day.
</div>
<div class="sm-privacy-strip">🔒 Your data is yours. Private by default. No public profiles, ever.</div>
<div class="sm-pills">
  <div class="sm-pill"><b>⚡</b> AI profile extraction</div>
  <div class="sm-pill"><b>♥</b> Intelligent matching</div>
  <div class="sm-pill"><b>ॐ</b> Vedic compatibility</div>
  <div class="sm-pill"><b>🔒</b> Private &amp; secure</div>
</div>
"""

_SECTIONS_HTML = """
<div class="sm-section sm-center">
  <div class="sm-kicker">Platform Overview</div>
  <div class="sm-h2">Built for parents, powered by AI</div>
  <div class="sm-lead">Everything a family needs to run their son or daughter's marriage
  search — importing biodatas, comparing matches, horoscope compatibility, and
  follow-ups — in one private workspace.</div>
  <div class="sm-stats">
    <div class="sm-stat"><div class="n">&lt;1<span> min</span></div>
      <div class="t">From chat export to structured profile</div>
      <div class="d">Paste a WhatsApp conversation or upload a biodata PDF — AI does the rest.</div></div>
    <div class="sm-stat"><div class="n">36<span> gunas</span></div>
      <div class="t">Full Ashtakoota horoscope scoring</div>
      <div class="d">Traditional koota matching computed precisely from birth details.</div></div>
    <div class="sm-stat"><div class="n">100<span>%</span></div>
      <div class="t">Your family's data stays yours</div>
      <div class="d">Private by default — only you see your child's search. No public profiles, ever.</div></div>
  </div>
</div>

<div class="sm-section sm-center">
  <div class="sm-kicker">Key Features</div>
  <div class="sm-h2">Everything between “hello” and “congratulations”</div>
  <div class="sm-grid">
    <div class="sm-card"><div class="sm-ico">📥</div>
      <h4>AI Profile Extraction</h4>
      <p>Import from WhatsApp chats, PDFs, and biodata documents. AI reads unstructured
      text and builds clean, complete profiles — education, family, horoscope details and more.</p></div>
    <div class="sm-card"><div class="sm-ico">💘</div>
      <h4>Intelligent Matchmaking</h4>
      <p>Configurable criteria — age, community, education, location, preferences — ranked
      and scored so the strongest candidates surface first.</p></div>
    <div class="sm-card"><div class="sm-ico">🔯</div>
      <h4>Vedic Compatibility</h4>
      <p>Ashtakoota guna matching with Telugu astrology names, computed from birth date,
      time, and place using precise ephemeris calculations.</p></div>
    <div class="sm-card"><div class="sm-ico">📋</div>
      <h4>Pipeline &amp; Progress Tracking</h4>
      <p>Every introduction moves through a clear pipeline — screening, outreach, meetings,
      outcome — with tasks and reminders so nothing slips.</p></div>
    <div class="sm-card"><div class="sm-ico">🔍</div>
      <h4>Search &amp; Insights</h4>
      <p>Ask questions in plain language — “software engineers in Hyderabad under 30” —
      and get instant answers and quick insights across your entire database.</p></div>
    <div class="sm-card"><div class="sm-ico">🛡️</div>
      <h4>Secure &amp; Private</h4>
      <p>User accounts with role-based access, session security, and full data ownership.
      Sensitive family information never leaves your control.</p></div>
  </div>
</div>

<div class="sm-section sm-center">
  <div class="sm-kicker">How It Works</div>
  <div class="sm-h2">Four steps from raw chat to right match</div>
  <div class="sm-steps">
    <div class="sm-step"><div class="num">1</div><h4>Import</h4>
      <p>Drop in WhatsApp exports, PDFs, or biodata files — individually or in bulk.</p></div>
    <div class="sm-step"><div class="num">2</div><h4>Extract</h4>
      <p>AI structures every detail into a rich profile and flags duplicates automatically.</p></div>
    <div class="sm-step"><div class="num">3</div><h4>Match</h4>
      <p>Score candidates on your criteria plus horoscope compatibility, ranked instantly.</p></div>
    <div class="sm-step"><div class="num">4</div><h4>Track</h4>
      <p>Manage introductions through the pipeline with tasks, notes, and reminders.</p></div>
  </div>
</div>

<div class="sm-section">
  <div class="sm-split">
    <div>
      <div class="sm-kicker">AI + Vedic Astrology</div>
      <div class="sm-h2">Modern intelligence, timeless wisdom</div>
      <div class="sm-lead">Every family wants both: a practical fit and an auspicious one.
      SoulMatch is the rare platform that treats Vedic astrology as a first-class
      signal alongside practical matching — because that's how your family actually decides.</div>
      <ul class="sm-checks">
        <li>Ashtakoota (36-guna) compatibility computed from precise birth charts</li>
        <li>Telugu naming for rasi, nakshatra, and koota — familiar to your elders</li>
        <li>Horoscope score blended with practical criteria in one ranked view</li>
        <li>Manual overrides when the astrologer’s judgment should prevail</li>
      </ul>
    </div>
    <img src="https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=900&q=80"
         alt="Wedding celebration" onerror="this.style.display='none'"/>
  </div>
</div>

<div class="sm-section sm-center">
  <div class="sm-kicker">Dashboard Preview</div>
  <div class="sm-h2">Your child's entire search, at a glance</div>
  <div class="sm-lead">Every proposal in play, follow-ups due, new biodatas waiting, and
  match activity — the first screen you see with your morning coffee.</div>
  <div class="sm-mock">
    <div class="bar"><i style="background:#E8626F"></i><i style="background:#E8C55B"></i><i style="background:#7BC47F"></i></div>
    <div class="body">
      <div class="sm-kpis">
        <div class="sm-kpi"><div class="v">248</div><div class="l">Active Profiles</div></div>
        <div class="sm-kpi"><div class="v">37</div><div class="l">In Outreach</div></div>
        <div class="sm-kpi"><div class="v">12</div><div class="l">Meetings Set</div></div>
        <div class="sm-kpi"><div class="v">5</div><div class="l">Engagements</div></div>
      </div>
      <div class="sm-bars">
        <i style="height:45%"></i><i style="height:70%"></i><i style="height:55%"></i><i style="height:85%"></i>
        <i style="height:60%"></i><i style="height:95%"></i><i style="height:75%"></i><i style="height:88%"></i>
      </div>
    </div>
  </div>
</div>

<div class="sm-section sm-center">
  <div class="sm-kicker">Testimonials</div>
  <div class="sm-h2">Trusted by parents like you</div>
  <div class="sm-quotes">
    <div class="sm-quote">
      <p>“Every biodata that arrived on WhatsApp for my daughter used to get lost in the
      scroll. Now each one becomes a proper profile in minutes, and I can finally compare
      proposals side by side instead of from memory.”</p>
      <div class="who"><div class="av">LP</div>
        <div><div class="nm">Lakshmi P.</div><div class="rl">Mother of the bride · Hyderabad</div></div></div>
    </div>
    <div class="sm-quote">
      <p>“Managing my son's search from New Jersey while the proposals came to my brother
      in Vijayawada was chaos. Now the whole family sees the same profiles, notes, and
      horoscope scores — nothing gets lost between calls to India.”</p>
      <div class="who"><div class="av">VR</div>
        <div><div class="nm">Venkat R.</div><div class="rl">Father of the groom · New Jersey, USA</div></div></div>
    </div>
    <div class="sm-quote">
      <p>“The koota score with Telugu names is what my grandmother trusts — and the
      follow-up reminders are what I trust. Between us, no proposal for my brother
      slips through anymore.”</p>
      <div class="who"><div class="av">AK</div>
        <div><div class="nm">Anitha K.</div><div class="rl">Managing her brother's search · Bengaluru</div></div></div>
    </div>
  </div>
</div>
"""

_CTA_FOOTER_HTML = f"""
<div class="sm-cta">
  <h2>Ready to find your child's soul match?</h2>
  <p>Create your free private workspace — let AI organize the biodatas while you focus on your family.</p>
  <a href="#ai-soulmatch-top">Start free with SoulMatch</a>
</div>

<div class="sm-footer">
  <div class="col">
    <img src="/app/static/logo.svg" alt="SoulMatch"/>
    <div class="tag">The private CRM for parents managing their son or daughter's marriage
    search — AI profile extraction, intelligent matching, and Vedic compatibility in one
    private workspace. A product of RedPrana.</div>
  </div>
  <div class="col"><h5>Platform</h5>
    <div>Profile Import<br/>Matchmaking<br/>Horoscope Check<br/>Search &amp; Insights</div></div>
  <div class="col"><h5>Workflow</h5>
    <div>Dashboard<br/>Pipeline Tracking<br/>Tasks &amp; Reminders<br/>My Plan</div></div>
  <div class="col"><h5>Trust</h5>
    <div>Private by default<br/>No public profiles, ever<br/>Your data, always<br/>&nbsp;</div></div>
</div>
<div class="sm-copy">© 2026 SoulMatch {_redprana_lockup_html(light=False)} · Crafted with care for families</div>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_hero_left() -> None:
    st.markdown(_hero_html(), unsafe_allow_html=True)


def _pricing_cards_html(currency: str) -> str:
    """Pricing cards sourced from soulmatch.billing (PLAN_PRICES_INR/USD,
    PLAN_LIMITS) so this can never drift from what's actually enforced
    (V3-4-3).

    Every line of generated HTML MUST be flush-left: st.markdown treats any
    line indented 4+ spaces as a Markdown code block, which renders the raw
    tags as text instead of a card (bug found live on the landing page)."""
    symbol = "₹" if currency == "INR" else "$"
    price_table = billing.PLAN_PRICES_INR if currency == "INR" else billing.PLAN_PRICES_USD
    cards = []
    for plan_key, label in (("free", "Free"), ("plus", "Plus"), ("pro", "Pro")):
        limits = billing.limits_for(plan_key)
        price = price_table[plan_key]
        price_html = f"{symbol}{price}<span>/mo</span>" if price else "Free"
        highlight = " sm-price-highlight" if plan_key == "plus" else ""
        bulk = limits["bulk_imports"]
        items = [
            f"{limits['ai_actions']} AI actions/mo",
            "Unlimited profiles" if limits["profiles"] is None else f"{limits['profiles']} profiles",
            "AI match explanations" if limits["ai_explanations"] else "Koota scores (always free)",
            "Natural-language search" if limits["nl_search"] else "Structured filters",
            "Unlimited bulk imports" if bulk is None else f"{bulk} bulk import(s)/mo" if bulk else "Manual import only",
        ]
        items_html = "".join(f"<li>{item}</li>" for item in items)
        cards.append(
            f'<div class="sm-price-card{highlight}">'
            f'<div class="sm-price-plan">{label}</div>'
            f'<div class="sm-price-amount">{price_html}</div>'
            f"<ul>{items_html}</ul>"
            "</div>"
        )
    return "".join(cards)


_PRICING_HEADER_HTML = """
<div class="sm-section sm-center" style="padding-bottom:0;">
<div class="sm-kicker">Pricing</div>
<div class="sm-h2">Simple plans, no surprises</div>
<div class="sm-lead">Start free — upgrade only when your child's search needs more.
Living abroad? Pay in USD for the same plans.</div>
</div>
"""


def render_sections() -> None:
    st.markdown(_SECTIONS_HTML, unsafe_allow_html=True)
    # Pricing header first, THEN the currency toggle, then the cards — the
    # toggle floating above the section heading read as if it belonged to
    # the testimonials above it.
    st.markdown(_PRICING_HEADER_HTML, unsafe_allow_html=True)
    with st.container(key="landing_currency_toggle"):
        currency = st.radio(
            "Currency", ["INR", "USD"], horizontal=True, label_visibility="collapsed",
            help="Choose USD if you're paying from outside India (NRI).", key="landing_currency",
        )
    st.markdown(
        f'<div class="sm-center"><div class="sm-pricing-grid">{_pricing_cards_html(currency)}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(_CTA_FOOTER_HTML, unsafe_allow_html=True)
