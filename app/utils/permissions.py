# app/utils/permissions.py
from __future__ import annotations
from typing import Any, Optional

def _status_of(p: Any) -> str:
    """
    Return a normalized status string ('approved', 'pending', 'unverified', etc.).
    Looks at approval_status, then status, then state. Defaults to ''.
    """
    for attr in ("approval_status", "status", "state"):
        if hasattr(p, attr):
            v = getattr(p, attr)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
    return ""

def is_unverified_product(p: Any) -> bool:
    """
    True if product is not yet approved (pending, submitted, unverified, etc).
    """
    st = _status_of(p)
    if not st:
        # Be conservative: if no status field, treat as unverified
        return True
    return st in {"pending", "submitted", "unverified", "pending_review", "draft"}

def can_edit_product(user: Any, product: Any) -> bool:
    """
    Policy: ANY authenticated user can edit unverified products.
    Otherwise, only owner/moderator/admin (if you have those) can edit.
    We keep this liberal as requested.
    """
    if is_unverified_product(product):
        return True
    # Optional: tighten for verified products
    # Example owner check: hasattr(product, "submitted_by_id") and product.submitted_by_id == getattr(user, "id", None)
    # Example admin/mod: getattr(user, "role", None) in {"ADMIN","MOD"}
    return False


