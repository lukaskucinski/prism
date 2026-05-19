import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

/**
 * GET /api/layers
 *
 * Returns the catalog of ingested layers. Cached at the edge (see
 * next.config.ts). The frontend uses this to populate the category filter
 * sidebar and to show "ingest_status" badges in an admin view.
 */
export async function GET() {
  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("prism_layers")
    .select(
      "layer_id, layer_name, friction_category, friction_weight, friction_tier, agency_name, agency_url, permit_start_url, ingest_status, feature_count, last_ingested"
    )
    .order("friction_category")
    .order("layer_name");

  if (error) {
    if (error.code === "42P01") {
      // Table doesn't exist yet — return empty list so the UI can render
      return NextResponse.json({ layers: [] });
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ layers: data ?? [] });
}
