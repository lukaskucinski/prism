import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const states = url.searchParams.get("states");
  const supabase = createAdminClient();
  let query = supabase
    .from("prism_districts")
    .select("district_id, state_fips, district_number, congress")
    .order("district_id");
  if (states) {
    const stateFips = states.split(",").map((s) => s.trim()).filter(Boolean);
    if (stateFips.length) query = query.in("state_fips", stateFips);
  }
  const { data, error } = await query;
  if (error) {
    if (error.code === "42P01") return NextResponse.json({ districts: [] });
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ districts: data ?? [] });
}
