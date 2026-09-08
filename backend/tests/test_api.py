import json
import time

import pytest
from fastapi.testclient import TestClient

from adapters.harness.harness import Harness
from adapters.llm.fake import FakeModel
from adapters.store.jsonl import JsonlRunStore
from api.main import build_app


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
    kyle = next(c for c in body["roster"] if c["id"] == "kyle")
    assert kyle["mbti"] and "딸" in kyle["life"] and kyle["build_preview"]["weapon"]
    assert sum(kyle["recommended"].values()) == 18


def test_출전_인원_상한을_넘으면_422(client):
    r = client.post("/runs", json={"lineup": ["garret", "elaine", "kyle", "thomas"], "seed": 1})
    assert r.status_code == 422 and "1~3명" in r.json()["detail"]


def test_혼자_출전해도_받아준다(client):
    """기획서 §8.1 — 게임은 막지 않는다. 결과가 따라올 뿐이다."""
    assert client.post("/runs", json={"lineup": ["garret"], "seed": 1}).status_code == 200


def test_포인트_초과는_422(client):
    r = client.post(
        "/runs",
        json={
            "lineup": ["garret", "elaine", "kyle"],
            "allocations": {"garret": {"str_": 19}},
            "seed": 1,
        },
    )
    assert r.status_code == 422 and "18" in r.json()["detail"]


def test_없는_캐릭터는_422(client):
    r = client.post("/runs", json={"lineup": ["garret", "elaine", "ghost"], "seed": 1})
    assert r.status_code == 422


def test_런_생성_후_스트림은_run_start_로_시작해_done_으로_끝난다(client):
    r = client.post("/runs", json={"lineup": ["garret", "elaine", "kyle"], "seed": 8})
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
    run_id = client.post("/runs", json={"lineup": ["garret", "elaine", "kyle"], "seed": 8}).json()[
        "run_id"
    ]
    body = _wait_done(client, run_id)
    assert body["events"][0]["kind"] == "run_start"
    # 저장소에서도 읽힌다
    assert client.get("/runs").json()["runs"][0]["run_id"] == run_id


def test_리플레이는_같은_판을_다시_돌린다(client):
    run_id = client.post("/runs", json={"lineup": ["garret", "elaine", "kyle"], "seed": 8}).json()[
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
