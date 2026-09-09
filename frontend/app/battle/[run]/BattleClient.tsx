"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Dashboard from "@/components/Dashboard";
import HornButton from "@/components/HornButton";
import RecoveryPanel from "@/components/RecoveryPanel";
import Inspector from "@/components/Inspector";
import IntermissionPanel from "@/components/IntermissionPanel";
import NarrativeStream from "@/components/NarrativeStream";
import { buildNameMap, isKind, KINDS, type TraceEvent } from "@/lib/trace";

type Status = "connecting" | "live" | "done" | "error";

// 2패널 트레이스 뷰어(기획서 §11.2): 왼쪽 서사 스트림, 가운데 판정 인스펙터.
// 원칙: 왼쪽에서 일어나는 모든 일이 가운데에서 설명 가능하다.
export default function BattleClient({ runId }: { runId: string }) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [follow, setFollow] = useState(true);
  const [showQuiet, setShowQuiet] = useState(false);
  const [sentFor, setSentFor] = useState<number[]>([]);
  const [recoverySent, setRecoverySent] = useState(false);
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
    for (const k of KINDS) es.addEventListener(k, onEvent as EventListener);
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
  // 인터미션이 입력을 기다리는 중인가 — 그 뒤에 다른 이벤트가 오면 이미 지나갔다.
  const awaiting = useMemo(() => {
    const idx = events.findLastIndex(
      (e) => e.kind === "intermission_start" && e.payload.awaiting_input,
    );
    if (idx < 0 || sentFor.includes(events[idx].seq)) return null;
    return idx === events.length - 1 ? events[idx] : null;
  }, [events, sentFor]);
  const missionStart = events.find((e) => e.kind === "mission_start");
  const title = missionStart ? String((missionStart.payload.name as string) ?? "") : "";

  // 그것에게 이름이 붙었나(기획서 v3 §8.5). 붙으면 15회차까지 남는다.
  const bossName = useMemo(() => {
    const named = events.findLast((e) => e.kind === "boss_named");
    return named ? String(named.payload.after ?? "") : null;
  }, [events]);

  // 굴로 끌려간 사람들 — 회수 결정을 받아야 한다(기획서 v3 §6.8).
  // 이미 결정을 보냈거나 판이 끝났으면 묻지 않는다.
  const taken = useMemo(
    () => events.filter((e) => e.kind === "casualty" && e.payload.verdict === "taken"),
    [events],
  );
  const askRecovery = taken.length > 0 && !recoverySent && status !== "error";

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
          <label className="row" style={{ gap: 4 }} title="승산·순응·행동 순서까지 전부 보여준다">
            <input type="checkbox" checked={showQuiet} onChange={(e) => setShowQuiet(e.target.checked)} />
            전부 보기
          </label>
          <HornButton runId={runId} live={status === "live"} />
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

      {bossName && (
        <p className="small" style={{ margin: 0 }}>
          대원들은 그것을 <strong>「{bossName}」</strong>이라 부른다.
        </p>
      )}

      {askRecovery && (
        <RecoveryPanel
          runId={runId}
          taken={taken}
          names={names}
          onSent={() => setRecoverySent(true)}
        />
      )}

      {awaiting && (
        <IntermissionPanel
          runId={runId}
          events={events}
          names={names}
          timeoutS={Number(awaiting.payload.timeout_s ?? 60)}
          onSent={() => setSentFor((cur) => [...cur, awaiting.seq])}
        />
      )}

      <div className="panels three">
        <section className="card panel panel-tall" style={{ gap: 8 }}>
          <div className="card-kicker">서사 스트림 · 클릭하면 판정이 열린다</div>
          <NarrativeStream
            events={events}
            names={names}
            selectedSeq={selectedSeq}
            onSelect={(s) => {
              setSelectedSeq(s);
              setFollow(false);
              // 좁은 화면에서는 인스펙터가 아래에 있다 — 눌렀는데 아무 일도
              // 안 일어난 것처럼 보이면 안 된다.
              if (typeof window !== "undefined" && window.innerWidth <= 900) {
                document.getElementById("inspector")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }
            }}
            follow={follow}
            showQuiet={showQuiet}
          />
        </section>
        <section id="inspector" className="card panel" style={{ gap: 8 }}>
          <div className="card-kicker">판정 인스펙터</div>
          <Inspector event={selected} names={names} events={events} />
        </section>
        <section className="card panel" style={{ gap: 8 }}>
          <div className="card-kicker">상태</div>
          <Dashboard events={events} names={names} />
        </section>
      </div>
    </main>
  );
}
