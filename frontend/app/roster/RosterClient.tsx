"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import RosterCard from "@/components/RosterCard";
import { compact, total, validate, type Allocation } from "@/lib/allocation";

export type PresetCharacter = {
  id: string;
  name: string;
  gender: "female" | "male";
  body: { height_cm: number; build: string; weight_kg: number };
  weight_class: number;
  base_stats: Record<string, number>;
  recommended: Record<string, number>;
  class: string;
  disposition: Record<string, number>;
  disposition_text: Record<string, string>;
  mbti: string;
  life: string;
  backstory: string;
  build_preview: { weapon: string; armor: string; rationale: string };
};

export type PresetResponse = {
  roster: PresetCharacter[];
  classes: { key: string; label: string; primary: string[] }[];
  free_points: number;
  stat_base: number;
  lineup_size: number;
};

// 로스터 화면(기획서 §4.1 [2]관찰 → [3]방향 결정 → 출전 조합). A단계는 프리셋 5 + 재분배.
// 게임은 막지 않는다 — 전사 셋도, 마른 전사도 보낸다. 막는 것은 총량·인원뿐이다.
export default function RosterClient({ preset }: { preset: PresetResponse }) {
  const router = useRouter();
  const [allocs, setAllocs] = useState<Record<string, Allocation>>(() =>
    Object.fromEntries(preset.roster.map((c) => [c.id, { ...c.recommended }])),
  );
  const [classes, setClasses] = useState<Record<string, string>>(() =>
    Object.fromEntries(preset.roster.map((c) => [c.id, c.class])),
  );
  const [genders, setGenders] = useState<Record<string, "female" | "male">>(() =>
    Object.fromEntries(preset.roster.map((c) => [c.id, c.gender])),
  );
  const [lineup, setLineup] = useState<string[]>([]);
  const [orchestrator, setOrchestrator] = useState(true);
  const [adaptation, setAdaptation] = useState(true);
  const [seed, setSeed] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const problems = useMemo(() => {
    const out: string[] = [];
    for (const c of preset.roster) {
      const p = validate(allocs[c.id], preset.stat_base, preset.free_points);
      if (p) out.push(`${c.name}: ${p}`);
    }
    if (lineup.length !== preset.lineup_size) out.push(`출전 인원은 ${preset.lineup_size}명이어야 한다 (지금 ${lineup.length}명)`);
    return out;
  }, [allocs, lineup, preset]);

  function toggleLineup(id: string) {
    setLineup((cur) => {
      if (cur.includes(id)) return cur.filter((x) => x !== id);
      if (cur.length >= preset.lineup_size) return cur;
      return [...cur, id];
    });
  }

  async function start() {
    setBusy(true);
    setError(null);
    const body = {
      lineup,
      allocations: Object.fromEntries(preset.roster.map((c) => [c.id, compact(allocs[c.id])])),
      classes,
      genders,
      orchestrator,
      adaptation,
      seed: seed.trim() === "" ? null : Number(seed),
      missions: 1,
    };
    const r = await fetch("/api/runs", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setError(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data));
      setBusy(false);
      return;
    }
    router.push(`/battle/${data.run_id}`);
  }

  return (
    <main className="page stack" style={{ gap: 20 }}>
      <section className="stack" style={{ gap: 6 }}>
        <div className="card-kicker">로스터 · 지급된 다섯 명</div>
        <h1>몸을 보고, 방향을 정하고, 셋을 고른다</h1>
        <p className="muted small">
          키·체형·몸무게는 태어날 때 주사위로 정해졌고 바뀌지 않는다. 당신이 정하는 것은 능력치 포인트({preset.free_points}점)·클래스·성별
          뿐이다. 무기와 스킬은 단원이 자기 몸을 보고 고른다. 성향은 타고난 것이라 손댈 수 없다 — MBTI 는 이름표일 뿐이다.
        </p>
      </section>

      <section className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        {preset.roster.map((c) => (
          <RosterCard
            key={c.id}
            c={c}
            classes={preset.classes}
            statBase={preset.stat_base}
            freePoints={preset.free_points}
            alloc={allocs[c.id]}
            onAlloc={(a) => setAllocs((cur) => ({ ...cur, [c.id]: a }))}
            cls={classes[c.id]}
            onClass={(k) => setClasses((cur) => ({ ...cur, [c.id]: k }))}
            gender={genders[c.id]}
            onGender={(g) => setGenders((cur) => ({ ...cur, [c.id]: g }))}
            selected={lineup.includes(c.id)}
            selectable={lineup.length < preset.lineup_size || lineup.includes(c.id)}
            onToggle={() => toggleLineup(c.id)}
          />
        ))}
      </section>

      <section className="card" style={{ gap: 12 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="stack" style={{ gap: 2 }}>
            <div className="card-kicker">출전 · 폐광의 군주 (출전 {preset.lineup_size}명)</div>
            <div className="row small">
              {lineup.length === 0 ? (
                <span className="faint">카드에서 &ldquo;출전&rdquo;을 눌러 고른다</span>
              ) : (
                lineup.map((id) => (
                  <span key={id} className="tag tag-accent">
                    {preset.roster.find((c) => c.id === id)?.name}
                  </span>
                ))
              )}
            </div>
          </div>
          <div className="row small">
            <label className="row" style={{ gap: 4 }}>
              <input type="checkbox" checked={orchestrator} onChange={(e) => setOrchestrator(e.target.checked)} />
              단장(오케스트레이터)
            </label>
            <label className="row" style={{ gap: 4 }}>
              <input type="checkbox" checked={adaptation} onChange={(e) => setAdaptation(e.target.checked)} />
              보스 적응
            </label>
            <label className="row" style={{ gap: 4 }}>
              시드
              <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="무작위" style={{ width: 96 }} />
            </label>
          </div>
        </div>
        {problems.length > 0 && (
          <ul className="small" style={{ margin: 0, paddingLeft: 18, color: "var(--color-warn)" }}>
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
        {error && (
          <p className="small" style={{ color: "var(--color-danger)" }}>
            서버가 거절했다: {error}
          </p>
        )}
        <div className="row">
          <button className="btn btn-primary" disabled={busy || problems.length > 0} onClick={start}>
            {busy ? "출정 준비 중…" : "출정 →"}
          </button>
          <span className="small faint">
            포인트 합계: {preset.roster.map((c) => `${c.name.split(" ")[0]} ${total(allocs[c.id])}`).join(" · ")}
          </span>
        </div>
      </section>
    </main>
  );
}
