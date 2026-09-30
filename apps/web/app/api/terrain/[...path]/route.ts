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
    const result = await fetch(
      `http://127.0.0.1:8766/${suffix}${request.nextUrl.search}`,
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
          "Terrain service unavailable. Run npm run planner from apps/web.",
      },
      { status: 503 },
    );
  }
}
