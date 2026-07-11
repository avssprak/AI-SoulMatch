"""V3 tenant isolation (V3_PLAN.md Sprint V3-1).

Every domain table carries owner_user_id, and every read/write path in the
app must go through the helpers here rather than raw select()/session.get(),
so that scoping is structural instead of per-query discipline. There is
deliberately NO admin bypass in these helpers: on the domain pages the Admin
works inside their own workspace exactly like a Member; operator surfaces
(the Customers page) query the users table directly and never touch another
tenant's domain rows.

tests/test_tenancy.py asserts cross-tenant invisibility for every page-level
query path — keep it green in every future change.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select
from sqlalchemy.orm import Session

T = TypeVar("T")


def owned(stmt: Select, model, owner_id: int) -> Select:
    """Append the tenant filter for `model` to a select() statement."""
    if owner_id is None:  # defensive: never silently widen to all tenants
        raise ValueError("owner_id is required for tenant-scoped queries")
    return stmt.where(model.owner_user_id == owner_id)


def get_owned(session: Session, model: type[T], pk: int, owner_id: int) -> T | None:
    """session.get() that returns None unless the row belongs to owner_id —
    the required replacement for session.get() on any domain model, so a
    guessed/stale ID in the URL or a widget can never cross tenants."""
    if owner_id is None:
        raise ValueError("owner_id is required for tenant-scoped lookups")
    obj = session.get(model, pk)
    if obj is None or obj.owner_user_id != owner_id:
        return None
    return obj


def owner_id_of(user: dict) -> int:
    """The tenant key for the signed-in user dict kept in session state."""
    return user["id"]
