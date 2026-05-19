import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function GET() {
  const supabase = createAdminClient();
  const { data, error } = await supabase
    .from("prism_states")
    .select("state_fips, state_abbr, state_name")
    .order("state_name");
  if (error) {
    if (error.code === "42P01") return NextResponse.json({ states: [] });
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ states: data ?? [] });
}
