"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Inspector from "@/components/Inspector";
import NarrativeStream from "@/components/NarrativeStream";
import { buildNameMap, isKind, type TraceEvent } from "@/lib/trace";

type Status = "connecting" | "live" | "done" | "error";

// 2패널 트레이스 뷰어(기획서 §11.2): 왼쪽 서사 스트림, 가운데 판정 인스펙터.
// 원칙: 왼쪽에서 일어나는 모든 일이 가운데에서 설명 가능하다.
export default function BattleClient({ runId }: { runId: string }) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [follow, setFollow] = useState(true);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`);
    const onEvent = (raw: MessageEvent) => {
      try {
        const e = JSON.parse(raw.data) as TraceEvent;
        if (!isKind(e.kind) || seen.current.has(e.seq)) return;
        seen.current.add(e.seq);
        setEvents((cur) => [...cur, e]);
        setStatus("live");
      } catch {
        /* keepalive 등 */
      }
    };
    es.onmessage = onEvent;
    // 서버가 event: <kind> 로 보내므로 종류별로 붙인다.
    for (const k of KIND_LIST) es.addEventListener(k, onEvent as EventListener);
    es.addEventListener("done", () => {
      setStatus("done");
      es.close();
    });
    es.addEventListener("error", (ev) => {
      const me = ev as MessageEvent;
      if (me.data) {
        try {
          setError(JSON.parse(me.data).error);
        } catch {
          setError(String(me.data));
        }
        setStatus("error");
        es.close();
      } else if (es.readyState === EventSource.CLOSED) {
        setStatus((s) => (s === "done" ? s : "error"));
      }
    });
    return () => es.close();
  }, [runId]);

  const names = useMemo(() => buildNameMap(events), [events]);
  const selected = useMemo(() => events.find((e) => e.seq === selectedSeq) ?? null, [events, selectedSeq]);
  const runEnd = events.find((e) => e.kind === "run_end");
  const missionStart = events.find((e) => e.kind === "mission_start");
  const title = missionStart ? String((missionStart.payload.name as string) ?? "") : "";

  return (
    <main className="page stack" style={{ gap: 14 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="stack" style={{ gap: 2 }}>
          <div className="card-kicker">전투 · {title || "…"}</div>
          <h2>
            {status === "connecting" && "전장에 연결하는 중…"}
            {status === "live" && "진행 중"}
            {status === "done" && "끝났다"}
            {status === "error" && "끊겼다"}
            <span className="faint small mono" style={{ marginLeft: 10 }}>
              {runId}
            </span>
          </h2>
        </div>
        <div className="row small">
          <label className="row" style={{ gap: 4 }}>
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            따라가기
          </label>
          {runEnd && (
            <Link className="btn btn-sm btn-primary" href={`/result/${runId}`}>
              결과 보기 →
            </Link>
          )}
          <Link className="btn btn-sm" href="/roster">
            다시 편성
          </Link>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--color-danger)" }}>
          <p className="small" style={{ color: "var(--color-danger)" }}>
            런이 실패했다: {error}
          </p>
        </div>
      )}

      <div className="panels">
        <section className="card panel" style={{ gap: 8 }}>
          <div className="card-kicker">서사 스트림 · 클릭하면 판정이 열린다</div>
          <NarrativeStream events={events} names={names} selectedSeq={selectedSeq} onSelect={(s) => { setSelectedSeq(s); setFollow(false); }} follow={follow} />
        </section>
        <section className="card panel" style={{ gap: 8 }}>
          <div className="card-kicker">판정 인스펙터</div>
          <Inspector event={selected} names={names} events={events} />
        </section>
      </div>
    </main>
  );
}

const KIND_LIST = [
  "run_start", "mission_start", "plan", "odds", "turn_start", "context", "compliance", "decision", "resolution",
  "boss_adapt", "replan_trigger", "abandon", "flee", "summon", "mission_end", "intermission_start", "directive",
  "train_compliance", "train_result", "life_event", "param_diff", "growth_points", "advice", "run_end",
];
