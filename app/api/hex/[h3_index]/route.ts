import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

/**
 * GET /api/hex/{h3_index}
 *
 * Returns the full layer breakdown for a single hex by joining
 * prism_hex_layer × prism_layers. Used by the hex-click popup.
 *
 * Tries r8 first; if the index isn't found there, walks up to r7 then r6
 * (lower-zoom views serve aggregated cells from r7/r6 directly).
 */
export async function GET(
  _request: Request,
  context: { params: Promise<{ h3_index: string }> }
) {
  const { h3_index } = await context.params;
  if (!/^[0-9a-f]{15,}$/i.test(h3_index)) {
    return NextResponse.json({ error: "Invalid h3_index" }, { status: 400 });
  }

  const supabase = createAdminClient();

  // Resolve the hex from whichever resolution table it lives in
  for (const table of ["prism_hex_r8", "prism_hex_r7", "prism_hex_r6"]) {
    const { data: hex, error } = await supabase
      .from(table)
      .select("h3_index, friction_score, layer_count, top_friction_driver, category_flags")
      .eq("h3_index", h3_index)
      .maybeSingle();
    if (error) {
      // Table doesn't exist yet — skip during early dev
      if (error.code === "42P01") continue;
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    if (!hex) continue;

    const { data: layers, error: layerErr } = await supabase
      .from("prism_hex_layer")
      .select(
        `feature_count, layer:prism_layers(layer_id, layer_name, friction_category, friction_weight, friction_tier, agency_name, agency_url, permit_start_url)`
      )
      .eq("h3_index", h3_index);
    if (layerErr) {
      return NextResponse.json({ error: layerErr.message }, { status: 500 });
    }

    return NextResponse.json({
      h3_index: hex.h3_index,
      friction_score: hex.friction_score,
      layer_count: hex.layer_count,
      top_friction_driver: hex.top_friction_driver,
      category_flags: hex.category_flags,
      layers: (layers ?? [])
        .map((row) => row.layer)
        .filter(Boolean),
    });
  }

  return NextResponse.json({ error: "Hex not found" }, { status: 404 });
}
