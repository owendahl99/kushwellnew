# FILE: app/constants/__init__.py
from .general_menus import (
    AFFLICTION_LIST,
    AFFLICTION_LEVELS,
    SUPPORT_GROUPS,
    UserRoleEnum,
    ProductStatus,
    ModerationReason,
    SubmissionType,
)

from .product_constants import (
    APPLICATION_METHODS,
    TERPENES,
    TERPENE_TRAITS,
    TERPENE_CHARACTERISTICS,
    STRAINS,
)

from .education import (
    KUSHWELL_SNIPPETS,
    get_random_snippet,
)

__all__ = [
    # General Menus
    "AFFLICTION_LIST",
    "AFFLICTION_LEVELS",
    "SUPPORT_GROUPS",
    "UserRoleEnum",
    "ProductStatus",
    "ModerationReason",
    "SubmissionType",
    # Product constants
    "APPLICATION_METHODS",
    "TERPENES",
    "TERPENE_TRAITS",
    "TERPENE_CHARACTERISTICS",
    "STRAINS",
    # Education / Snippets
    "KUSHWELL_SNIPPETS",
    "CANNABIS_FACTS",
]
