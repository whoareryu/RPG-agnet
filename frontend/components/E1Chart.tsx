// E1 결과 차트 — 외부 라이브러리 없이 SVG. eval/e1.py 의 출력 형태를 그대로 받는다.
export type E1Cell = {
  games: number;
  win_rate: number;
  retreat_rate: number;
  loss_rate: number;
  draw_rate: number;
  survival_rate: number;
  avg_turns: number;
  avg_calls: number;
};
export type E1Result = {
  experiment: "e1";
  seeds: number;
  model: string;
  compositions: { key: string; label: string; lineup: string[]; on: E1Cell; off: E1Cell }[];
};

const W = 640;
const ROW = 64;

export default function E1Chart({ data }: { data: E1Result }) {
  const H = ROW * data.compositions.length + 40;
  return (
    <div className="card" style={{ gap: 12 }}>
      <div className="row small faint">
        <span>시드 {data.seeds}개</span>
        <span>·</span>
        <span>모델 {data.model}</span>
        <span>·</span>
        <span style={{ color: "var(--color-accent-2)" }}>■ 승률</span>
        <span style={{ color: "var(--color-warn)" }}>■ 후퇴율</span>
        <span style={{ color: "var(--color-ok)" }}>■ 생존율</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="E1 조합별 단장 ON/OFF">
          {data.compositions.map((c, i) => {
            const y = i * ROW + 10;
            return (
              <g key={c.key} transform={`translate(0, ${y})`}>
                <text x={0} y={14} fontSize={13} fontWeight={700} fill="var(--color-text)">
                  {c.label}
                </text>
                {(["on", "off"] as const).map((side, j) => {
                  const cell = c[side];
                  const yy = 20 + j * 18;
                  return (
                    <g key={side} transform={`translate(0, ${yy})`}>
                      <text x={0} y={11} fontSize={11} fill="var(--color-text-faint)">
                        단장 {side.toUpperCase()}
                      </text>
                      <rect x={70} y={2} width={300} height={10} fill="var(--color-surface-2)" rx={3} />
                      <rect x={70} y={2} width={300 * cell.win_rate} height={10} fill="var(--color-accent-2)" rx={3} />
                      <rect x={70 + 300 * cell.win_rate} y={2} width={300 * cell.retreat_rate} height={10} fill="var(--color-warn)" />
                      <rect x={380} y={2} width={120} height={10} fill="var(--color-surface-2)" rx={3} />
                      <rect x={380} y={2} width={120 * cell.survival_rate} height={10} fill="var(--color-ok)" rx={3} />
                      <text x={510} y={11} fontSize={11} fill="var(--color-text-muted)">
                        승 {Math.round(cell.win_rate * 100)}% · 후퇴 {Math.round(cell.retreat_rate * 100)}% · 생존 {Math.round(cell.survival_rate * 100)}%
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>
      <table className="kv">
        <thead>
          <tr>
            <th>조합</th>
            <th>ON 승/후퇴/패/무</th>
            <th>OFF 승/후퇴/패/무</th>
            <th>생존율 ON / OFF</th>
            <th>평균 턴 ON / OFF</th>
          </tr>
        </thead>
        <tbody>
          {data.compositions.map((c) => (
            <tr key={c.key}>
              <td>{c.label}</td>
              <td className="mono">{[c.on.win_rate, c.on.retreat_rate, c.on.loss_rate, c.on.draw_rate].map((v) => Math.round(v * 100)).join(" / ")}</td>
              <td className="mono">{[c.off.win_rate, c.off.retreat_rate, c.off.loss_rate, c.off.draw_rate].map((v) => Math.round(v * 100)).join(" / ")}</td>
              <td className="mono">
                {Math.round(c.on.survival_rate * 100)}% / {Math.round(c.off.survival_rate * 100)}%
              </td>
              <td className="mono">
                {c.on.avg_turns.toFixed(1)} / {c.off.avg_turns.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
