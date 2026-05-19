/**
 * Zoom-to-resolution mapping for PRISM.
 *
 * R8 is the base resolution (~0.74 km², ~460m edge). Aggregated to R7 and R6
 * for low-zoom views. Tile RPC reads from prism_hex_r{6,7,8} based on z.
 */
export type H3Resolution = 6 | 7 | 8;

export function resolutionForZoom(z: number): H3Resolution {
  if (z <= 6) return 6;
  if (z <= 9) return 7;
  return 8;
}

export function tableForResolution(res: H3Resolution): string {
  return `prism_hex_r${res}`;
}
