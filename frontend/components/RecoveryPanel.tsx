"use client";

import { useState } from "react";
import type { TraceEvent } from "@/lib/trace";

type Props = {
  runId: string;
  taken: TraceEvent[]; // kind === "casualty" && verdict === "taken"
  names: Record<string, string>;
  onSent: () => void;
};

/**
 * 회수 결정 — 굴에 끌려간 대원을 다시 데려올 것인가(기획서 v3 §6.8).
 *
 * 몸값은 은화만 태우지만 회수는 은화와 출동 슬롯을 동시에 태운다.
 * **회수는 보장된 거래가 아니다** — 돈을 내도 실패할 수 있다.
 * 그리고 두고 오면 그것이 그 사람에게서 배운다(§8.4 「섭식」).
 */
export default function RecoveryPanel({ runId, taken, names, onSent }: Props) {
  const [pay, setPay] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const toggle = (id: string) =>
    setPay((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(`/api/runs/${encodeURIComponent(runId)}/recovery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pay }),
      });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setErr(String(b.detail ?? "결정을 보내지 못했다"));
        return;
      }
      onSent();
    } catch {
      setErr("결정을 보내지 못했다");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card stack" style={{ gap: 10, borderColor: "var(--color-warn)" }}>
      <div className="card-kicker">회수 결정 — 굴에 두고 올 것인가</div>
      <p className="small" style={{ margin: 0 }}>
        되찾으려면 은화를 낸다. <strong>돈을 내도 실패할 수 있다.</strong>
        두고 오면 그것이 그 사람에게서 배워 다음에 돌아온다.
      </p>
      <ul className="stack" style={{ gap: 6, listStyle: "none", padding: 0, margin: 0 }}>
        {taken.map((e) => {
          const id = String(e.actor ?? "");
          return (
            <li key={e.seq} className="row" style={{ gap: 8, alignItems: "center" }}>
              <label className="row" style={{ gap: 6, alignItems: "center" }}>
                <input type="checkbox" checked={pay.includes(id)} onChange={() => toggle(id)} />
                <strong>{names[id] ?? id}</strong>
              </label>
              <span className="faint small">굴로 끌려갔다</span>
            </li>
          );
        })}
      </ul>
      {err && (
        <p className="small" style={{ margin: 0, color: "var(--color-danger)" }}>
          {err}
        </p>
      )}
      <div className="row" style={{ gap: 6 }}>
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={send}>
          {pay.length ? `${pay.length}명을 되찾는다` : "아무도 되찾지 않는다"}
        </button>
        <span className="faint small">답하지 않으면 전원 미지불로 처리된다</span>
      </div>
    </section>
  );
}
