"""
Application method constants for Kushwell.

This module defines the canonical list of ways patients can consume or
otherwise use cannabis products.  Having a consistent set of terms ensures
that enterprises describe their products uniformly and that patient
check‑ins and usage logs can be correlated accurately.

The list below comes directly from the stakeholder and should be treated
as authoritative.  If new methods need to be added, they should be
appended via the admin interface rather than edited here directly.
"""

# The master list of application methods.  Do not reorder entries.  New
# methods should be appended via the admin workflow.
APPLICATION_METHODS = [
    "Smoking",
    "Vaping",
    "Edible",
    "Capsule/Pill",
    "Sublingual (Tincture/Oil)",
    "Topical (Non-ingestible)",
    "Transdermal Patch",
    "Beverage",
    "Other",
]

# Stable single-term values for saving to DB, matching the labels above.
# Do not reorder; append new entries at the end via admin workflow.
# 
APPLICATION_METHOD_CHOICES = [
    ("smoking", "Smoking"),
    ("vaping", "Vaping"),
    ("edible", "Edible"),
    ("capsule_pill", "Capsule/Pill"),
    ("sublingual", "Sublingual (Tincture/Oil)"),
    ("topical", "Topical (Non-ingestible)"),
    ("transdermal_patch", "Transdermal Patch"),
    ("beverage", "Beverage"),
    ("other", "Other"),
]

def application_method_choices():
    return APPLICATION_METHOD_CHOICES


