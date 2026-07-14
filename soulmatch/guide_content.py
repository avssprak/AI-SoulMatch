"""V5-2-1: copy for the "How It Works" guide (pages_/10_Guide.py).

Kept as plain markdown constants in one file, not inline in the page, so
(a) tests can assert every section exists and (b) a future translation pass
(V5 backlog: Telugu/Hindi) has exactly one file to work from. Section keys
are also the anchors `theme.help_link()` deep-links to — keep them stable
once shipped, since a stale anchor just silently fails to auto-expand
rather than erroring.
"""

from __future__ import annotations

SECTIONS: dict[str, tuple[str, str]] = {
    "child": (
        "Setting up your child's profile",
        """
Everything in SoulMatch is scored *against* your child's profile — think of
it as the anchor. You can create it from **My Child** in the sidebar, or
you'll be walked through it automatically the first time you sign in.

**Why birth time and place matter:** the horoscope (koota) score needs an
exact date, time, and place of birth to calculate planetary positions. If
any of the three is missing, that profile is not "match-ready" and only the
practical-fit score will be available for it — koota compatibility simply
can't be computed. You can always add these later; nothing is lost by
skipping them for now.
""",
    ),
    "candidates": (
        "Adding candidates",
        """
There are three ways to bring a candidate into SoulMatch, all under
**Add Candidates**:

1. **Paste a WhatsApp chat export.** This is the fastest way if a family
   has been sharing biodata over WhatsApp — SoulMatch reads the chat and
   pulls out name, age, birth details, and background automatically.
2. **Paste or upload a biodata document** (PDF, image, or pasted text).
3. **Add one by hand** under the **Add Manually** tab on the Candidates
   page — useful for a quick entry from a phone call.

**How to export a WhatsApp chat (so you can paste it in):**

- **On Android:** open the chat → tap the three-dot menu (⋮) → **More** →
  **Export chat** → choose **Without media** → share it to yourself (e.g.
  via email, or "Save to files") → open that file and copy the text.
- **On iPhone:** open the chat → tap the contact/group name at the top →
  scroll down to **Export Chat** → choose **Without Media** → share it to
  yourself the same way → copy the text out of the exported file.

Once you have the text, paste it into the **Import** tab on Add Candidates.
""",
    ),
    "matching": (
        "Understanding the match score",
        """
Every pairing gets two independent scores, blended into one:

- **Koota score (astrology)** — traditional Vedic compatibility out of 36
  points, shown as a percentage. Needs both people's exact birth date, time,
  and place.
- **Practical score** — how well the candidate fits the preferences you've
  set (location, background, etc.), also shown as a percentage.
- **Composite score** — the two blended together using the **astro weight**
  slider on the Match & Compare page. Slide it toward astrology if Vedic
  matching matters more to your family, or toward practical if it matters
  less. 50/50 is the default.

**Colour bands:** green means a strong match on that score, amber is
borderline, and red flags a likely mismatch or a failed mandatory
criterion (e.g. a dealbreaker in your preferences).
""",
    ),
    "followup": (
        "Follow-ups and pipeline stages",
        """
Every candidate moves through stages (New → Screening → Outreach →
Shortlisted → … → Marriage/Rejected) as you make progress. Use
**Follow-Ups** to add reminders — "call the family," "share biodata,"
"schedule a meeting" — with a due date, so nothing falls through the
cracks. The Dashboard's "Today" panel surfaces anything overdue or
stalled (no activity in a week or more).
""",
    ),
    "billing": (
        "Plans & billing",
        """
- **AI actions** are metered per month (extracting a biodata, an AI match
  explanation, natural-language search). The count and reset date are on
  **My Plan**.
- **Profile caps** limit how many candidates you can store and add per
  month on Free/Plus; Pro is unlimited.
- **Pausing** a paid plan drops you to Free immediately and stops billing
  at the end of the current period — resume anytime from My Plan, and
  your paid-tier limits come back.
- Questions we haven't answered here: **support@redprana.com**.
""",
    ),
}


SECTION_ORDER = ["child", "candidates", "matching", "followup", "billing"]
