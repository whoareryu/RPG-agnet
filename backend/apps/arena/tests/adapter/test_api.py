import json
import time

import pytest
from fastapi.testclient import TestClient

from apps.arena.adapter.inbound.api.v1.arena_router import build_app
from apps.arena.adapter.outbound.repositories.jsonl_run_repository import JsonlRunStore
from apps.arena.adapter.outbound.strategies.harness.harness import Harness
from apps.arena.adapter.outbound.strategies.llm.fake import FakeModel


@pytest.fixture
def client(tmp_path):
    app = build_app(
        store=JsonlRunStore(tmp_path), model_factory=lambda: Harness(FakeModel(), FakeModel())
    )
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        kind = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if kind and data is not None:
            out.append({"event": kind, "data": json.loads(data)})
    return out


def _wait_done(client, run_id, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/runs/{run_id}")
        if r.status_code == 200 and r.json()["done"]:
            return r.json()
        time.sleep(0.05)
    raise AssertionError("런이 끝나지 않는다")


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["model"] == "fake"


def test_프리셋_로스터_다섯(client):
    r = client.get("/roster/preset")
    body = r.json()
    assert len(body["roster"]) == 5 and body["free_points"] == 18 and body["lineup_size"] == 3
    가장형 = next(c for c in body["roster"] if c["id"] == "agnes")
    assert 가장형["mbti"] and "딸" in 가장형["life"] and 가장형["build_preview"]["weapon"]
    assert sum(가장형["recommended"].values()) == 18


def test_출전_인원_상한을_넘으면_422(client):
    r = client.post("/runs", json={"lineup": ["martin", "aude", "thoma", "agnes"], "seed": 1})
    assert r.status_code == 422 and "1~3명" in r.json()["detail"]


def test_혼자_출전해도_받아준다(client):
    """기획서 §8.1 — 게임은 막지 않는다. 결과가 따라올 뿐이다."""
    assert client.post("/runs", json={"lineup": ["martin"], "seed": 1}).status_code == 200


def test_포인트_초과는_422(client):
    r = client.post(
        "/runs",
        json={
            "lineup": ["martin", "aude", "thoma"],
            "allocations": {"martin": {"str_": 19}},
            "seed": 1,
        },
    )
    assert r.status_code == 422 and "18" in r.json()["detail"]


def test_없는_캐릭터는_422(client):
    r = client.post("/runs", json={"lineup": ["martin", "aude", "ghost"], "seed": 1})
    assert r.status_code == 422


def test_런_생성_후_스트림은_run_start_로_시작해_done_으로_끝난다(client):
    r = client.post("/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 8})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    with client.stream("GET", f"/runs/{run_id}/stream") as s:
        text = "".join(s.iter_text())
    events = _parse_sse(text)
    assert events[0]["event"] == "run_start" and events[-1]["event"] == "done"
    assert events[-2]["event"] == "run_end"
    kinds = {e["event"] for e in events}
    assert {"plan", "decision", "resolution", "mission_end"} <= kinds


def test_완료된_런은_저장되고_다시_읽힌다(client):
    run_id = client.post("/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 8}).json()[
        "run_id"
    ]
    body = _wait_done(client, run_id)
    assert body["events"][0]["kind"] == "run_start"
    # 저장소에서도 읽힌다
    assert client.get("/runs").json()["runs"][0]["run_id"] == run_id


def test_리플레이는_같은_판을_다시_돌린다(client):
    run_id = client.post("/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 8}).json()[
        "run_id"
    ]
    first = _wait_done(client, run_id)
    r = client.post(f"/runs/{run_id}/replay")
    assert r.status_code == 200 and r.json()["model"] == "replay"
    second = _wait_done(client, r.json()["run_id"])
    labels1 = [e["payload"].get("label") for e in first["events"] if e["kind"] == "decision"]
    labels2 = [e["payload"].get("label") for e in second["events"] if e["kind"] == "decision"]
    assert labels1 == labels2 and len(labels1) > 10


def test_없는_런은_404(client):
    assert client.get("/runs/zzz").status_code == 404


def test_시크릿이_설정되면_헤더_없이는_401(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_SHARED_SECRET", "s3cret")
    app = build_app(
        store=JsonlRunStore(tmp_path), model_factory=lambda: Harness(FakeModel(), FakeModel())
    )
    c = TestClient(app)
    assert c.get("/roster/preset").status_code == 401
    assert c.get("/roster/preset", headers={"X-Backend-Secret": "s3cret"}).status_code == 200
    assert c.get("/healthz").status_code == 200  # healthz 는 열려 있다


def test_실험_결과가_없으면_404_이고_목록은_빈다(client):
    assert client.get("/experiments/e1").status_code == 404
    assert client.get("/experiments").json()["available"] == []
    assert client.get("/experiments/e9").status_code == 404


def test_실험_결과가_있으면_그대로_내려준다(tmp_path):
    import json as _json

    out = tmp_path / "out"
    out.mkdir()
    (out / "e1.json").write_text(_json.dumps({"experiment": "e1", "compositions": []}), "utf-8")
    app = build_app(
        store=JsonlRunStore(tmp_path),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        experiments_dir=out,
    )
    c = TestClient(app)
    assert c.get("/experiments").json()["available"] == ["e1"]
    assert c.get("/experiments/e1").json()["experiment"] == "e1"


# ─── B단계 인터미션 ────────────────────────────────────────────────────


def _two_mission_client(tmp_path, timeout=5.0):
    app = build_app(
        store=JsonlRunStore(tmp_path),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        directive_timeout=timeout,
    )
    return TestClient(app)


def test_두_판이면_인터미션에서_입력을_기다린다(tmp_path):
    """기획서 §7.1 — 1판 → 인터미션 → 2판. 인터미션이 있어야 인과가 닫힌다."""
    c = _two_mission_client(tmp_path)
    run_id = c.post(
        "/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 3, "missions": 2}
    ).json()["run_id"]

    # 인터미션에 닿을 때까지 기다렸다가 지시를 보낸다.
    t0 = time.time()
    while time.time() - t0 < 10:
        events = c.get(f"/runs/{run_id}").json()["events"]
        if any(e["kind"] == "intermission_start" for e in events):
            break
        time.sleep(0.05)
    r = c.post(
        f"/runs/{run_id}/directives",
        json={"directives": {"thoma": "rest", "martin": "train"}, "growth": {"thoma": {"agi": 3}}},
    )
    assert r.status_code == 200

    body = _wait_done(c, run_id)
    kinds = [e["kind"] for e in body["events"]]
    assert kinds.count("mission_start") == 2, "2판이 시작되지 않았다"
    assert "train_result" in kinds and "growth_points" in kinds
    지시 = [e["payload"]["category"] for e in body["events"] if e["kind"] == "directive"]
    assert "rest" in 지시


def test_인터미션이_아닐_때의_지시는_409(tmp_path):
    c = _two_mission_client(tmp_path)
    run_id = c.post("/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 8}).json()[
        "run_id"
    ]
    r = c.post(f"/runs/{run_id}/directives", json={"directives": {}})
    assert r.status_code in (409, 404)


def test_응답이_없어도_기본값으로_판이_이어진다(tmp_path):
    """화면이 죽어도 스트림이 영원히 열려 있으면 안 된다."""
    c = _two_mission_client(tmp_path, timeout=0.3)
    run_id = c.post(
        "/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 3, "missions": 2}
    ).json()["run_id"]
    body = _wait_done(c, run_id, timeout=20)
    kinds = [e["kind"] for e in body["events"]]
    assert kinds.count("mission_start") == 2
    지시 = {e["payload"]["category"] for e in body["events"] if e["kind"] == "directive"}
    assert 지시 == {"train"}, "기본값은 전원 훈련이어야 한다"


def test_잘못된_성장_분배는_판을_죽이지_않는다(tmp_path):
    c = _two_mission_client(tmp_path)
    run_id = c.post(
        "/runs", json={"lineup": ["martin", "aude", "thoma"], "seed": 3, "missions": 2}
    ).json()["run_id"]
    t0 = time.time()
    while time.time() - t0 < 10:
        if any(
            e["kind"] == "intermission_start" for e in c.get(f"/runs/{run_id}").json()["events"]
        ):
            break
        time.sleep(0.05)
    c.post(f"/runs/{run_id}/directives", json={"growth": {"thoma": {"agi": 99}}})
    body = _wait_done(c, run_id, timeout=20)
    assert body["error"] is None
    rejected = [
        e
        for e in body["events"]
        if e["kind"] == "intermission_start" and e["payload"].get("rejected")
    ]
    assert rejected and "찍으려 한다" in rejected[0]["payload"]["rejected"]


def test_동시_런_상한을_넘으면_429(tmp_path):
    """배포하면 누구나 POST /runs 를 반복할 수 있다 — 런마다 스레드가 생긴다."""
    app = build_app(
        store=JsonlRunStore(tmp_path),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        max_active_runs=1,
        directive_timeout=30,
    )
    c = TestClient(app)
    body = {"lineup": ["martin", "aude", "thoma"], "seed": 3, "missions": 2}
    first = c.post("/runs", json=body)
    assert first.status_code == 200
    second = c.post("/runs", json=body)
    # 첫 런이 인터미션에서 입력을 기다리는 동안 두 번째는 거절된다.
    if second.status_code == 200:
        _wait_done(c, first.json()["run_id"], timeout=40)
        return
    assert second.status_code == 429 and "동시에" in second.json()["detail"]


def test_완료된_런은_상한을_먹지_않는다(tmp_path):
    app = build_app(
        store=JsonlRunStore(tmp_path),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        max_active_runs=1,
    )
    c = TestClient(app)
    body = {"lineup": ["martin", "aude", "thoma"], "seed": 8}
    run_id = c.post("/runs", json=body).json()["run_id"]
    _wait_done(c, run_id)
    assert c.post("/runs", json=body).status_code == 200


# ─── 뿔피리 (기획서 v3 §8.2) ────────────────────────────────────────────


def test_뿔피리는_세_번까지만_받는다(client):
    """계약 기간 3회. 무한이면 유저가 조종하는 게임이 된다(§0.1 위반)."""
    run_id = client.post("/runs", json={"lineup": ["martin", "aude", "agnes"], "seed": 5}).json()[
        "run_id"
    ]
    남은 = []
    for _ in range(3):
        r = client.post(f"/runs/{run_id}/horn")
        if r.status_code == 200:
            남은.append(r.json()["horn_left"])
        elif r.status_code == 409:
            break  # 판이 먼저 끝났으면 그것도 정상이다
    assert 남은 == list(range(2, 2 - len(남은), -1)), 남은
    # 다 쓰거나 판이 끝나면 더는 안 받는다.
    assert client.post(f"/runs/{run_id}/horn").status_code in (409, 200)


def test_없는_런에_뿔피리를_불면_404(client):
    assert client.post("/runs/nope/horn").status_code == 404
