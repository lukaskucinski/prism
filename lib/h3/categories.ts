/**
 * 8 consolidated friction categories.
 *
 * Source-of-truth for both the Python ingest (which maps each layer's raw
 * APPEIT `group` string to a category) and the frontend category-toggle UI.
 */
export const FRICTION_CATEGORIES = [
  "critical_habitat",
  "floodplain_wetland",
  "historic",
  "tribal_federal_land",
  "epa_program",
  "state_protected",
  "infrastructure",
  "environmental_justice",
] as const;

export type FrictionCategory = (typeof FRICTION_CATEGORIES)[number];

export const CATEGORY_LABELS: Record<FrictionCategory, string> = {
  critical_habitat: "Critical Habitat",
  floodplain_wetland: "Floodplain / Wetland",
  historic: "Historic & Cultural",
  tribal_federal_land: "Tribal & Federal Land",
  epa_program: "EPA Programs",
  state_protected: "State Protected Lands",
  infrastructure: "Infrastructure Corridors",
  environmental_justice: "Environmental Justice",
};

export const CATEGORY_DEFAULT_TIER: Record<FrictionCategory, "high" | "medium" | "low"> = {
  critical_habitat: "high",
  floodplain_wetland: "high",
  historic: "medium",
  tribal_federal_land: "medium",
  epa_program: "medium",
  state_protected: "low",
  infrastructure: "low",
  environmental_justice: "medium",
};

export const TIER_SCORE: Record<"high" | "medium" | "low", number> = {
  high: 30,
  medium: 15,
  low: 5,
};
