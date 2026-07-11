"""Parent-facing printable profile summary — the first genuinely
family-shareable output the app produces. Deliberately excludes internal
CRM fields (stage, notes, IDs, phone/whatsapp/email) that aren't a family's
business and would look unprofessional in front of them.
"""

from __future__ import annotations

import base64
from html import escape

from .models import Profile

_FIELDS = [
    ("Age", "age"),
    ("Height", "height_cm"),
    ("Religion", "religion"),
    ("Caste", "caste"),
    ("Gothram", "gothram"),
    ("Qualification", "qualification"),
    ("Occupation", "occupation"),
    ("Current Location", "current_location"),
    ("Native Place", "native_place"),
    ("Food Preference", "food_preference"),
]


def _row(label: str, value) -> str:
    if not value:
        return ""
    return f'<tr><td class="label">{escape(label)}</td><td>{escape(str(value))}</td></tr>'


def profile_summary_html(profile: Profile, photo_bytes: bytes | None = None, chart: dict | None = None) -> str:
    """Self-contained print-friendly HTML biodata summary for one profile.
    `chart` is the optional dict shape astrology.engine.chart_summary()
    returns (nakshatra/rashi/lagna) — pass None if not computed."""
    photo_html = ""
    if photo_bytes:
        b64 = base64.b64encode(photo_bytes).decode("ascii")
        photo_html = f'<img class="photo" src="data:image;base64,{b64}" alt="Photo" />'

    rows = "".join(
        _row(label, f"{getattr(profile, attr):.0f} cm" if attr == "height_cm" and getattr(profile, attr) else getattr(profile, attr))
        for label, attr in _FIELDS
    )

    chart_html = ""
    if chart:
        chart_html = f"""
        <h2>Astrology</h2>
        <table>
          {_row("Nakshatra", chart.get("nakshatra"))}
          {_row("Rashi", chart.get("rashi"))}
          {_row("Lagna", chart.get("lagna"))}
        </table>
        """

    name = escape(profile.full_name or "Unnamed")
    gender = escape(profile.gender or "")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{name} — Profile Summary</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 640px; margin: 0 auto; padding: 32px;
          color: #2b2024; }}
  .header {{ display: flex; gap: 20px; align-items: center; border-bottom: 2px solid #B03A5B; padding-bottom: 16px; }}
  .photo {{ width: 120px; height: 120px; object-fit: cover; border-radius: 8px; }}
  h1 {{ margin: 0; font-size: 28px; }}
  h2 {{ color: #B03A5B; font-size: 18px; margin-top: 28px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  td.label {{ font-weight: bold; width: 40%; color: #555; }}
  @media print {{ body {{ padding: 0; }} }}
</style></head>
<body>
  <div class="header">
    {photo_html}
    <div><h1>{name}</h1><p>{gender}</p></div>
  </div>
  <table>{rows}</table>
  {chart_html}
</body></html>"""
