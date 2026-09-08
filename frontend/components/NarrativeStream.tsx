"use client";

import { useEffect, useRef } from "react";
import { narrate } from "@/lib/narrate";
import type { TraceEvent } from "@/lib/trace";

// 스트림에 문장으로 나오는 종류. 나머지(odds·context·turn_start 등)는 접어 두고
// 인스펙터에서만 연다 — 24턴이 433줄이 되면 아무도 읽지 않는다.
const QUIET = new Set(["odds", "context", "turn_start"]);

type Props = {
  events: TraceEvent[];
  names: Record<string, string>;
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  follow: boolean;
  showQuiet?: boolean;
};

export default function NarrativeStream({ events, names, selectedSeq, onSelect, follow, showQuiet = false }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: "end" });
  }, [events.length, follow]);

  return (
    <div className="stream">
      {events.map((e) => {
        if (!showQuiet && QUIET.has(e.kind) && e.kind !== "turn_start") return null;
        if (e.kind === "compliance" && e.payload.verdict === "comply") return null; // 순응은 조용하다. 이탈만 문장이 된다.
        const cls = [
          "stream-item",
          `k-${e.kind}`,
          e.kind === "compliance" && e.payload.verdict === "deviate" ? "deviate" : "",
          e.seq === selectedSeq ? "selected" : "",
        ].join(" ");
        return (
          <div key={e.seq} className={cls} onClick={() => onSelect(e.seq)}>
            <span className="seq">#{e.seq}</span>
            {narrate(e, names)}
          </div>
        );
      })}
      {events.length === 0 && <p className="small faint">아직 아무 일도 일어나지 않았다.</p>}
      <div ref={endRef} />
    </div>
  );
}
