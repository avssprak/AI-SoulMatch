"""Shared rendering for match evaluation results.

Used both by the live "Evaluate Match" flow (pages_/4_Matching.py's
render_match_detail) and by browsing an already-saved MatchResult row
(Matching's Saved Matches tab, a profile's Matches tab) — one place renders
an AI recommendation / a saved match's stored detail, not two copies that
drift apart.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from .models import MatchResult, Profile
from .timezones import to_local


def render_recommendation(recommendation: dict) -> None:
    """Render a generate_recommendation()-shaped dict — the AI narrative
    (strengths/concerns/questions/verdict). Shared by the live flow and by
    replaying a saved match's stored recommendation JSON."""
    final = recommendation.get("final_recommendation") or "Unknown"
    if final == "Recommended":
        st.success(f"**{final}** — {recommendation.get('summary', '')}")
    elif final == "Not Recommended":
        st.error(f"**{final}** — {recommendation.get('summary', '')}")
    else:
        st.warning(f"**{final}** — {recommendation.get('summary', '')}")

    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown("**Strengths**")
        for s in recommendation.get("strengths") or []:
            st.markdown(f"- {s}")
        st.markdown("**Questions for Families**")
        for q in recommendation.get("questions_for_families") or []:
            st.markdown(f"- {q}")
    with rc2:
        st.markdown("**Concerns**")
        for c in recommendation.get("concerns") or []:
            st.markdown(f"- {c}")
        if recommendation.get("risk_indicators"):
            st.markdown("**Risk Indicators**")
            for r in recommendation["risk_indicators"]:
                st.markdown(f"- ⚠️ {r}")

    st.markdown(f"**Family compatibility:** {recommendation.get('family_compatibility', '')}")
    st.markdown(f"**Lifestyle compatibility:** {recommendation.get('lifestyle_compatibility', '')}")
    st.markdown(f"**Career compatibility:** {recommendation.get('career_compatibility', '')}")
    st.caption(f"Generated via {recommendation.get('_provider', 'unknown')} AI service")


def render_saved_match_result(
    mr: MatchResult, bride: Profile | None, groom: Profile | None, tz_name: str | None = None,
) -> None:
    """Render a previously-saved MatchResult's full stored detail —
    practical strengths/weaknesses, koota breakdown, dosha flags, and the
    stored AI recommendation JSON — reconstructed entirely from what was
    persisted at save time (no re-evaluation, no LLM call)."""
    st.subheader("Practical Compatibility")
    badge = "✅ Recommended" if mr.recommendation == "Recommended" else "❌ Not Recommended"
    score_text = f"{mr.practical_score:.0f}%" if mr.practical_score is not None else "—"
    st.metric("Practical Score", score_text, badge)
    if mr.practical_detail:
        pc1, pc2 = st.columns(2)
        with pc1:
            st.markdown("**Strengths**")
            for s in mr.practical_detail.get("strengths") or []:
                st.markdown(f"- {s}")
        with pc2:
            st.markdown("**Weaknesses**")
            for w in mr.practical_detail.get("weaknesses") or []:
                st.markdown(f"- {w}")

    if mr.koota_total is not None:
        st.subheader("Vedic Astrology Compatibility")
        st.metric("Ashta Koota Score", f"{mr.koota_total:.1f} / 36")
        if mr.koota_detail and mr.koota_detail.get("kootas"):
            koota_rows = [
                {"Koota": name, "Score": f"{v['score']:.1f} / {v['max']}", "Detail": v["detail"]}
                for name, v in mr.koota_detail["kootas"].items()
            ]
            st.dataframe(pd.DataFrame(koota_rows), width="stretch", hide_index=True)
        flags = (mr.dosha_detail or {}).get("flags")
        if flags:
            st.warning("Dosha flags: " + "; ".join(flags))
        else:
            st.success("No major doshas flagged.")
    else:
        st.info("No astrology score was computed for this match.")

    recommendation = None
    if mr.notes:
        try:
            recommendation = json.loads(mr.notes)
        except (TypeError, ValueError):
            recommendation = None
    if recommendation:
        st.subheader("AI Recommendation")
        render_recommendation(recommendation)

    st.caption(
        f"Saved {to_local(mr.created_at, tz_name):%d %b %Y, %H:%M} — "
        f"Bride #{mr.bride_id} {bride.full_name if bride else 'Unknown'} × "
        f"Groom #{mr.groom_id} {groom.full_name if groom else 'Unknown'}"
    )
