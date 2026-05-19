# Design

UI/UX, visual language, component patterns, and design tokens.

## Visual identity

PRISM is a map-first analytical tool. The UI gets out of the way — full-viewport map with floating panels. Inspiration: Kepler.gl, Felt.com, Unfolded Studio.

| Aesthetic decision | Choice |
|---|---|
| Default theme | **Dark** (basemap dark-v11). Light/streets/satellite available via switcher. |
| Color palette | Magma family (deep purple → bright yellow) for the friction ramp; neutral grays for chrome |
| Chrome density | Minimal — floating cards over the map, transparent panels with backdrop-blur |
| Typography | System UI stack (no custom web font) |
| Spacing | Tight (~3 unit base) — panels are utility-dense, not editorial |

## Friction color ramp

`lib/h3/colors.ts` is the canonical source. Stops:

| Score | Hex | OKLCH approx | Tier label |
|---|---|---|---|
| 0 | `#1a0b30` | oklch(0.18 0.10 295) | Minimal |
| 25 | `#4a0d67` | oklch(0.30 0.20 305) | Low |
| 50 | `#b73779` | oklch(0.56 0.20 0) | Moderate |
| 75 | `#ed6925` | oklch(0.69 0.20 50) | High |
| 100 | `#fcffa4` | oklch(0.96 0.13 100) | Very High |

Why magma over Viridis or RdYlGn:
- **Viridis** maps low to dark purple and high to yellow-green. Visually appealing but doesn't reinforce "high = bad" intuition.
- **RdYlGn** is the most natural ("green = safe, red = stop") but fails for the ~5% of users with deuteranopia (red-green color blindness).
- **Magma** is perceptually uniform AND has high-is-bright/warm semantics, which permitting professionals read as "more friction" without needing a legend.

Implementation: `mapboxFrictionExpression()` returns a Mapbox `["interpolate", ["linear"], ["coalesce", ["get", "friction_score"], 0], ...stops]` paint expression.

Hex `fill-opacity` is 0.7 so basemap shows through (gives geographic context). No stroke at low zoom (would be visual noise); a thin dark stroke at z≥10.

## Layout

```
+----------------------------------------------------+
| [PRISM logo] ............ [Filters] [Layers] [Basemap] |
|                                                     |
|                                                     |
|                MAP VIEWPORT                          |
|                                                     |
|                                                     |
|  +-------------+                  [Zoom +/-]        |
|  | LEGEND      |                  [Geolocate]       |
|  | friction    |                  [Scale]           |
|  | 0 -- 100    |                                    |
|  +-------------+                                    |
+----------------------------------------------------+
```

All panels are `position: absolute`, `pointer-events-auto` on interactive children, transparent-card backgrounds with `backdrop-blur-sm`.

The `<main>` container uses `height: 100dvh` (dynamic viewport height) so mobile browser UI bars don't crop the map.

## Shadcn / Radix primitives

We use a thin subset of shadcn's component patterns, built on Radix:

| Component | Used in |
|---|---|
| `Button` (CVA variants) | All clickable controls |
| `Slider` (Radix) | `ScoreFilter` — friction range 0–100 |
| `Checkbox` (Radix) | `GeographyFilter` (state/county multi-select), `CategoryFilter` |
| `Popover` (Radix) | (defined; not yet used — Phase 3) |

Components are owned by us in `components/ui/`; we don't pull `shadcn add` (would conflict with our Tailwind v4 theme tokens). Add new primitives by hand-copying from shadcn's source and adapting to our `@theme` block.

## Design tokens

Custom OKLCH values defined in `app/globals.css` `@theme` block. Tailwind v4 generates classes from these automatically. Key tokens:

| Token | Value | Used for |
|---|---|---|
| `--color-background` | `oklch(0.145 0 0)` (near-black) | Body bg, panel base |
| `--color-foreground` | `oklch(0.985 0 0)` (near-white) | Text |
| `--color-card` | `oklch(0.205 0 0)` | Panel surface |
| `--color-popover` | `oklch(0.205 0 0)` | Mapbox popup override |
| `--color-primary` | `oklch(0.78 0.18 75)` (warm yellow) | Brand accent, active filter chip |
| `--color-border` | `oklch(1 0 0 / 0.1)` (10% white) | Panel edges |
| `--color-ring` | `oklch(0.78 0.18 75)` | Focus rings |
| `--friction-0` … `--friction-100` | (see above) | Friction ramp anchors |
| `--radius` | `0.625rem` | Card corner radius |

## Component patterns

### Floating panel

All overlay panels follow:

```tsx
<div className="rounded-md border border-border bg-card/85 p-3 backdrop-blur-sm">
  ...
</div>
```

The `/85` opacity + `backdrop-blur-sm` is the signature — makes the map visible through controls without being washed out.

### Filter chips

When a filter set is active, show a count badge in the trigger:

```tsx
{activeCount > 0 && (
  <span className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold">
    {activeCount}
  </span>
)}
```

### Hex hover tooltip vs click popup

Two different interactions on purpose:

| Hover | Click |
|---|---|
| Lightweight tooltip (no fetch) | Heavyweight Mapbox popup (fetches `/api/hex/{h3_index}`) |
| Reads from tile properties | Joins prism_hex_layer × prism_layers |
| Shows score + top 3 layers | Shows full layer breakdown + agency links |
| Disappears on mouseleave | Pinned until close-button or new click |
| 80 ms debounce | None (deliberate click action) |

The popup is rendered into a React Portal inside Mapbox's popup container — see `HexPopup.tsx`. Click-popup loading state is a brief `Loading layer breakdown…` while the API request completes.

## Open design items

These are explicit deferred decisions, not bugs:

- **Branding / logo**: currently a plain `PRISM` wordmark + "Permitting Risk Index" tagline. No logo asset. Acceptable for pilot; revisit before public launch.
- **Mobile**: layout is desktop-first. On mobile, panels would need to collapse to bottom-sheets. Out of scope for Phase 1–3.
- **Empty-state for no-data regions**: currently a no-hex region just shows basemap. Could add a "no permitting data for this area" legend item, or render a translucent overlay outside the ingested AOI.
- **Polygon-upload UI**: file-parser lib is ready (`lib/file-parsers.ts`), but no UI component yet. Phase 3.
- **Sentry visual / accessibility audit**: not done. Run lighthouse / axe before launch.
