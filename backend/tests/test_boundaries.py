"""계층 경계를 CI 가 강제한다.

설계 §3.3 의 규칙을 문서가 아니라 테스트로 만든다. secu-agent 의 같은 이름
테스트를 이식했고, 이 프로젝트 고유의 격리 셋(성별 · 행운)을 더했다.
"""

import ast
from pathlib import Path

import pytest

# core/ 는 안쪽이다. content 도 바깥이다 — 세계관 데이터가 규칙 엔진에
# 스며들면 밸런스 튠이 코드 수정이 된다(설계 §3.3).
바깥_계층 = ("adapters", "api", "eval", "content", "tests")

인프라_프레임워크 = (
    "fastapi",
    "google",
    "langchain",
    "langchain_core",
    "langgraph",
    "anthropic",
    "pydantic",
    "httpx",
    "yaml",
    "uvicorn",
)


def _모듈_이름들_추출(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return [n.split(".")[0] for n in names]


def _최상위_import(py: Path) -> list[str]:
    return _모듈_이름들_추출(ast.parse(py.read_text(encoding="utf-8")))


def _core_파일들() -> list[Path]:
    return sorted(Path("core").rglob("*.py"))


def _속성_접근_파일들(root: str, attr: str) -> set[str]:
    """root 아래에서 `.attr` 속성을 읽는 파일 집합."""
    hits: set[str] = set()
    for py in sorted(Path(root).rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == attr:
                hits.add(str(py))
    return hits


def test_core_에_검사할_파일이_있다():
    assert _core_파일들(), "core/ 에 파이썬 파일이 없다"


@pytest.mark.parametrize("py", _core_파일들(), ids=lambda p: str(p))
def test_core_는_바깥_계층을_import_하지_않는다(py):
    for name in _최상위_import(py):
        assert name not in 바깥_계층, f"{py} 가 바깥 계층 {name} 을 import 한다"


@pytest.mark.parametrize("py", _core_파일들(), ids=lambda p: str(p))
def test_core_는_인프라_프레임워크를_import_하지_않는다(py):
    for name in _최상위_import(py):
        assert name not in 인프라_프레임워크, f"{py} 가 {name} 을 import 한다"


@pytest.mark.parametrize("py", _core_파일들(), ids=lambda p: str(p))
def test_core_는_random_을_직접_쓰지_않는다(py):
    """난수는 전부 Dice 포트를 통한다 — 같은 시드 = 같은 판(설계 §3.4).

    예외는 SeededDice 자신뿐이다. random.Random 을 감싸는 곳이 거기다.
    """
    if py.name == "dice.py":
        return
    assert "random" not in _최상위_import(py), f"{py} 가 random 을 직접 import 한다"


def test_성별은_엔진에_닿지_않는다():
    """기획서 §4.4 "전투·능력치·판단 엔진에 영향 0" 을 테스트로 만든다.

    허용되는 곳은 서사 표기(core/agents/narration.py)뿐이다.
    """
    금지_영역 = ("core/rules", "core/battle", "core/judgment", "core/intermission")
    for root in 금지_영역:
        if not Path(root).exists():
            continue
        hits = _속성_접근_파일들(root, "gender")
        assert not hits, f"{root} 가 gender 를 읽는다: {hits}"
    if Path("core/agents").exists():
        agents_hits = _속성_접근_파일들("core/agents", "gender")
        허용 = {"core/agents/narration.py"}
        assert agents_hits <= 허용, f"narration 밖에서 gender 를 읽는다: {agents_hits}"


def test_행운은_판단에_개입하지_않는다():
    """기획서 §4.2 — 행운은 굴림에만. core/judgment 는 luck 을 읽지 않는다."""
    if not Path("core/judgment").exists():
        return
    hits = _속성_접근_파일들("core/judgment", "luck")
    assert not hits, f"core/judgment 가 luck 을 읽는다: {hits}"
