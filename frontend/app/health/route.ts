export async function GET() {
  const base = process.env.BACKEND_URL || "http://127.0.0.1:8765";
  try {
    const response = await fetch(`${base}/health`, { cache: "no-store" });
    const body = await response.json();
    return Response.json({ web: "ok", api: body }, { status: response.ok ? 200 : 503 });
  } catch (error) {
    return Response.json({ web: "ok", api: "down", error: String(error) }, { status: 503 });
  }
}
