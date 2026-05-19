/**
 * Friction-score → color ramp.
 *
 * Magma-family palette (dark-first): low friction = deep purple, high friction =
 * bright yellow. Anchored at 0/25/50/75/100. Used both for the Mapbox paint
 * expression and the HTML legend.
 */
export type FrictionTier = "minimal" | "low" | "moderate" | "high" | "very-high";

export interface ColorStop {
  score: number;
  hex: string;
  tier: FrictionTier;
  label: string;
}

export const COLOR_STOPS: ColorStop[] = [
  { score: 0, hex: "#1a0b30", tier: "minimal", label: "Minimal" },
  { score: 25, hex: "#4a0d67", tier: "low", label: "Low" },
  { score: 50, hex: "#b73779", tier: "moderate", label: "Moderate" },
  { score: 75, hex: "#ed6925", tier: "high", label: "High" },
  { score: 100, hex: "#fcffa4", tier: "very-high", label: "Very High" },
];

export function tierForScore(score: number): FrictionTier {
  if (score <= 10) return "minimal";
  if (score <= 25) return "low";
  if (score <= 50) return "moderate";
  if (score <= 75) return "high";
  return "very-high";
}

/**
 * Mapbox GL paint expression for fill-color interpolated over friction_score.
 */
export function mapboxFrictionExpression() {
  return [
    "interpolate",
    ["linear"],
    ["coalesce", ["get", "friction_score"], 0],
    ...COLOR_STOPS.flatMap((stop) => [stop.score, stop.hex]),
  ] as const;
}
