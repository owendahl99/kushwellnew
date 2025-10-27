# app/routes/search.py
from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_login import current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import User  # import other enterprise/group models inside helpers to avoid hard deps
from app.services.security import get_privacy

search_bp = Blueprint("search", __name__, url_prefix="/search")


# ----------------- helpers -----------------

def _people_results(q: str):
    """
    People search gate:
    - If query matches alias -> require discoverable.by_alias
    - If query matches real name -> require discoverable.by_name
    - If no query -> require either flag True
    """
    qn = (q or "").strip().lower()

    qry = db.session.query(User)
    if qn:
        qry = qry.filter(or_(
            User.alias_name.ilike(f"%{qn}%"),
            User.name.ilike(f"%{qn}%")
        ))

    rows = []
    for u in qry.limit(50).all():
        s = get_privacy(u.id)  # {'alias', 'preferred_display', 'discoverable':{'by_name','by_alias'}, 'visibility': {...}}

        matched_alias = bool(qn) and u.alias_name and (qn in u.alias_name.lower())
        matched_name  = bool(qn) and u.name and (qn in u.name.lower())

        if not qn:
            # Empty query: only include users who are discoverable in some way
            if not (s["discoverable"]["by_alias"] or s["discoverable"]["by_name"]):
                continue
        else:
            allow = False
            if matched_alias and s["discoverable"]["by_alias"]:
                allow = True
            if matched_name and s["discoverable"]["by_name"]:
                allow = True
            if not allow:
                continue

        rows.append({
            "id": u.id,
            "name": u.name,          # your template can call {{ display_name(u) }} if you pass the object instead
            "alias": u.alias_name,
            "profile_url": "#",      # wire to your profiles route when ready
        })
    return rows


def _enterprise_results(q: str):
    """
    Return list[dict]: {id, name, kind} where kind ? {'provider','supplier','dispensary'}.
    Template should build links via enterprise_public_url(e).
    """
    like = f"%{q}%" if q else None
    items = []

    # Import inside function so the module doesn’t hard-fail if one model is missing
    try:
        from app.models import Provider
        qp = db.session.query(Provider)
        if like:
            qp = qp.filter(Provider.name.ilike(like))
        for p in qp.limit(30).all():
            items.append({"id": p.id, "name": p.name, "kind": "provider"})
    except Exception:
        pass

    try:
        from app.models import SupplierProfile
        qs = db.session.query(SupplierProfile)
        if like:
            qs = qs.filter(SupplierProfile.company_name.ilike(like))
        for s in qs.limit(30).all():
            items.append({"id": s.id, "name": s.company_name, "kind": "supplier"})
    except Exception:
        pass

    try:
        from app.models import Dispensary
        qd = db.session.query(Dispensary)
        if like:
            qd = qd.filter(Dispensary.name.ilike(like))
        for d in qd.limit(30).all():
            items.append({"id": d.id, "name": d.name, "kind": "dispensary"})
    except Exception:
        pass

    return items


def _support_group_results(q: str):
    """
    Prefer DB model SupportGroup(name). Fallback to static JSON at static/data/support_groups.json.
    """
    like = f"%{q}%" if q else None
    try:
        from app.models import SupportGroup
        qs = db.session.query(SupportGroup)
        if like:
            qs = qs.filter(SupportGroup.name.ilike(like))
        return [{"id": g.id, "name": g.name, "kind": "group"} for g in qs.limit(50).all()]
    except Exception:
        # static fallback
        import json, os
        from flask import current_app
        data_path = os.path.join(current_app.root_path, "static", "data", "support_groups.json")
        try:
            names = json.load(open(data_path, "r", encoding="utf-8"))
        except Exception:
            names = []
        out = [{"id": i + 1, "name": n, "kind": "group"} for i, n in enumerate(names)]
        if q:
            ql = q.lower()
            out = [g for g in out if ql in g["name"].lower()]
        return out[:50]


# ----------------- unified route -----------------

@search_bp.get("/", endpoint="unified")
def unified():
    q     = request.args.get("q", "", type=str)
    scope = (request.args.get("scope") or "all").lower()  # all|people|enterprises|groups

    results = {}
    if scope in ("all", "people"):
        results["people"] = _people_results(q)
    if scope in ("all", "enterprises"):
        results["enterprises"] = _enterprise_results(q)
    if scope in ("all", "groups"):
        results["groups"] = _support_group_results(q)

    total = sum(len(v) for v in results.values())
    return render_template("search/unified.html", q=q, scope=scope, results=results, total=total)


