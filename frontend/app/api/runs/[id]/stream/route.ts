import { backendFetch, BackendDown } from "@/lib/backend";

// SSE 를 그대로 흘린다. 버퍼링하면 실시간이 아니다 — body 스트림을 통째로 넘긴다.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  try {
    const r = await backendFetch(`/runs/${encodeURIComponent(id)}/stream`);
    if (!r.ok || !r.body) {
      return new Response(await r.text(), { status: r.status });
    }
    return new Response(r.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (e) {
    if (e instanceof BackendDown) return Response.json({ detail: e.message }, { status: 502 });
    throw e;
  }
}
