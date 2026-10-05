import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const suffix = path.join("/");
  if (
    !/^(?:(?:height|hillshade|slope|psr|height_error)\/\d{1,2}\/\d{1,5}\/\d{1,5}|inspect|health)$/.test(
      suffix,
    )
  ) {
    return Response.json(
      { error: "Unsupported terrain request" },
      { status: 400 },
    );
  }
  try {
    // Server-only configuration: never accept an upstream URL from the client.
    // A hosted frontend must point at a hosted terrain service, not the user's Mac.
    const origin = process.env.TERRAIN_SERVICE_URL || "http://127.0.0.1:8766";
    const upstream = new URL(origin);
    if (!["http:", "https:"].includes(upstream.protocol) || upstream.username || upstream.password ||
        upstream.search || upstream.hash || upstream.pathname !== "/")
      throw new Error("TERRAIN_SERVICE_URL must be an HTTP(S) origin without credentials or path");
    const result = await fetch(
      new URL(`/${suffix}${request.nextUrl.search}`,upstream),
      { signal: AbortSignal.timeout(20000) },
    );
    return new Response(result.body, {
      status: result.status,
      headers: {
        "Content-Type":
          result.headers.get("Content-Type") || "application/octet-stream",
        "Cache-Control": result.ok ? "public, max-age=3600" : "no-store",
      },
    });
  } catch (error) {
    console.error("Local terrain upstream failed", suffix, error);
    return Response.json(
      {
        error:
          "Terrain service unavailable. The operator must start or configure the terrain backend; no substitute terrain is being returned.",
      },
      { status: 503 },
    );
  }
}
