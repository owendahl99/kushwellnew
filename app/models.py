# -*- coding: utf-8 -*-
from __future__ import annotations
# Canonicalize this module so it's the same object under both names.
import sys as _sys
if __name__ != "app.models":    
    # If someone imports `models` or via another path, alias it to app.models
    _sys.modules.setdefault("app.models", _sys.modules[__name__])
    _sys.modules.setdefault("models", _sys.modules[__name__])

# ----------------------
# Stdlib
# ----------------------
import random
import string
from datetime import datetime, date
import uuid
from datetime import datetime, date
from typing import Optional, Dict, List

# ----------------------
# Flask
# ----------------------
from flask import url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------
# SQLAlchemy (core + orm)
# ----------------------
from sqlalchemy import (
    and_,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    event,
    Float,
    ForeignKey,
    Index,
    Column,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship, validates, foreign, synonym, Session, object_session, backref  
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.dialects.sqlite import TEXT

# ----------------------
# App extensions (db MUST be imported before using db.Column)
# ----------------------
from app.extensions import db


# ======================
# UUID config
# ======================
_UUID_KW = dict(as_uuid=True)  # ensure all UUID columns are consistent

#   ----------------------
# App constants / enums
# ----------------------
from app.constants.product_constants import APPLICATION_METHODS
from app.constants.general_menus import ProductStatus, SubmissionType, UserRoleEnum, AFFLICTION_LEVELS, AFFLICTION_LIST
# optional, your timestamp mixin


# --- Small helpers ----------------------------------------------------------
def _clamp_int(x, default=6, lo=1, hi=10):
    try:
        v = int(float(x))
    except Exception:
        v = default
    return max(lo, min(hi, v))

def _calc_qol_from_sliders(vals: dict) -> int:
    """
    Compute QoL (0..100) from six equally-weighted sliders:
      pain (inverted: 11 - pain), mood, energy, clarity, appetite, sleep
    Sliders expected in 1..10. Missing -> default 6.
    """
    p = _clamp_int(vals.get("pain", vals.get("pain_level", None)), default=6)
    m = _clamp_int(vals.get("mood", vals.get("mood_level", None)), default=6)
    e = _clamp_int(vals.get("energy", vals.get("energy_level", None)), default=6)
    c = _clamp_int(vals.get("clarity", vals.get("clarity_level", None)), default=6)
    a = _clamp_int(vals.get("appetite", vals.get("appetite_level", None)), default=6)
    s = _clamp_int(vals.get("sleep", vals.get("sleep_level", None)), default=6)

    inv_pain = 11 - p
    total = inv_pain + m + e + c + a + s   # range 6..60
    qol = int(round((total / 60.0) * 100))  # 0..100
    return qol

# --- Mixins ----------------------------------------------------------------
class TimestampMixin(object):
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class SoftDeleteMixin(object):
    deleted_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


# ======================
# Helper lookups (safe to call even if constants move)
# ======================
def _afflictions_master() -> List[str]:
    try:
        from app.constants.afflictions import get_afflictions
        return list(get_afflictions() or [])
    except Exception:
        try:
            from app.constants.afflictions import AFFLICTION_LIST as _LIST
            return list(_LIST or [])
        except Exception:
            return []


def _severity_levels() -> List[str]:
    try:
        from app.constants.afflictions import get_levels
        levels = list(get_levels() or [])
        return levels if levels else ["I", "II", "III", "IV", "V"]
    except Exception:
        return ["I", "II", "III", "IV", "V"]


# ======================
# Uploads
# ======================
class UploadedFile(db.Model):
    __tablename__ = "uploaded_file"

    id = db.Column(Integer, primary_key=True)
    filename = db.Column(String(255), nullable=False)
    filepath = db.Column(String(255), nullable=False)
    uploaded_at = db.Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by_id = db.Column(Integer, db.ForeignKey("user.id"), nullable=True)

    uploaded_by = relationship("User", backref="uploaded_files")

    def __repr__(self) -> str:
        return f"<UploadedFile {self.filename}>"


# =========================
# Association Table
# =========================
user_support_groups = db.Table(
    "user_support_groups",
    Column("user_id", Integer, ForeignKey("user.id"), primary_key=True),
    Column("support_group_id", Integer, ForeignKey("support_group.id"), primary_key=True),
)

# =========================
# Support Groups
# =========================
class SupportGroup(db.Model):
    __tablename__ = "support_group"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    affliction = Column(String(64), nullable=False)

    # Relationships
    members = relationship(
        "User",
        secondary=user_support_groups,
        back_populates="support_groups",
        lazy="dynamic",
    )
    posts = relationship(
        "SupportGroupPost",
        back_populates="support_group",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    
# =========================
# Support Group Posts (Bulletin)
# =========================
class SupportGroupPost(db.Model):
    __tablename__ = "support_group_post"

    id = Column(Integer, primary_key=True)
    support_group_id = Column(Integer, ForeignKey("support_group.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)

    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    is_moderated = Column(db.Boolean, default=False)
    is_approved = Column(db.Boolean, default=True)

    user = relationship("User", back_populates="support_group_posts")
    support_group = relationship("SupportGroup", back_populates="posts")

# =========================
# Support Group Membership (UUID-based)
# =========================
class GroupMember(db.Model):
    __tablename__ = "group_member"

    id = Column(Integer, primary_key=True)

    user_sid = Column(String(36), ForeignKey("user.sid"), nullable=True)
    patient_sid = Column(String(36), nullable=True)

    group_id = Column(Integer, ForeignKey("support_group.id"), nullable=True)
    group_key = Column(String(120), nullable=True)
    group_name = Column(String(255), nullable=True)

    joined_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    timestamp = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    group = relationship("SupportGroup", backref=backref("group_memberships", lazy="dynamic"))
    user = relationship("User", backref=backref("group_members", lazy="dynamic"))

    def __repr__(self):
        return f"<GroupMember user_sid={self.user_sid} group_key={self.group_key}>"


    # convenience helper to set from UUID object
    @staticmethod
    def uuid_to_str(val):
        if isinstance(val, uuid.UUID):
            return str(val)
        if val:
            return str(uuid.UUID(str(val)))
        return None


    # ======================
    # Identity Split (PII kept separate)
    # ======================
    class PersonIdentity(db.Model, TimestampMixin):
        __tablename__ = "person_identity"
        __table_args__ = {"extend_existing": True}  #
        
        id = db.Column(Integer, primary_key=True)
        legal_name = db.Column(String(255), nullable=False)
        birthdate = db.Column(db.Date, nullable=True)
        email = db.Column(String(255), nullable=True, index=True)
        phone = db.Column(String(64), nullable=True)
        

    class IdentityLink(db.Model, TimestampMixin):
        """
        Maps a PII identity row to a pseudonymous SID (UUID) used everywhere else.
        """
        __tablename__ = "identity_link"
        __table_args__ = {"extend_existing": True}  # temporary guard


        id = db.Column(Integer, primary_key=True)
        identity_id = db.Column(
            Integer,
            db.ForeignKey("person_identity.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
        sid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

        key_version = db.Column(Integer, nullable=False, default=1)

        identity = relationship("PersonIdentity")
        
# ======================
# Users
# ======================
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(SAEnum(UserRoleEnum), nullable=False)

    # Auth / identity
    name = db.Column(db.String(128))
    first_name = db.Column(db.String(64))
    last_name  = db.Column(db.String(64))
    birthdate = db.Column(db.Date, nullable=False)
    zip_code   = db.Column(db.String(20), nullable=False)

    # Status flags
    is_blacklisted = db.Column(db.Boolean, default=False)
    privacy = db.Column(db.JSON, nullable=True)

    # Public identity
    alias_name         = db.Column(db.String(80))
    alias_slug         = db.Column(db.String(100), unique=True)
    alias_public_on    = db.Column(db.Boolean, default=False)
    alias_mask_friends = db.Column(db.Boolean, default=False)
    preferred_display = db.Column(db.String(10), default="real")  # 'real' or 'alias'

    # ------------------ One-to-One Profiles ------------------
    patient_profile = db.relationship(
        "PatientProfile",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="PatientProfile.user_sid",
    )
    
    provider_profile = db.relationship(
        "Provider",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Provider.user_id",
    )  
    dispensary_profile = db.relationship(
        "Dispensary",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan"
    )
    supplier_profile = db.relationship(
        "SupplierProfile",
        uselist=False,
        back_populates="user",
        cascade="all, delete-orphan"
    )
    support_group_posts = db.relationship(
        "SupportGroupPost",
        back_populates="user",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    support_groups = db.relationship(
        "SupportGroup",
        secondary=user_support_groups,
        back_populates="members",
        lazy="dynamic"
    )

    group_memberships = relationship(
        "GroupMember",
        back_populates="user",
        lazy="dynamic",
        overlaps="group_members"
    )
    
    def is_friend(self, other_user_id: int) -> bool:
        """Return True if this user is friends with the given user_id."""
        return (
            Friends.query.filter_by(user_id=self.id, friend_id=other_user_id).first()
            or Friends.query.filter_by(user_id=other_user_id, friend_id=self.id).first()
        ) is not None

    

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ------------------ Other Relationships ------------------
    upvotes = db.relationship(
        "Upvote",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    support_groups = db.relationship(
        "SupportGroup",
        secondary=user_support_groups,
        back_populates="members",
        lazy="dynamic"
    )

    support_posts = db.relationship(
        "SupportGroupPost",
        back_populates="user",
        cascade="all, delete-orphan",
        overlaps="support_group_posts"  # fixes the warning
        )
    
    # ------------------ Methods ------------------
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        return self.role == UserRoleEnum.ADMIN  # compare properly to the enum

    def get_display_name(self) -> str:
        fn = getattr(self, "first_name", "").strip() if getattr(self, "first_name", None) else ""
        ln = getattr(self, "last_name", "").strip() if getattr(self, "last_name", None) else ""
        if fn or ln:
            return f"{fn} {ln}".strip()
        if self.name and self.name.strip():
            return self.name.strip()
        return (self.email or "User").split("@")[0]

    # ------------------ Inventory Reports ------------------
    @property
    def submitted_inventory_reports(self):
        """Return InventoryReport objects submitted by this user, either as a dispensary or direct-to-public supplier."""
        from app.models import InventoryReport
        from sqlalchemy import or_

        conds = []
        if self.dispensary_profile:
            conds.append(
                (InventoryReport.reporter_type == "dispensary") &
                (InventoryReport.reporter_id == self.dispensary_profile.id)
            )
        if self.supplier_profile:
            conds.append(
                (InventoryReport.reporter_type == "supplier") &
                (InventoryReport.reporter_id == self.supplier_profile.id)
            )
        if not conds:
            return InventoryReport.query.filter(False)  # empty query
        query = InventoryReport.query.filter(or_(*conds))
        return query

    # ------------------ Helper Methods ------------------
    def is_dispensary_owner(self):
        return self.dispensary_profile is not None

    def is_supplier(self):
        return self.supplier_profile is not None

    # ------------------
    # Utility / computed properties
    # ------------------
    @property
    def display_name(self) -> str:
        print(f"Computing display_name for user id={self.id}")
        # Defensive get with defaults
        preferred_display = getattr(self, "preferred_display", "real")
        alias_name = getattr(self, "alias_name", None)
        alias_public_on = getattr(self, "alias_public_on", False)
        first_name = getattr(self, "first_name", None)
        last_name = getattr(self, "last_name", None)
        email = getattr(self, "email", "user@example.com")

        # Alias display takes priority if preferred
        if preferred_display == "alias" and alias_name and alias_public_on:
            return alias_name

        # Real name fallback
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        if full_name:
            return full_name

        # Alias fallback if public not preferred
        if alias_name:
            return alias_name

        # Fallback to email username
        return email.split("@")[0]

    def is_discoverable_by_alias(self):
        """Check if the user can be discovered via alias."""
        return bool(self.discoverable and self.discoverable.get("by_alias", False) and self.alias_public_on)

    def is_discoverable_by_real_name(self):
        """Check if the user can be discovered via real name."""
        return bool(self.discoverable and self.discoverable.get("by_name", False) and self.first_name)

    def is_discoverable_by_friends(self):
        """Check if user allows friends to see them (MPTT-style)."""
        return bool(self.discoverable and self.discoverable.get("by_friends", False))

    def can_be_seen_field(self, field: str, viewer_is_friend=False):
        """
        Determine visibility for a particular field: 'private', 'friends', 'public'.
        """
        if not self.visibility or field not in self.visibility:
            return False

        vis = self.visibility.get(field, "private")
        if vis == "public":
            return True
        if vis == "friends" and viewer_is_friend:
            return True
        return False

    @property
    def visibility(self):
        return self.privacy or {}

@property
def full_name(self):
    return f"{self.first_name or ''} {self.last_name or ''}".strip()

@full_name.setter
def full_name(self, value):
    """Allow setting full_name directly; splits into first/last."""
    value = (value or "").strip()
    parts = value.split(" ", 1)
    self.first_name = parts[0]
    self.last_name = parts[1] if len(parts) > 1 else ""
# ======================
# Patient Profile
# ======================
class PatientProfile(db.Model):
    __tablename__ = "patient_profile"

    # ------------------
    sid = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_sid = db.Column(db.String(36), db.ForeignKey("user.sid"), nullable=False)
    onboarding_complete = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

 
    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=True)
 
    
    # ------------------
    # Optional Extended Data
    # ------------------
    sex = db.Column(db.String(10), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)

    # Height and Weight (U.S. units)
    height_feet = db.Column(db.Integer, nullable=True)   # e.g., 5
    height_inches = db.Column(db.Integer, nullable=True) # e.g., 9
    weight_lbs = db.Column(db.Float, nullable=True)      # e.g., 165.0

    # ------------------
    # Cannabis Use History
    # ------------------
    cannabis_use_start_age = db.Column(db.Integer, nullable=True)  # Age when patient first used cannabis
    cannabis_use_frequency = db.Column(
        db.Enum(
            "daily",
            "multiple_per_week",
            "weekly",
            "monthly",
            "occasional",
            "social_only",
            "recreational_only",
            "none",
            name="cannabis_use_frequency_enum"
        ),
        nullable=True,
    )

      
    cannabis_use_characterization = db.Column(
            db.Text,
            nullable=True,
            doc="Free-text description of relationship with cannabis, e.g., 'Daily smoker for 10 years, currently microdosing for pain.'"
        )


    # ------------------
    # Relationships
    # ------------------
    user = db.relationship(
    "User",
    back_populates="patient_profile",
    foreign_keys=[user_sid],  # <-- reference to the UUID column
    uselist=False,
)
    provider = db.relationship("Provider", back_populates="patients")

    conditions = relationship(
        "PatientCondition",
        back_populates="patient",
        cascade="all, delete-orphan",
            lazy="joined",
        )
    
    # In PatientProfile
    dispensary_links = db.relationship(
        "PatientDispensary",
        back_populates="patient",
        cascade="all, delete-orphan",
        overlaps="dispensaries,patients"
    )
    dispensaries = db.relationship(
        "Dispensary",
        secondary="patient_dispensaries",
        back_populates="patients",
        viewonly=True,
        overlaps="dispensary_links,patient_links"
    )
    wellness_checks = relationship(  
        "WellnessCheck",
        back_populates="patient",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    
    comparisons = relationship(
        "WellnessComparisonsCache",
        back_populates="patient",
        cascade="all, delete-orphan",
    )
    
    medications_list = db.relationship(
        "PatientMedication",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    medical_history = db.relationship(
        "PatientMedicalHistory",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    # Relationship to PatientPreference
    preferences = db.relationship(
        "PatientPreference",
        back_populates="patient_profile",
        uselist=False  # if one-to-one, otherwise remove
    )
    
    # Inside PatientProfile
    current_products = db.relationship(
        "CurrentPatientProductUsage",
        back_populates="patient",
        cascade="all, delete-orphan"
    )

    product_history = db.relationship(
        "PatientProductUsage",
        back_populates="patient",
        cascade="all, delete-orphan"
    )

    grassroots_submissions = db.relationship("GrassrootsProduct", back_populates="submitted_by")
    
    latest_ai_recommendation = db.relationship(
        "LatestAIRecommendation",
        back_populates="patient",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True
    )


    
    # ------------------
    # Properties
    # ------------------

    @property
    def dispensary_products(self):
        """Return approved products available through the patient's dispensaries."""
        products = []
        for d in self.dispensaries:
            products.extend(
                [p for p in getattr(d, "products", []) if p.status == ProductStatus.APPROVED.value]
            )
        return products

   
    # Affliction / Condition Helpers
    # ------------------

    @hybrid_property
    def afflictions_map(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for c in self.conditions or []:
            if c.affliction:
                out[c.affliction] = c.severity_level or ""
        return out

    def set_afflictions_with_severity(self, name_to_level: Dict[str, str]) -> None:
        """Assign conditions with specified severity levels."""
        names = list(name_to_level.keys()) if name_to_level else []
        existing_by_name = {c.affliction: c for c in (self.conditions or [])}

        try:
            levels = set(_severity_levels())
        except Exception:
            levels = {"I", "II", "III", "IV", "V"}

        desired: Dict[str, str] = {}
        for raw_name, raw_level in (name_to_level or {}).items():
            name = (raw_name or "").strip()
            lvl = (raw_level or "").strip()
            if not name:
                continue
            if lvl not in levels:
                lvl = next(iter(levels)) if levels else "I"
            desired[name] = lvl

        keep: Dict[str, "PatientCondition"] = {}
        for name, lvl in desired.items():
            row = existing_by_name.get(name)
            if not row:
                row = PatientCondition(patient=self, affliction=name, severity_level=lvl)
                db.session.add(row)
            else:
                row.severity_level = lvl
                row.updated_at = datetime.utcnow()
            keep[name] = row

        for name, row in list(existing_by_name.items()):
            if name not in desired:
                self.conditions.remove(row)

    def set_afflictions_list(self, names: List[str], default_level: Optional[str] = None) -> None:
        """Assign conditions with default severity level if none specified."""
        try:
            default_lvl = default_level or (_severity_levels()[0] if _severity_levels() else "I")
        except Exception:
            default_lvl = default_level or "I"
        mapping = {str(n).strip(): default_lvl for n in (names or []) if str(n).strip()}
        self.set_afflictions_with_severity(mapping)
        
    @property
    def has_checkin(self) -> bool:
        """Returns True if the patient has completed any wellness check."""
        return self.wellness_check_id is not None or bool(self.product_interactions)

    @property
    def is_onboarded(self) -> bool:
        """Returns True if onboarding flag is set or a check-in exists."""
        return self.onboarding_complete or self.has_checkin

    # ------------------
    # Wellness Check Accessors
    # ------------------

    @property
    def last_wellness_check(self):
        """Return the most recent WellnessCheck for the patient."""
        from app.models import WellnessCheck
        return (
            WellnessCheck.query
            .filter_by(sid=self.sid)
            .order_by(WellnessCheck.checkin_date.desc())
            .first()
        )
        
    @property
    def last_qol_date(self) -> Optional[datetime]:
        """Return the date of the most recent wellness check."""
        last = self.last_wellness_check
        return last.checkin_date if last else None
    
    
    @property
    def last_slider_scores(self) -> dict:
        """Return last recorded wellness slider scores."""
        wc = self.last_wellness_check
        if not wc:
            return {}
        return {
            "pain": wc.pain_level,
            "energy": wc.energy_level,
            "clarity": wc.clarity_level,
            "appetite": wc.appetite_level,
            "mood": wc.mood_level,
            "sleep": wc.sleep_level,
        }

    @property
    def last_qol_score(self) -> Optional[float]:
        """Compute overall QoL score from the most recent check."""
        sliders = self.last_slider_scores
        if not sliders:
            return None
        values = [v for v in sliders.values() if v is not None]
        if not values:
            return None
        return sum(values) / len(values)

    @property
    def last_qol_delta(self) -> Optional[float]:
        """Return % change in overall QoL vs previous wellness check."""
        from app.models import WellnessCheck
        last = self.last_wellness_check
        if not last:
            return None
        prev = (
            WellnessCheck.query
            .filter(WellnessCheck.sid == self.sid, WellnessCheck.id < last.id)
            .order_by(WellnessCheck.last_checkin_date.desc())
            .first()
        )
        if not prev:
            return None
        last_score = self.last_qol_score
        prev_score = (
            sum(
                v for v in [
                    prev.pain_level,
                    prev.energy_level,
                    prev.clarity_level,
                    prev.appetite_level,
                    prev.mood_level,
                    prev.sleep_level,
                ] if v is not None
            ) / 5
        )
        if prev_score == 0:
            return None
        return ((last_score - prev_score) / prev_score) * 100

    # ------------------
    # Product Attribution Helpers
    # ------------------

    @property
    def product_attributions(self) -> dict[int, float]:
        """Return dict mapping product_id -> QoL contribution (positive only)."""
        wc = self.last_wellness_check
        if not wc:
            return {}
        attributions = {}
        for attr in wc.attributions:
            if attr.overall_pct and attr.overall_pct > 0:
                attributions[attr.product_id] = attr.overall_pct
        return attributions

    @property
    def products_with_positive_qol(self) -> list[int]:
        """Return list of product IDs that improved QoL."""
        return list(self.product_attributions.keys())

    @property
    def product_qol_map(self) -> dict[int, dict]:
        """Detailed breakdown of product QoL contributions."""
        wc = self.last_wellness_check
        if not wc:
            return {}
        data = {}
        for attr in wc.attributions:
            data[attr.product_id] = {
                "overall": attr.overall_pct,
                "pain": attr.pain_pct,
                "mood": attr.mood_pct,
                "energy": attr.energy_pct,
                "clarity": attr.clarity_pct,
                "appetite": attr.appetite_pct,
                "sleep": attr.sleep_pct,
            }
        return data

    # ------------------
    # Representation
    # ------------------
    def __repr__(self):
        return f"<PatientProfile sid={self.sid} user_id={self.user_id}>"

class PatientMedication(db.Model):
    __tablename__ = "patient_medication"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String, db.ForeignKey("patient_profile.sid"), nullable=False)

    medication_name = db.Column(db.String(120), nullable=False)
    dosage = db.Column(db.String(50), nullable=True)          # e.g., "10 mg"
    frequency = db.Column(db.String(50), nullable=True)       # e.g., "Twice daily"
    route = db.Column(db.String(50), nullable=True)           # e.g., "Oral", "Topical"
    prescribed_by = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = db.relationship("PatientProfile", back_populates="medications_list")


class PatientMedicalHistory(db.Model):
    __tablename__ = "patient_medical_history"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String, db.ForeignKey("patient_profile.sid"), nullable=False)

    condition_name = db.Column(db.String(120), nullable=False)   # e.g., "Hypertension"
    diagnosis_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), nullable=True)             # e.g., "Active", "Resolved"
    notes = db.Column(db.Text, nullable=True)

    # For allergies or sensitivities
    is_allergy = db.Column(db.Boolean, default=False)
    reaction = db.Column(db.String(255), nullable=True)          # e.g., "Rash", "Nausea"

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = db.relationship("PatientProfile", back_populates="medical_history")


 # ======================
# Favorites (Enterprise bookmarks)
# ======================
class FavoriteEnterprise(db.Model):
    """
    A user bookmarking an enterprise account.
    If your 'enterprise' is represented by a User with a specific role
    (e.g., UserRoleEnum.ENTERPRISE), we store a FK to user.id.
    Adjust FK if you have a dedicated Enterprise table.
    """
    __tablename__ = "favorite_enterprise"

    id = db.Column(Integer, primary_key=True)

    # Who favorited
    user_id = db.Column(
        Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which enterprise (defaults to User.id; change if you have Enterprise table)
    enterprise_user_id = db.Column(
        Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("favorite_enterprises", lazy="dynamic", cascade="all, delete-orphan"),
    )
    enterprise_user = relationship("User", foreign_keys=[enterprise_user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "enterprise_user_id", name="uq_favorite_enterprise_once"),
        CheckConstraint("user_id <> enterprise_user_id", name="ck_favorite_enterprise_not_self"),
        Index("ix_fav_enterprise_user_target", "user_id", "enterprise_user_id"),
    )

    def __repr__(self) -> str:
        return f"<FavoriteEnterprise by={self.user_id} -> enterprise={self.enterprise_user_id}>"

        
# ======================
# PatientCondition
# ======================
class PatientCondition(db.Model, TimestampMixin):
    __tablename__ = "patient_condition"

    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid", ondelete="CASCADE"), nullable=False, index=True)
    condition = db.Column(db.String(255), nullable=False)
    stage = db.Column(db.String(5), nullable=False, default='I')  # or Integer if you prefer

    __table_args__ = (
        UniqueConstraint("sid", "condition", name="uq_patient_condition"),
        Index("ix_condition_patient_condition", "sid", "condition"),
    )

    patient = relationship("PatientProfile", back_populates="conditions")

    # --- Aliases ---
    @property
    def severity_level(self):
        return self.stage

    @severity_level.setter
    def severity_level(self, value):
        self.stage = value

    @property
    def affliction(self):
        return self.condition

    @affliction.setter
    def affliction(self, value):
        self.condition = value

    def __repr__(self):
        return f"<PatientCondition id={self.id} sid={self.sid} condition={self.condition!r} stage={self.stage!r}>"

    # ======================
# PatientPreference
# ======================
class PatientPreference(db.Model, TimestampMixin):
    __tablename__ = "patient_preferences"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), nullable=False)
       
     
    patient_profile = db.relationship("PatientProfile", back_populates="preferences")
         

    strain_type = db.Column(db.String(50), nullable=True)
    company_name = db.Column(db.String(120), nullable=True)
    thc_min = db.Column(db.Float, nullable=True)
    thc_max = db.Column(db.Float, nullable=True)
    application_method = db.Column(db.String(50), nullable=True)
 

# ======================
# Supplier / Provider / Dispensary
# ======================

class SupplierProfile(db.Model):
    __tablename__ = "supplier_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    company_name = db.Column(db.String(255), nullable=False)
    product_categories = db.Column(db.Text)
    contact_email = db.Column(db.String(255))
    website = db.Column(db.String(255))

    # Address Fields
    street_address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(64), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)

    logo_file_id = db.Column(db.Integer, db.ForeignKey("uploaded_file.id"), nullable=True)
    logo_file = db.relationship("UploadedFile")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="supplier_profile")

    upvotes = db.relationship(
        "Upvote",
        primaryjoin=lambda: and_(
            foreign(Upvote.target_id) == SupplierProfile.id,
            Upvote.target_type == "supplier"
        ),
        viewonly=True,
        lazy="dynamic"
    )

    @property
    def logo_url(self) -> str | None:
        if self.logo_file and getattr(self.logo_file, "filepath", None):
            return url_for("static", filename=self.logo_file.filepath)
        return None

    @property
    def upvote_count(self) -> int:
        return self.upvotes.count()


class Provider(db.Model):
    __tablename__ = "provider"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    name = db.Column(db.String(128))
    email = db.Column(db.String(128), unique=True)
    clinic_name = db.Column(db.String(128))
    education = db.Column(db.String(255))
    years_experience = db.Column(db.Integer)

    # Address Fields
    street_address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(64), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)

    logo_file_id = db.Column(db.Integer, db.ForeignKey("uploaded_file.id"), nullable=True)
    logo_file = db.relationship("UploadedFile")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="provider_profile")
    patients = db.relationship("PatientProfile", back_populates="provider", cascade="all, delete-orphan")
    products = db.relationship("Product", back_populates="provider", cascade="all, delete-orphan")

    upvotes = db.relationship(
        "Upvote",
        primaryjoin=lambda: and_(
            foreign(Upvote.target_id) == Provider.id,
            Upvote.target_type == "provider"
        ),
        viewonly=True,
        lazy="dynamic"
    )

    @property
    def logo_url(self) -> str | None:
        if self.logo_file and getattr(self.logo_file, "filepath", None):
            return url_for("static", filename=self.logo_file.filepath)
        return None

    @property
    def upvote_count(self) -> int:
        return self.upvotes.count()


class Dispensary(db.Model):
    __tablename__ = "dispensary"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)


    name = db.Column(db.String(128), nullable=False)
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(128))
    website = db.Column(db.String(255))

    street_address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(128), nullable=False)
    state = db.Column(db.String(64), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True, index=True)

    logo_file_id = db.Column(db.Integer, db.ForeignKey("uploaded_file.id"))
    logo_file = db.relationship("UploadedFile")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="dispensary_profile")
    
    patient_links = db.relationship(
        "PatientDispensary",
        back_populates="dispensary",
        cascade="all, delete-orphan",
        overlaps="dispensaries,patients"
    )
    patients = db.relationship(
        "PatientProfile",
        secondary="patient_dispensaries",
        back_populates="dispensaries",
        viewonly=True,
        overlaps="dispensary_links,patient_links"
    )
    
    @property
    def logo_url(self) -> str | None:
        if self.logo_file and getattr(self.logo_file, "filepath", None):
            return url_for("static", filename=self.logo_file.filepath)
        return None

    @property
    def upvote_count(self) -> int:
        return Upvote.query.filter_by(target_id=self.id, target_type="dispensary").count()


class DispensaryNote(db.Model):
    __tablename__ = "dispensary_note"

    id = db.Column(db.Integer, primary_key=True)
    dispensary_id = db.Column(db.Integer, db.ForeignKey("dispensary.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    dispensary = db.relationship("Dispensary", backref="notes")


# ======================
# PatientDispensary (assoc table)
# ======================
class PatientDispensary(db.Model, TimestampMixin):
    __tablename__ = "patient_dispensaries"

    sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), primary_key=True)
    dispensary_id = db.Column(db.Integer, db.ForeignKey("dispensary.id"), primary_key=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

   # In PatientDispensary
    patient = db.relationship(
        "PatientProfile",
        back_populates="dispensary_links",
        overlaps="dispensaries,patients"
    )
    dispensary = db.relationship(
        "Dispensary",
        back_populates="patient_links",
        overlaps="dispensaries,patients"
    )
    
# ======================
# Products & Chemistry
# ======================
class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(140), nullable=False)
    manufacturer = db.Column(db.String(140), nullable=True)
    brand = db.Column(db.String(120), nullable=True)  # ✅ new field
    description = db.Column(db.Text)
    category = db.Column(db.String(80))
    image_path = db.Column(db.String(255))
    status = db.Column(db.String(32), default=ProductStatus.ENTERPRISE_PENDING.value, nullable=False)
    approval_status = db.synonym("status")
    submission_type = db.Column(db.String(20), default=SubmissionType.ENTERPRISE.value, nullable=False)

    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    submitted_by_sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), nullable=True, default=lambda: str(uuid.uuid4()))

    provider_id = db.Column(db.Integer, db.ForeignKey("provider.id"), nullable=True)

    # Relationships
    profile = db.relationship("ProductChemProfile", uselist=False, back_populates="product", cascade="all, delete-orphan")
    terpenes = db.relationship("ProductTerpene", back_populates="product", cascade="all, delete-orphan")
    inventory_reports = db.relationship("InventoryReport", back_populates="product", lazy="dynamic", cascade="all, delete-orphan")
    provider = db.relationship("Provider", back_populates="products")
    aggregate_score = db.relationship("ProductAggregateScore", back_populates="product", uselist=False, cascade="all, delete-orphan")
    wellness_attributions = db.relationship("WellnessAttribution", back_populates="product", cascade="all, delete-orphan", passive_deletes=True)


    # -------------------------
    # Typeahead + search helper
    # -------------------------
    @staticmethod
    def get_typeahead_options(query=None, limit=25):
        """Returns filtered product names for typeahead."""
        q = Product.query.filter_by(status="approved")

        if query:
            q = q.filter(Product.name.ilike(f"%{query}%"))

        results = q.order_by(Product.name.asc()).limit(limit).all()

        return [{"id": p.id, "name": p.name} for p in results]        

    @property
    def name(self):
        return self.product_name

    def __repr__(self):
        return f"<Product id={self.id} name={self.product_name}>"


class ProductChemProfile(db.Model):
    __tablename__ = "product_chem_profile"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    strain = db.Column(db.String(100), nullable=True)  # store the strain name
    chem_type = db.Column(db.String(20), default="n/a")  # indica|sativa|hybrid|n/a
    thc_percent = db.Column(db.Float)
    cbd_percent = db.Column(db.Float)
    cbn_percent = db.Column(db.Float)

    product = db.relationship("Product", back_populates="profile")


class ProductTerpene(db.Model):
    __tablename__ = "product_terpene"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)
    percent = db.Column(db.Float, nullable=True)

    product = db.relationship("Product", back_populates="terpenes")


class GrassrootsProduct(db.Model):
    """Patient-submitted product placeholder."""
    __tablename__ = "grassroots_product"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(140), nullable=False)
    manufacturer = db.Column(db.String(140), nullable=True)
    brand = db.Column(db.String(120), nullable=True)  # ✅ new field
    description = db.Column(db.Text)
    category = db.Column(db.String(80))
    image_path = db.Column(db.String(255))
    status = db.Column(db.String(32), default=ProductStatus.GRASSROOTS_PENDING.value, nullable=False)
    submitted_by_sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), nullable=True, default=lambda: str(uuid.uuid4()))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    submitted_by = db.relationship("PatientProfile", back_populates="grassroots_submissions")

# -------------------------
    # Patient Usage Models
    # -------------------------
class CurrentPatientProductUsage(db.Model, TimestampMixin):
    __tablename__ = "current_patient_product_usage"
    __table_args__ = (Index("ix_usage_sid_product", "sid", "product_id"),)

    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(
        db.String(36),
        db.ForeignKey("patient_profile.sid"),
        nullable=False,
        default=lambda: str(uuid.uuid4())
    )
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    grassroots_id = db.Column(db.Integer, db.ForeignKey("grassroots_product.id"), nullable=True)
    start_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    dosage_amount = db.Column(db.Float, nullable=True)
    dosage_unit = db.Column(db.String(20), nullable=True)
    frequency = db.Column(db.String(50), nullable=True)

    patient = db.relationship(
        "PatientProfile",
        back_populates="current_products",
        primaryjoin="foreign(CurrentPatientProductUsage.sid)==PatientProfile.sid"
    )
    product = db.relationship("Product", foreign_keys=[product_id])
    grassroots = db.relationship("GrassrootsProduct")

    # ---------- Add this method ----------
    @classmethod
    def get_current_for_patient(cls, sid):
        """Return all current product usage rows for a given patient SID."""
        return cls.query.filter_by(sid=sid).all()
        


# ======================
# Patient Product Usage
# ======================
class PatientProductUsage(db.Model):
    __tablename__ = "patient_product_usage"

    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), nullable=False, default=lambda: str(uuid.uuid4()))
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    grassroots_id = db.Column(db.Integer, db.ForeignKey("grassroots_product.id"), nullable=True)
    start_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    replacement_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    still_using = db.Column(db.Boolean, default=True, nullable=False)
    
    # --- Historical dosage/frequency tracking ---
    dosage_amount = db.Column(db.Float, nullable=True)  # e.g., 5 mg
    dosage_unit = db.Column(db.String(20), nullable=True)  # e.g., 'mg', 'ml', 'puffs'
    frequency = db.Column(db.String(50), nullable=True)  # e.g., 'twice daily', 'as needed'

    patient = db.relationship(
        "PatientProfile",
        back_populates="product_history",
        primaryjoin="foreign(PatientProductUsage.sid)==PatientProfile.sid"
    )
    product = db.relationship("Product", foreign_keys=[product_id])
    grassroots = db.relationship("GrassrootsProduct")
    replacement = db.relationship("Product", foreign_keys=[replacement_id])



# ======================
# Inventory Reporting
# ======================

class InventoryReport(db.Model):
    __tablename__ = "inventory_report"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, nullable=False)
    reporter_type = db.Column(db.String(50), nullable=False)  # "dispensary" or "supplier"
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    reported_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product", back_populates="inventory_reports")

    dispensary = db.relationship(
        "Dispensary",
        primaryjoin="and_(InventoryReport.reporter_id==foreign(Dispensary.id), InventoryReport.reporter_type=='dispensary')",
        viewonly=True,
    )
    supplier = db.relationship(
        "SupplierProfile",
        primaryjoin="and_(InventoryReport.reporter_id==foreign(SupplierProfile.id), InventoryReport.reporter_type=='supplier')",
        viewonly=True,
    )

    __mapper_args__ = {
        'polymorphic_on': reporter_type,
        'polymorphic_identity': 'inventory_report'
    }


# ======================
# Affliction Suggestions
# ======================
class AfflictionSuggestion(db.Model):
    __tablename__ = "affliction_suggestion"

    id = db.Column(Integer, primary_key=True)
    submitted_by_id = db.Column(Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    product_id = db.Column(Integer, db.ForeignKey("product.id"), nullable=True, index=True)
    affliction = db.Column(String(64), nullable=False)
    rating = db.Column(Float, nullable=True)
    notes = db.Column(Text, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[submitted_by_id], backref=db.backref("affliction_suggestions", lazy="dynamic"))
    product = relationship("Product", foreign_keys=[product_id], backref=db.backref("affliction_suggestions", lazy="dynamic"))

    __table_args__ = (
        CheckConstraint("(rating IS NULL) OR (rating >= 0.0 AND rating <= 10.0)", name="ck_afflict_suggestion_rating_0_10"),
        UniqueConstraint("submitted_by_id", "product_id", "affliction", name="uq_afflict_suggestion_once"),
    )


# ======================
# Notes
# ======================
class PatientNote(db.Model):
    __tablename__ = "patient_note"

    id = db.Column(Integer, primary_key=True)
    sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid"), nullable=False, default=lambda: str(uuid.uuid4()))
    product_id = db.Column(Integer, db.ForeignKey("product.id"), nullable=False)
    content = db.Column(Text, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow, nullable=False)

    patient_profile = relationship("PatientProfile", primaryjoin="foreign(PatientNote.sid)==PatientProfile.sid")
    product = relationship("Product", backref="patient_notes")


# ======================
# Social graph (friendships)
# ======================
class Friends(db.Model):
    __tablename__ = "user_friends"

    user_id = db.Column(Integer, db.ForeignKey("user.id"), primary_key=True)
    friend_id = db.Column(Integer, db.ForeignKey("user.id"), primary_key=True)
    created_at = db.Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], backref=db.backref("friend_links", lazy="dynamic"))
    friend = relationship("User", foreign_keys=[friend_id])

    def __repr__(self) -> str:
        return f"<Friends {self.user_id} <-> {self.friend_id}>"

# ======================
# Upvotes (derived from positive wellness attribution)
# ======================
class Upvote(db.Model):
    __tablename__ = "upvote"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    # Target can be product/provider/supplier/dispensary
    target_type = db.Column(db.String(32), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)

    # QoL improvement (0?100%) or raw slider-based effectiveness
    qol_improvement = db.Column(db.Float, nullable=True, index=True)

    # Reference to originating wellness check (optional for non-product targets)
    wellness_check_id = db.Column(db.Integer, db.ForeignKey("wellness_check.id"), nullable=True)
    wellness_check = relationship("WellnessCheck", backref=db.backref("upvotes", lazy="dynamic"))

    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_upvote_user_target"),
        CheckConstraint(
            "target_type IN ('product','provider','supplier','dispensary')",
            name="ck_upvote_target_type",
        ),
        Index("ix_upvote_target", "target_type", "target_id"),
    )

    user = relationship("User", back_populates="upvotes")

    def __repr__(self):
        return (
            f"<Upvote id={self.id} user_id={self.user_id} "
            f"target={self.target_type}:{self.target_id} "
            f"qol={self.qol_improvement}>"
        )

# ======================
# WellnessCheck (single canonical table)
# ======================
class WellnessCheck(db.Model, TimestampMixin):
    __tablename__ = "wellness_check"
    __table_args__ = (Index("ix_wellness_sid_date", "sid", "checkin_date"),)

    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(
        db.String(36),
        db.ForeignKey("patient_profile.sid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checkin_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pain_level = db.Column(db.Integer)
    mood_level = db.Column(db.Integer)
    energy_level = db.Column(db.Integer)
    clarity_level = db.Column(db.Integer)
    appetite_level = db.Column(db.Integer)
    sleep_level = db.Column(db.Integer)
    notes = db.Column(db.Text)

    heart_rate = db.Column(db.Integer, nullable=True)
    bp_systolic = db.Column(db.Integer, nullable=True)
    bp_diastolic = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        """Convert wellness check object into a JSON-safe dictionary."""
        return {
            "id": self.id,
            "sid": str(self.sid),
            "checkin_date": self.checkin_date.isoformat() if self.checkin_date else None,
            "pain_level": self.pain_level,
            "mood_level": self.mood_level,
            "energy_level": self.energy_level,
            "clarity_level": self.clarity_level,
            "appetite_level": self.appetite_level,
            "sleep_level": self.sleep_level,
            "notes": self.notes or "",
            "heart_rate": self.heart_rate,
            "bp_systolic": self.bp_systolic,
            "bp_diastolic": self.bp_diastolic,
        }
            
    # The user-level answer: "how much of your QoL change is due to cannabis?" (0..100)
    cannabis_pct = db.Column(db.Float, nullable=True)

    # overall numeric QoL (0..100) computed and cached
    overall_qol = db.Column(db.Float, nullable=True)
    pct_change_qol = db.Column(db.Float, nullable=True)

    patient = relationship("PatientProfile", back_populates="wellness_checks")
    attributions = relationship("WellnessAttribution", back_populates="wellness_check", cascade="all, delete-orphan")

    def compute_overall_qol(self) -> Optional[float]:
        vals = {
            "pain_level": self.pain_level,
            "mood_level": self.mood_level,
            "energy_level": self.energy_level,
            "clarity_level": self.clarity_level,
            "appetite_level": self.appetite_level,
            "sleep_level": self.sleep_level,
        }
        self.overall_qol = _calc_qol_from_sliders(vals)
        return self.overall_qol

# ======================
# WellnessAttribution
# ======================
class WellnessAttribution(db.Model, TimestampMixin):
    __tablename__ = "wellness_attribution"

    id = db.Column(db.Integer, primary_key=True)
    wellness_check_id = db.Column(db.Integer, db.ForeignKey("wellness_check.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id", ondelete="CASCADE"), nullable=False)

    # per-metric percent attribution (0..100) - the fraction of that metric improvement assigned to this product
    pain_pct = db.Column(db.Float, nullable=True)
    mood_pct = db.Column(db.Float, nullable=True)
    energy_pct = db.Column(db.Float, nullable=True)
    clarity_pct = db.Column(db.Float, nullable=True)
    appetite_pct = db.Column(db.Float, nullable=True)
    sleep_pct = db.Column(db.Float, nullable=True)

    # derived numbers
    derived_qol = db.Column(db.Float, nullable=True)   # raw QoL contribution (same units as overall_qol)
    overall_pct = db.Column(db.Float, nullable=True)   # percent of QoL change (e.g., 3.5 => 3.5% improvement)

    wellness_check = relationship("WellnessCheck", back_populates="attributions")
    product = relationship("Product", back_populates="wellness_attributions")

    def __repr__(self):
        return f"<WellnessAttribution check={self.wellness_check_id} prod={self.product_id} qol={self.derived_qol}>"

# Event listener: compute derived_qol before insert/update
@event.listens_for(WellnessAttribution, "before_insert")
@event.listens_for(WellnessAttribution, "before_update")
def _compute_derived_qol(mapper, connection, target: WellnessAttribution):
    try:
        # fetch related wellness_check (prefer loaded relationship)
        wc = getattr(target, "wellness_check", None)
        if wc is None and target.wellness_check_id:
            wc = db.session.get(WellnessCheck, target.wellness_check_id)

        if not wc:
            return

        def safe_mul(val, pct):
            return (val or 0) * (pct or 0) / 100.0

        total = sum([
            safe_mul(11 - (wc.pain_level or 6), target.pain_pct),
            safe_mul(wc.mood_level, target.mood_pct),
            safe_mul(wc.energy_level, target.energy_pct),
            safe_mul(wc.clarity_level, target.clarity_pct),
            safe_mul(wc.appetite_level, target.appetite_pct),
            safe_mul(wc.sleep_level, target.sleep_pct),
        ])

        # derived_qol is the absolute QoL contribution in slider-units; convert to percent consistent with overall_qol scale
        # We adopt: derived_pct = total / 60 * 100  (same as slider->QOL mapping)
        derived_pct = (total / 60.0) * 100.0 if total is not None else None
        target.derived_qol = derived_pct
        target.overall_pct = derived_pct

        # also compute and cache the wellness_check overall QoL if not already set
        try:
            wc.compute_overall_qol()
            # compute pct_change_qol by looking up previous check if exists
            prev = (
                WellnessCheck.query
                .filter(WellnessCheck.sid == wc.sid, WellnessCheck.id < wc.id)
                .order_by(WellnessCheck.checkin_date.desc())
                .first()
            )
            if prev and prev.overall_qol is not None:
                if prev.overall_qol != 0:
                    wc.pct_change_qol = ((wc.overall_qol - prev.overall_qol) / prev.overall_qol) * 100.0
        except Exception:
            pass

    except Exception:
        # defensive: do not raise to avoid failing inserts from UI
        try:
            import logging
            logging.getLogger(__name__).exception("compute_derived_qol failed")
        except Exception:
            pass

# Event listener: update product aggregate after insert/update/delete
@event.listens_for(WellnessAttribution, "after_insert")
@event.listens_for(WellnessAttribution, "after_update")
@event.listens_for(WellnessAttribution, "after_delete")
def _update_product_aggregate(mapper, connection, target: WellnessAttribution):
    try:
        session = object_session(target) or db.session
        product_id = target.product_id
        # gather all overall_pct for this product
        rows = session.query(WellnessAttribution.overall_pct).filter(
            WellnessAttribution.product_id == product_id,
            WellnessAttribution.overall_pct != None
        ).all()
        qols = [r[0] for r in rows]
        if qols:
            total_votes = len(qols)
            avg_qol = sum(qols) / total_votes
            min_qol = min(qols)
            max_qol = max(qols)
        else:
            total_votes = 0
            avg_qol = None
            min_qol = None
            max_qol = None

        agg = session.query(ProductAggregateScore).filter_by(product_id=product_id).first()
        if not agg:
            agg = ProductAggregateScore(product_id=product_id)
            session.add(agg)

        agg.total_votes = total_votes
        agg.avg_qol = avg_qol
        agg.min_qol = min_qol
        agg.max_qol = max_qol
        agg.updated_at = datetime.utcnow()
        # flush but don't commit here
        try:
            session.flush()
        except Exception:
            pass

    except Exception:
        try:
            import logging
            logging.getLogger(__name__).exception("update_product_aggregate failed")
        except Exception:
            pass

# ======================
# ProductAggregateScore
# ======================
class ProductAggregateScore(db.Model, TimestampMixin):
    __tablename__ = "product_aggregate_score"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id", ondelete="CASCADE"), unique=True, nullable=False)

    total_votes = db.Column(db.Integer, nullable=False, default=0)
    avg_qol = db.Column(db.Float, nullable=True)
    min_qol = db.Column(db.Float, nullable=True)
    max_qol = db.Column(db.Float, nullable=True)

    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    product = db.relationship("Product", back_populates="aggregate_score", uselist=False)

# ======================
# WellnessComparisonsCache
# ======================
class WellnessComparisonsCache(db.Model, TimestampMixin):
    __tablename__ = "wellness_comparisons_cache"
    __table_args__ = (Index("ix_comparison_sid_metric", "sid", "metric"),)

    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(36), db.ForeignKey("patient_profile.sid", ondelete="CASCADE"), nullable=False)
    metric = db.Column(db.String(50))
    user_avg = db.Column(db.Float)
    group_avg = db.Column(db.Float)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship("PatientProfile", back_populates="comparisons")


# ======================
# Latest AI Recommendation
# ======================
class LatestAIRecommendation(db.Model):
    __tablename__ = "latest_ai_recommendations"

    id = db.Column(db.Integer, primary_key=True)
    patient_sid = db.Column(
        db.String(36),
        db.ForeignKey("patient_profile.sid", name="fk_latest_ai_patient_sid"),
        nullable=False,
        unique=True
    )
    ai_feedback = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    patient = db.relationship("PatientProfile", back_populates="latest_ai_recommendation")

    def __repr__(self):
        return f"<LatestAIRecommendation patient_sid={self.patient_sid} updated_at={self.updated_at}>"


# ======================
# Audit / Product Submissions / Moderation
# ======================
class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(String(100), nullable=False)
    target_type = db.Column(String(50), nullable=False)
    target_id = db.Column(Integer, nullable=True)
    timestamp = db.Column(DateTime, default=datetime.utcnow, nullable=False)
    details = db.Column(Text, nullable=True)

    user = relationship("User", backref="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.target_type} {self.target_id} by {self.user_id}>"

    
class ProductSubmission(db.Model):  
    __tablename__ = "product_submission"

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(128), nullable=False)
    description = db.Column(Text)
    application_method = db.Column(String(64), nullable=False)
    thc_content = db.Column(Float)
    cbd_content = db.Column(Float)
    cbn_content = db.Column(Float)
    manufacturer_claim = db.Column(Text, nullable=True)
    condition = db.Column(String(64), nullable=True)  # formerly suggested_treatment / affliction
    retail_price = db.Column(Numeric(10, 2))
    image_path = db.Column(String(256))
    submitted_by_id = db.Column(Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(
        SAEnum("pending", "approved", "rejected", name="submission_status_enum"),
        default="pending",
        nullable=False,
    )
    rejection_reason = db.Column(String(256))
    last_checkin_date = db.Column(DateTime, default=datetime.utcnow, nullable=False)

    submitted_by = relationship("User", backref="submitted_products")

    @db.validates("application_method")
    def _validate_app_method(self, key, value):
        if value not in APPLICATION_METHODS:
            raise ValueError(f"Invalid application method: {value}")
        return value

    @db.validates("condition")
    def _validate_condition(self, key, value):
        if value and value not in AFFLICTION_LIST:
            raise ValueError(f"Invalid condition/affliction: {value}")
        return value

    # Convenience property to use either term in code
    @property
    def affliction(self):
        return self.condition

    @affliction.setter
    def affliction(self, value):
        self.condition = value

# ======================
# Affliction (Dynamic)
# ======================
class Affliction(db.Model):
    __tablename__ = "affliction"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @staticmethod
    def seed_defaults():
        """Seed the DB with default afflictions if none exist."""
        defaults = [
            "Chronic Pain", "Anxiety", "Depression", "Insomnia", "Nausea",
            "Seizures", "Appetite Loss", "Inflammation", "Stress",
            "PTSD", "Muscle Spasms",
        ]
        if not Affliction.query.count():
            for name in defaults:
                db.session.add(Affliction(name=name))
            db.session.commit()

    @staticmethod
    def get_typeahead_options(query=None, limit=25):
        q = Affliction.query.filter(Affliction.is_active.is_(True))
        if query:
            q = q.filter(Affliction.name.ilike(f"%{query}%"))
        return [{"id": a.id, "name": a.name} for a in q.limit(limit).all()]

    def __repr__(self):
        return f"<Affliction {self.name}>"

class ModerationReport(db.Model):
    __tablename__ = "moderation_report"

    id = db.Column(Integer, primary_key=True)
    reporter_id = db.Column(Integer, db.ForeignKey("user.id"), nullable=False)
    reporter_role = db.Column(SAEnum(UserRoleEnum), nullable=False)
    target_type = db.Column(String(64), nullable=False)
    target_id = db.Column(Integer, nullable=False)
    reason = db.Column(String(256), nullable=True)
    details = db.Column(Text, nullable=True)
    created_at = db.Column(DateTime, default=func.now(), nullable=False)
    status = db.Column(String(32), default="open")
    reviewed_by = db.Column(Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(DateTime, nullable=True)
    resolution_notes = db.Column(Text, nullable=True)


# ======================
# Communications / Messaging
# ======================
class Conversation(db.Model):
    __tablename__ = "conversation"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=True)
    is_group = Column(Boolean, default=False, nullable=False)
    is_broadcast = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # One-to-many relationship with messages
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation {self.id} {self.title or 'Untitled'}>"

class Message(db.Model):
    __tablename__ = "message"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversation.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to Conversation
    conversation = relationship("Conversation", back_populates="messages")
    receipts = relationship("MessageReceipt", back_populates="message", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Message {self.id} in Conversation {self.conversation_id}>"

class MessageReceipt(db.Model):
    __tablename__ = "message_receipt"   

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("message.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)

    message = relationship("Message", back_populates="receipts")

    def __repr__(self):
        return f"<MessageReceipt {self.id} for Message {self.message_id}>"

class ThemeConfig(db.Model):
    __tablename__ = 'theme_config'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, default='default')
    industrial_color = db.Column(db.String(20), default='#4a4a4a')
    callout_color = db.Column(db.String(20), default='#ffa500')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
