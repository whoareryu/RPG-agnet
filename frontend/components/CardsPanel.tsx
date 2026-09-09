"use client";

import type { TraceEvent } from "@/lib/trace";

const SOURCE_KO: Record<string, string> = {
  scout: "고블린의 척후 관찰",
  flight: "놀의 탈주 추적",
  loot: "오크의 전리품",
  feeding: "섭식",
};

type Card = {
  key: string;
  name: string;
  source: string;
  observation: string;
  evidence: Record<string, unknown>;
  applied: Record<string, unknown>;
};

/**
 * 학습 카드 패널 — 보스전 시작에 펼쳐진다(기획서 v3 §8.4).
 *
 * 여기가 이 시나리오의 심장이다. 보스 적응이 기술 차트가 아니라 **죄책감**으로
 * 전달된다 — 유저가 안 한 것(회수)이 카드가 되어 눈앞에 있다.
 */
export default function CardsPanel({
  event,
  names,
}: {
  event: TraceEvent;
  names: Record<string, string>;
}) {
  const cards = (event.payload.cards as Card[]) ?? [];
  if (!cards.length) return null;

  return (
    <section className="card stack" style={{ gap: 10, borderColor: "var(--color-accent)" }}>
      <div className="card-kicker">그것이 배운 것</div>
      <ul className="stack" style={{ gap: 10, listStyle: "none", padding: 0, margin: 0 }}>
        {cards.map((c) => {
          const who = c.evidence?.member ? String(c.evidence.member) : null;
          return (
            <li key={c.key} className="stack" style={{ gap: 3 }}>
              <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
                <strong>「{c.name}」</strong>
                <span className="faint small">출처: {SOURCE_KO[c.source] ?? c.source}</span>
              </div>
              <p className="small" style={{ margin: 0 }}>
                관측: {c.observation}
              </p>
              {c.source === "feeding" && who && (
                <p className="small" style={{ margin: 0, color: "var(--color-accent)" }}>
                  이 보스는 당신이 굴에 두고 온 {names[who] ?? who}에게서 이걸 배웠습니다.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
