import { backendFetch } from "@/lib/backend";
import E1Chart, { type E1Result } from "@/components/E1Chart";

export const dynamic = "force-dynamic";

// 실험 E1 — 조합별 오케스트레이터 ON/OFF (기획서 §10.1). 차트는 SVG 로 직접 그린다.
export default async function ExperimentsPage() {
  let e1: E1Result | null = null;
  let note: string | null = null;
  try {
    const r = await backendFetch("/experiments/e1");
    if (r.ok) e1 = (await r.json()) as E1Result;
    else note = r.status === 404 ? "아직 E1 결과가 없다. backend 에서 `uv run python -m eval.run --experiment e1 --seeds 30` 을 돌린다." : `GET /experiments/e1 → ${r.status}`;
  } catch (e) {
    note = `백엔드에 닿지 못했다: ${(e as Error).message}`;
  }
  return (
    <main className="page page-narrow stack" style={{ gap: 16 }}>
      <div className="card-kicker">실험</div>
      <h1>E1 · 조합별 단장 ON / OFF</h1>
      <p className="muted small">
        단장(오케스트레이터)이 실제로 도움이 되는가 — 좋은 조합의 승률이 아니라 <b>나쁜 조합에서의 회복력</b>으로 잰다. 조합 4종 × 단장
        ON/OFF × 시드 N. 같은 시드는 같은 판이므로 두 조건의 차이는 단장 하나에서 온다.
      </p>
      {note && (
        <div className="card">
          <p className="small muted">{note}</p>
        </div>
      )}
      {e1 && <E1Chart data={e1} />}
    </main>
  );
}
