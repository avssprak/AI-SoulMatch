"""Module 15 — Plan limits, AI-action metering & quota enforcement (V3-2).

Single source of truth for what each plan includes (PLAN_LIMITS) plus the
helpers pages call to record usage, check quotas, and gate features. See
V3_PLAN.md Sprint V3-2 for the full spec this implements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import AiUsage, Profile, User
from .tenancy import owned

GRACE_DAYS = 7

# None = unlimited. Keep this the only place plan differences are encoded —
# every gate in the app reads from here rather than branching on plan name.
PLAN_LIMITS = {
    "free": {"ai_actions": 15, "profiles": 25, "profiles_per_month": 10, "children": 1,
             "ai_explanations": False, "nl_search": False, "bulk_imports": 0},
    "plus": {"ai_actions": 150, "profiles": 200, "profiles_per_month": 30, "children": 1,
             "ai_explanations": True, "nl_search": True, "bulk_imports": 1},
    "pro": {"ai_actions": 500, "profiles": 1000, "profiles_per_month": 100, "children": 3,
            "ai_explanations": True, "nl_search": True, "bulk_imports": None},
}

# Display-only; kept alongside PLAN_LIMITS so the pricing table on My Plan
# and the landing page can never drift from what's actually enforced here.
PLAN_PRICES_INR = {"free": 0, "plus": 199, "pro": 499}
PLAN_PRICES_INR_ANNUAL = {"free": 0, "plus": 1499, "pro": 3999}
PLAN_PRICES_USD = {"free": 0, "plus": 9.99, "pro": 14.99}
PLAN_PRICES_USD_ANNUAL = {"free": 0, "plus": 79.99, "pro": 119.99}


def annual_discount_pct(plan: str, currency: str) -> int:
    """Approx % saved by paying annually vs. 12x the monthly price, rounded
    to the nearest whole percent for display on the pricing cards."""
    monthly = (PLAN_PRICES_INR if currency == "INR" else PLAN_PRICES_USD)[plan]
    annual = (PLAN_PRICES_INR_ANNUAL if currency == "INR" else PLAN_PRICES_USD_ANNUAL)[plan]
    if not monthly:
        return 0
    return round((1 - annual / (monthly * 12)) * 100)

AI_ACTIONS = ("extract", "recommend", "nl_search")


class QuotaExceeded(Exception):
    """Raised by require_quota(); .message is ready to show the user directly."""


def limits_for(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def estimate_cost_inr(tokens_in: int, tokens_out: int) -> float:
    cost_usd = (
        tokens_in * config.LLM_PRICE_IN_USD_PER_MTOK
        + tokens_out * config.LLM_PRICE_OUT_USD_PER_MTOK
    ) / 1_000_000
    return cost_usd * config.USD_INR


def record_usage(session: Session, owner_id: int, action: str, tokens_in: int, tokens_out: int) -> AiUsage:
    """Insert one AiUsage row. Call ONLY after a successful LLM call — a
    failed call must not consume the caller's quota."""
    if action not in AI_ACTIONS:
        raise ValueError(f"Unknown AI action: {action}")
    row = AiUsage(
        owner_user_id=owner_id, action=action, tokens_in=tokens_in, tokens_out=tokens_out,
        cost_estimate_inr=estimate_cost_inr(tokens_in, tokens_out),
    )
    session.add(row)
    session.flush()
    return row


def _month_start(today: date | None = None) -> datetime:
    today = today or datetime.now(timezone.utc).date()
    return datetime(today.year, today.month, 1, tzinfo=timezone.utc)


def _next_month_start(today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return date(today.year + (today.month == 12), today.month % 12 + 1, 1)


@dataclass
class QuotaStatus:
    used: int
    limit: int | None  # None = unlimited
    resets_on: date

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.used >= self.limit


def quota_status(session: Session, user: dict, *, today: date | None = None) -> QuotaStatus:
    """Actions used by this owner so far in the current UTC calendar month."""
    owner_id = user["id"]
    limit = limits_for(user.get("plan", "free"))["ai_actions"]
    used = session.scalar(
        select(func.count(AiUsage.id)).where(
            AiUsage.owner_user_id == owner_id,
            AiUsage.created_at >= _month_start(today),
        )
    ) or 0
    return QuotaStatus(used=used, limit=limit, resets_on=_next_month_start(today))


def require_quota(session: Session, user: dict, *, today: date | None = None) -> QuotaStatus:
    """Raise QuotaExceeded (message ready for st.warning) if the owner has
    used up this month's AI-action quota. Call BEFORE the LLM call — quota
    checks must never depend on whether the call that follows succeeds."""
    status = quota_status(session, user, today=today)
    if status.exhausted:
        raise QuotaExceeded(
            f"You've used {status.used}/{status.limit} AI actions this month — "
            f"upgrade on My Plan or wait until {status.resets_on:%d %b} when your quota resets."
        )
    return status


def can_use_ai_explanations(user: dict) -> bool:
    return limits_for(user.get("plan", "free"))["ai_explanations"]


def can_use_nl_search(user: dict) -> bool:
    return limits_for(user.get("plan", "free"))["nl_search"]


UPGRADE_TEASE = (
    f"🔒 **Why this match works** — AI match explanations are on the Plus plan (₹{PLAN_PRICES_INR['plus']}/mo). "
    "[See plans](#) on **My Plan**."
)
NL_SEARCH_TEASE = (
    f"🔒 Natural-language search is on the Plus plan (₹{PLAN_PRICES_INR['plus']}/mo). See **My Plan** to upgrade."
)


@dataclass
class ProfileUsage:
    used_this_month: int
    monthly_limit: int | None  # None = unlimited
    total: int
    total_limit: int | None  # None = unlimited
    resets_on: date


def profile_usage_status(session: Session, user: dict, *, today: date | None = None) -> ProfileUsage:
    """Profiles added this calendar month plus the lifetime total, for
    display on My Plan (V3-2). Mirrors quota_status()'s AI-actions shape."""
    plan_limits = limits_for(user.get("plan", "free"))
    owner_id = user["id"]
    used_this_month = session.scalar(
        select(func.count()).select_from(
            owned(
                select(Profile.id).where(Profile.created_at >= _month_start(today)),
                Profile, owner_id,
            ).subquery()
        )
    ) or 0
    total = session.scalar(
        select(func.count()).select_from(owned(select(Profile.id), Profile, owner_id).subquery())
    ) or 0
    return ProfileUsage(
        used_this_month=used_this_month,
        monthly_limit=plan_limits["profiles_per_month"],
        total=total,
        total_limit=plan_limits["profiles"],
        resets_on=_next_month_start(today),
    )


def can_add_profile(session: Session, user: dict, *, today: date | None = None) -> tuple[bool, str]:
    """Whether this owner may create one more Profile row under their plan's
    total cap and monthly cap. Call before every Profile-create path (Ingest
    auto-process, Ingest manual save, Profiles Add Manually)."""
    plan_limits = limits_for(user.get("plan", "free"))
    limit = plan_limits["profiles"]
    monthly_limit = plan_limits["profiles_per_month"]
    owner_id = user["id"]

    if limit is not None:
        count = session.scalar(
            select(func.count()).select_from(owned(select(Profile.id), Profile, owner_id).subquery())
        ) or 0
        if count >= limit:
            return False, (
                f"Your plan stores up to {limit} candidate profiles — upgrade for a higher limit."
            )

    if monthly_limit is not None:
        month_count = session.scalar(
            select(func.count()).select_from(
                owned(
                    select(Profile.id).where(Profile.created_at >= _month_start(today)),
                    Profile, owner_id,
                ).subquery()
            )
        ) or 0
        if month_count >= monthly_limit:
            return False, (
                f"Your plan allows adding up to {monthly_limit} new profiles per month — "
                "upgrade for a higher limit or try again next month."
            )

    return True, ""


def can_mark_own_child(session: Session, user: dict) -> tuple[bool, str]:
    """Whether this owner may mark one more Profile as their own child
    (V3-6-1), under their plan's cap. Only call when a profile is being
    newly marked (False -> True) — unmarking is always allowed regardless
    of the cap."""
    limit = limits_for(user.get("plan", "free"))["children"]
    if limit is None:
        return True, ""
    owner_id = user["id"]
    count = session.scalar(
        select(func.count()).select_from(
            owned(select(Profile.id).where(Profile.is_own_child.is_(True)), Profile, owner_id).subquery()
        )
    ) or 0
    if count >= limit:
        return False, (
            f"Your plan allows marking up to {limit} child profile(s) as your own — "
            "upgrade for more."
        )
    return True, ""


def monthly_usage_summary(session: Session, *, today: date | None = None) -> dict:
    """Admin-only: this month's total cost and breakdown by action, plus the
    top-5 heaviest users by cost. See pages_/7_Users.py."""
    start = _month_start(today)
    total_cost = session.scalar(
        select(func.sum(AiUsage.cost_estimate_inr)).where(AiUsage.created_at >= start)
    ) or 0.0
    by_action = dict(session.execute(
        select(AiUsage.action, func.count(AiUsage.id))
        .where(AiUsage.created_at >= start).group_by(AiUsage.action)
    ).all())
    top_rows = session.execute(
        select(AiUsage.owner_user_id, func.sum(AiUsage.cost_estimate_inr).label("cost"))
        .where(AiUsage.created_at >= start)
        .group_by(AiUsage.owner_user_id)
        .order_by(func.sum(AiUsage.cost_estimate_inr).desc())
        .limit(5)
    ).all()
    owner_ids = [r[0] for r in top_rows]
    names = {
        u.id: (u.email or u.username)
        for u in session.scalars(select(User).where(User.id.in_(owner_ids))).all()
    } if owner_ids else {}
    top_users = [{"user": names.get(oid, f"#{oid}"), "cost_inr": cost} for oid, cost in top_rows]
    return {"total_cost_inr": total_cost, "by_action": by_action, "top_users": top_users}


# --- V3-3: price catalog, checkout, and plan lifecycle ----------------------
#
# PRICE_CATALOG is the single source of truth for (plan, interval, currency)
# -> amount + which gateway/price-id to use. My Plan and soulmatch.payments
# both read from here so the checkout amount can never drift from what's
# advertised, and adding a new interval/currency means editing this table
# only.

class PaymentConfigError(Exception):
    """Raised when a checkout is attempted before the relevant gateway's
    account/price ids are configured in .env — message is support-ready."""


def _catalog() -> dict[tuple[str, str, str], dict]:
    catalog: dict[tuple[str, str, str], dict] = {}
    for plan in ("plus", "pro"):
        catalog[(plan, "monthly", "INR")] = {
            "amount": PLAN_PRICES_INR[plan], "provider": "razorpay",
            "provider_price_id": getattr(config, f"RAZORPAY_PLAN_{plan.upper()}_MONTHLY"),
        }
        catalog[(plan, "annual", "INR")] = {
            "amount": PLAN_PRICES_INR_ANNUAL[plan], "provider": "razorpay",
            "provider_price_id": getattr(config, f"RAZORPAY_PLAN_{plan.upper()}_ANNUAL"),
        }
        catalog[(plan, "monthly", "USD")] = {
            "amount": PLAN_PRICES_USD[plan], "provider": "stripe",
            "provider_price_id": getattr(config, f"STRIPE_PRICE_{plan.upper()}_MONTHLY"),
        }
        catalog[(plan, "annual", "USD")] = {
            "amount": PLAN_PRICES_USD_ANNUAL[plan], "provider": "stripe",
            "provider_price_id": getattr(config, f"STRIPE_PRICE_{plan.upper()}_ANNUAL"),
        }
    return catalog


PRICE_CATALOG = _catalog()


def price_entry(plan: str, interval: str, currency: str) -> dict:
    try:
        return PRICE_CATALOG[(plan, interval, currency)]
    except KeyError as e:
        raise PaymentConfigError(f"No price configured for {plan}/{interval}/{currency}.") from e


def plan_interval_for_provider_price_id(provider_price_id: str) -> tuple[str, str] | None:
    """Reverse lookup used by webhook handlers: a gateway plan/price id ->
    our (plan, interval), so we don't have to trust the webhook payload's
    own idea of plan naming."""
    for (plan, interval, _currency), entry in PRICE_CATALOG.items():
        if entry["provider_price_id"] and entry["provider_price_id"] == provider_price_id:
            return plan, interval
    return None


def effective_plan(user: User) -> str:
    """The plan to enforce gates against. A paused subscription gates as
    free WITHOUT overwriting user.plan, so Resume can restore the same tier
    (see V3-3-4). Everything else (active/past_due/free) uses the stored
    plan as-is — past_due still has full access during its grace window."""
    if user.plan_status == "paused":
        return "free"
    return user.plan


def sync_plan_status(session: Session, user: User) -> None:
    """Lazily downgrade a past_due account whose grace window has expired.
    Call once per login/token-restore (see app.py) — there is no cron in
    this deployment, so expiry is only ever discovered when the user (or an
    Admin looking them up) causes a page load."""
    if (
        user.plan_status == "past_due"
        and user.plan_grace_until is not None
        and datetime.now(timezone.utc).replace(tzinfo=None) > user.plan_grace_until
    ):
        user.plan = "free"
        user.plan_status = "free"
        user.plan_grace_until = None
        session.commit()


def pause_subscription(session: Session, user: User) -> None:
    """V3-3-4 Pause: gates as free immediately (plan value is preserved for
    Resume). Cancelling the gateway subscription itself is the caller's
    job (soulmatch.payments) — this only flips the local flag."""
    user.plan_status = "paused"
    session.commit()


def resume_subscription(session: Session, user: User) -> None:
    """V3-3-4 Resume: clears the pause flag. Actually reactivating billing
    (a new checkout) is a separate step the My Plan page walks the user
    through — this alone does not create a new gateway subscription."""
    if user.plan_status == "paused":
        user.plan_status = "active" if user.plan != "free" else "free"
        session.commit()
