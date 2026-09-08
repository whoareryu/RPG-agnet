"""평가 하네스는 회귀 안전망이다(기획서 §10.1). 이 테스트가 그 안전망을 지킨다."""

import json

from eval.experiments import COMPOSITIONS, _run_once, e1, e3
from eval.metrics import aggregate


def test_지표는_트레이스_후처리만으로_나온다():
    """러너를 고쳐야 지표가 나오면 실험이 코어를 건드리게 된다(기획서 §3.1)."""
    m = _run_once(1, ("garret", "elaine", "kyle"), {}, orchestrator=True, adaptation=True)
    assert m.outcome in ("win", "lose", "retreat", "draw")
    assert m.party_size == 3 and 0 <= m.survivors <= 3
    assert m.turns > 0 and m.calls > 0
    assert sum(m.actions.values()) > 0


def test_집계는_비율과_평균을_낸다():
    runs = [
        _run_once(s, ("garret", "elaine", "kyle"), {}, orchestrator=True, adaptation=True)
        for s in range(1, 4)
    ]
    a = aggregate(runs)
    assert a["games"] == 3
    for k in ("win_rate", "retreat_rate", "loss_rate", "draw_rate", "survival_rate"):
        assert 0.0 <= a[k] <= 1.0
    assert abs(a["win_rate"] + a["retreat_rate"] + a["loss_rate"] + a["draw_rate"] - 1.0) < 1e-9
    assert a["max_calls"] <= 300, "호출 상한(기획서 §7.1)을 넘었다"


def test_E1_은_같은_시드로_같은_결과를_낸다():
    """실험이 재현되지 않으면 차트가 근거가 되지 못한다(설계 §3.4)."""
    a = e1(seeds=2)
    b = e1(seeds=2)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_E1_은_조합_넷과_ON_OFF_를_모두_담는다():
    r = e1(seeds=2)
    assert {c["key"] for c in r["compositions"]} == {c.key for c in COMPOSITIONS}
    for c in r["compositions"]:
        assert c["on"]["games"] == 2 and c["off"]["games"] == 2
        assert c["off"]["avg_plans"] == 0, "감독 OFF 인데 작전이 수립됐다"
        assert c["on"]["avg_plans"] > 0, "감독 ON 인데 작전이 없다"


def test_E3_은_성향_수치만_바꾼다():
    r = e3(seeds=2)
    axes = {a["axis"] for a in r["axes"]}
    assert axes == {"risk", "sacrifice", "cooperation"}
    for a in r["axes"]:
        assert [row["level"] for row in a["levels"]] == [-80, 0, 80]


def test_희생_수용도가_높으면_이탈이_줄어든다():
    """기획서 §5.1 "항상 순응하는 캐릭터가 최강인가" 의 재료 — 축이 실제로 듣는가."""
    r = e3(seeds=4)
    sac = next(a for a in r["axes"] if a["axis"] == "sacrifice")
    낮음 = next(x for x in sac["levels"] if x["level"] == -80)["avg_deviations"]
    높음 = next(x for x in sac["levels"] if x["level"] == 80)["avg_deviations"]
    assert 높음 < 낮음, f"희생 수용도가 이탈에 영향이 없다: {낮음} → {높음}"
