"""
Mapping from APPEIT's raw `group` strings (18 distinct values) to PRISM's 8
consolidated friction categories. Also the placeholder tier weights.

This module is the single source of truth for category assignment during
ingest. Mirrors `lib/h3/categories.ts` on the frontend.
"""

from __future__ import annotations

from typing import Final, Literal

FrictionCategory = Literal[
    "critical_habitat",
    "floodplain_wetland",
    "historic",
    "tribal_federal_land",
    "epa_program",
    "state_protected",
    "infrastructure",
    "environmental_justice",
]

Tier = Literal["high", "medium", "low"]

# APPEIT raw `group` → PRISM friction_category.
# State-specific groups all map to state_protected.
RAW_GROUP_TO_CATEGORY: Final[dict[str, FrictionCategory]] = {
    # Direct mappings
    "Critical Habitats": "critical_habitat",
    "Floodplains": "floodplain_wetland",
    "Historic Places": "historic",
    "Federal/Tribal Land": "tribal_federal_land",
    "EPA Programs": "epa_program",
    "Infrastructure": "infrastructure",
    "State Lands": "state_protected",
    # State-specific catalog groups (Alaska, New York, Kentucky, etc.)
    # → all funnel into state_protected
    "Alaska": "state_protected",
    "New York": "state_protected",
    "Kentucky": "state_protected",
    "North Dakota": "state_protected",
    "Delaware": "state_protected",
    "Wyoming": "state_protected",
    "Oregon": "state_protected",
    "Maryland": "state_protected",
    "Colorado": "state_protected",
    "Washington": "state_protected",
    "Mississippi": "state_protected",
    "Adirondack Park": "state_protected",
    "Vermont": "state_protected",
    # APPEIT may include a top-level EJ category in future; map for safety.
    "Environmental Justice": "environmental_justice",
}

# Default tier per category. Overridden later by layer-evaluation task,
# which writes friction_weight + friction_tier into prism_layers directly.
CATEGORY_DEFAULT_TIER: Final[dict[FrictionCategory, Tier]] = {
    "critical_habitat": "high",
    "floodplain_wetland": "high",
    "historic": "medium",
    "tribal_federal_land": "medium",
    "epa_program": "medium",
    "state_protected": "low",
    "infrastructure": "low",
    "environmental_justice": "medium",
}

TIER_SCORE: Final[dict[Tier, int]] = {"high": 30, "medium": 15, "low": 5}


def category_for(raw_group: str | None) -> FrictionCategory:
    """
    Resolve an APPEIT raw group string to a PRISM friction category.
    Falls back to 'state_protected' for unrecognized values (state-specific
    layers from new states added to APPEIT but not yet mapped here).
    """
    if not raw_group:
        return "state_protected"
    return RAW_GROUP_TO_CATEGORY.get(raw_group.strip(), "state_protected")


def default_weight_for(category: FrictionCategory) -> int:
    return TIER_SCORE[CATEGORY_DEFAULT_TIER[category]]
