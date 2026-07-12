"""Module 17 — Privacy Policy & Terms content (V3-5-1).

Plain markdown constants, not a database-backed CMS — this is a two-page
static document, not a product surface that needs editing without a
deploy. Rendered via st.dialog from the signup form (see app.py) since
this app has no unauthenticated multipage routing.

DRAFT STATUS: this copy was written to be DPDP-aware (what's stored, that
third-party biodata stays private to the workspace, retention, deletion
rights) but has NOT been reviewed by a lawyer. [HUMAN]: get counsel review
before public launch — see the notice embedded in both documents below.
"""

from __future__ import annotations

LAST_UPDATED = "12 July 2026"

_DRAFT_NOTICE = (
    "> **Draft — not yet reviewed by counsel.** This document describes our "
    "current data practices in good faith but has not been reviewed by a "
    "lawyer. Do not treat it as a final legal document until this notice is "
    "removed."
)

PRIVACY_POLICY_MD = f"""
{_DRAFT_NOTICE}

### Privacy Policy

*Last updated: {LAST_UPDATED}*

**Who we are.** SoulMatch is a product of RedPrana. This policy covers the
SoulMatch web application (soulmatch.redprana.com).

**What we store.** When you use SoulMatch we store: your account details
(name, email, hashed password — we never see or store your plain-text
password); every candidate profile you create or import, including
biodata, horoscope details, and any documents/photos you upload; your
notes, tasks, and activity history; and usage records of AI features (for
billing and quota purposes — see "AI usage" below).

**Third-party data.** Many profiles you manage belong to other people —
candidates found through WhatsApp groups, relatives, or matrimonial
bureaus, not your own account. That data is stored **privately in your
workspace only**; SoulMatch never makes it visible to other accounts,
never shares it with other Members, and never uses it to train any model.
If you are the subject of a profile someone else created and want it
corrected or removed, contact us at support@redprana.com.

**AI usage.** When you use an AI feature (profile extraction, match
explanations, natural-language search), the relevant profile text is sent
to our configured AI provider (Google Gemini or Anthropic Claude,
depending on configuration) to generate a response. We log the number of
tokens used for billing and quota enforcement — not the content of your
data — in our own database.

**Retention.** Your data is retained as long as your account is active.
If you downgrade or your subscription lapses, your existing data is kept
(read-only above your new plan's limits) — nothing is deleted just because
you stop paying. You can permanently delete your account and all its data
at any time from **My Plan → Delete my account**.

**Your rights.** You can export a complete copy of everything your account
has stored (My Plan → Export my data) and permanently delete your account
and all associated data (My Plan → Delete my account) at any time,
yourself, without contacting support.

**Payments.** Subscription payments are processed by Razorpay (India) or
Stripe (international) — we never see or store your card/UPI details
directly; that's handled entirely by the payment gateway.

**Contact.** Questions about this policy: support@redprana.com.
"""

TERMS_MD = f"""
{_DRAFT_NOTICE}

### Terms of Service

*Last updated: {LAST_UPDATED}*

**The service.** SoulMatch (a product of RedPrana) is a private workspace
for managing a matrimonial search — profile extraction, matching,
horoscope compatibility, and workflow tracking. It is not a public
matrimonial directory: profiles you create are visible only to your own
account, never to other Members, and there is no public search of any
kind.

**Your account.** You're responsible for keeping your login credentials
confidential and for the accuracy of the data you enter or import. You
must be at least 18 years old to create an account.

**Acceptable use.** Don't use SoulMatch to store or process data you
don't have a legitimate reason to hold, to harass anyone, or to attempt
to access another account's data.

**Subscription & billing.** Paid plans (Plus, Pro) renew automatically per
your chosen billing interval (monthly/annual) until you pause or cancel.
You can pause anytime from My Plan — this stops future billing and your
account gates to the Free plan's limits until you resume.

**Data ownership.** You own the data you put into SoulMatch. We do not
sell it, and do not use it to train AI models. See the Privacy Policy for
full detail on storage and third-party AI processing.

**Termination.** You may delete your account at any time (My Plan →
Delete my account), which permanently and immediately removes your data.
We may suspend an account that violates the Acceptable Use section above.

**Changes.** We may update these Terms; material changes will be
communicated by email to the address on your account.

**Contact.** support@redprana.com.
"""
