import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  v: string;
  z: string;
  x: string;
  y: string;
}

/**
 * GET /api/tiles/v{N}/{z}/{x}/{y}.mvt?f={base64url(filterHash)}
 *
 * Calls the Postgres function prism_get_hex_mvt(z, x, y, filter_json) which
 * returns a BYTEA MVT payload at the appropriate H3 resolution for `z`.
 * Filter JSON is decoded from the `f` query param and passed through.
 *
 * Cache headers are set in next.config.ts via the /api/tiles/:path* matcher.
 */
export async function GET(
  request: Request,
  context: { params: Promise<Params> }
) {
  const params = await context.params;
  const z = parseInt(params.z, 10);
  // y comes in as "{y}.mvt" — strip the extension
  const yStr = params.y.replace(/\.mvt$/, "");
  const x = parseInt(params.x, 10);
  const y = parseInt(yStr, 10);

  if ([z, x, y].some((n) => !Number.isFinite(n) || n < 0)) {
    return new NextResponse("Bad tile coordinates", { status: 400 });
  }
  if (z < 0 || z > 22) {
    return new NextResponse("Zoom out of range", { status: 400 });
  }

  const url = new URL(request.url);
  const filterParam = url.searchParams.get("f");
  let filterJson: Record<string, unknown> = {};
  if (filterParam) {
    try {
      const decoded = Buffer.from(filterParam, "base64url").toString("utf8");
      filterJson = JSON.parse(decoded);
    } catch {
      // Ignore malformed filter — serve unfiltered tile
    }
  }

  try {
    const supabase = createAdminClient();
    const { data, error } = await supabase.rpc("prism_get_hex_mvt", {
      z,
      x,
      y,
      filter_json: filterJson,
    });

    if (error) {
      // Common during early dev: RPC doesn't exist yet. Return empty tile.
      if (error.code === "PGRST202" || error.message?.includes("not found")) {
        return new NextResponse(new Uint8Array(0), {
          status: 200,
          headers: { "Content-Type": "application/vnd.mapbox-vector-tile" },
        });
      }
      console.error("Tile RPC error:", error);
      return new NextResponse("Tile RPC error", { status: 500 });
    }

    // Supabase returns bytea as base64-encoded string OR a Uint8Array depending
    // on the wire format. Normalize.
    let bytes: Uint8Array;
    if (data instanceof Uint8Array) {
      bytes = data;
    } else if (typeof data === "string") {
      // PostgREST returns "\\x..." hex strings for bytea; tolerate both
      if (data.startsWith("\\x")) {
        bytes = hexToBytes(data.slice(2));
      } else {
        bytes = Uint8Array.from(Buffer.from(data, "base64"));
      }
    } else if (data && typeof data === "object" && "data" in data) {
      bytes = new Uint8Array((data as { data: number[] }).data);
    } else {
      bytes = new Uint8Array(0);
    }

    return new NextResponse(new Blob([new Uint8Array(bytes)]), {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.mapbox-vector-tile",
        "Content-Length": String(bytes.byteLength),
      },
    });
  } catch (err) {
    console.error("Tile route exception:", err);
    return new NextResponse("Tile route exception", { status: 500 });
  }
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}
