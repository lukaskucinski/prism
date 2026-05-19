import { filterHash, type FilterState } from "@/lib/store/filters";

const TILE_VERSION = process.env.NEXT_PUBLIC_TILE_VERSION ?? "1";

/**
 * Construct the Mapbox vector-tile source URL template.
 *
 * The version segment lives in the path (not the query) so CDNs cache it
 * cleanly. Bump NEXT_PUBLIC_TILE_VERSION after rescore/weight changes to
 * invalidate every edge cache transparently.
 */
export function tileUrlTemplate(filters: FilterState, origin = ""): string {
  const filterB64 =
    typeof window === "undefined"
      ? Buffer.from(filterHash(filters)).toString("base64url")
      : btoa(filterHash(filters)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${origin}/api/tiles/v${TILE_VERSION}/{z}/{x}/{y}.mvt?f=${filterB64}`;
}
