"""Kushwell moderation reasons.

This module defines an enumeration of reasons a product or submission might be
flagged by the moderation system.  It mirrors the definitions supplied by
the user and can be imported wherever moderation logic is needed.

Usage::

    from app.models.moderation import ModerationReason

    if form.reason == ModerationReason.PRODUCT_UNAVAILABLE:
        # handle unavailable product

"""

import enum


class ModerationReason(enum.Enum):
    PRODUCT_UNAVAILABLE = "product_unavailable"
    DUPLICATE_ENTRY = "duplicate_entry"
    NO_EVIDENCE_OF_BENEFIT = "no_evidence_of_benefit"
    PHISHING_SPAM = "phishing_spam"
    BULLYING_OR_HARASSMENT = "bullying_or_harassment"
    VIOLATES_TERMS = "violates_terms"
    MISLEADING_CLAIMS = "misleading_claims"
    INAPPROPRIATE_CONTENT = "inappropriate_content"


