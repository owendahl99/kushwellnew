# FILE: app/utils/wellness.py
from datetime import datetime as _dt
from app.extensions import db
from sqlalchemy import func

def _UsageModel():
    try:
        from app.models import PatientProductUsage
        return PatientProductUsage
    except Exception:
        return None

def _WellnessModel():
    try:
        from app.models import WellnessCheckin
        return WellnessCheckin
    except Exception:
        return None

def latest_wellness(sid):
    WC = _WellnessModel()
    if not WC or not sid:
        return None
    tcol = None
    for t in ("created_at","last_checkin_at","datetime","timestamp","updated_at","created"):
        if hasattr(WC, t):
            tcol = getattr(WC, t); break
    q = db.session.query(WC).filter(getattr(WC, "sid") == sid)
    if tcol is not None:
        q = q.order_by(tcol.desc())
    return q.first()

def wellness_score(row) -> int:
    if not row:
        return 0
    for field in ("score","qol","qol_score","overall"):
        v = getattr(row, field, None)
        if v is not None:
            try: return int(round(float(v)))
            except Exception: pass
    vals = []
    for f in ("mood","appetite","energy","clarity"):
        v = getattr(row, f, None)
        if v is not None:
            vals.append(float(v))
    p = getattr(row, "pain", None)
    if p is not None:
        try: vals.append(max(0.0, 100.0 - float(p)))
        except Exception: pass
    return int(round(sum(vals)/len(vals))) if vals else 0

def has_baseline(sid) -> bool:
    return bool(latest_wellness(sid))

def _has_product_engagement(user_id, sid) -> bool:
    U = _UsageModel()
    if U and hasattr(U, "sid"):
        try:
            return bool(db.session.query(func.count(U.id)).filter(U.sid == sid).scalar() or 0)
        except Exception:
            pass
    # Fallback to UserProduct(status in ["current","saved"])
    try:
        from app.models import UserProduct
        return bool(
            db.session.query(func.count(UserProduct.id)).filter(
                UserProduct.user_id == user_id,
                getattr(UserProduct, "status", "current").in_(["current", "saved"])
            ).scalar() or 0
        )
    except Exception:
        return False

def calculate_onboarding_progress_breakdown(user):
    sid = getattr(user, "sid", None)
    profile = getattr(user, "patient_profile", None)

    def _has_val(x):
        return bool((x or "").strip()) if isinstance(x, str) else bool(x)

    alias_ok = _has_val(getattr(user, "alias_name", None)
                        or getattr(user, "alias", None)
                        or getattr(profile, "alias", None))
    fullname_ok = _has_val(getattr(user, "full_name", None)
                           or getattr(profile, "full_name", None)
                           or (f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()))
    dob_ok = bool(getattr(profile, "date_of_birth", None) or getattr(profile, "dob", None))
    zip_ok = _has_val(getattr(profile, "zip", None) or getattr(profile, "postal_code", None) or getattr(user, "zip", None))
    checkin_ok = has_baseline(sid)
    products_ok = _has_product_engagement(getattr(user, "id", None), sid)

    # 7 fixed steps, no duplicates
    steps = {
        "registration": True,
        "alias": alias_ok,
        "fullname": fullname_ok,
        "dob": dob_ok,
        "zip": zip_ok,
        "checkin": checkin_ok,
        "products": products_ok,
    }
    return steps

def calculate_onboarding_progress(user) -> int:
    steps = calculate_onboarding_progress_breakdown(user)
    total = len(steps) or 1
    pct = int(round(100.0 * (sum(1 for v in steps.values() if v) / total)))
    return max(0, min(100, pct))


