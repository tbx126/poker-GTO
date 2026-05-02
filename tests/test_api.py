"""End-to-end API tests using FastAPI's TestClient.

Tests run a real (small) CFR+ solve to keep the wiring honest — total
time stays under a second."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_solve_kuhn_smoke():
    r = client.post("/solve/kuhn", json={"iters": 200, "chunks": 4})
    assert r.status_code == 200
    body = r.json()
    assert body["game"] == "kuhn"
    assert body["iters"] == 200
    assert len(body["trajectory"]) == 4
    # Trajectory must be monotonically non-increasing
    eps = [pt["exploitability"] for pt in body["trajectory"]]
    assert all(b <= a + 1e-6 for a, b in zip(eps, eps[1:])), f"trajectory regressed: {eps}"
    # Strategies returned for all known Kuhn infosets (3 cards × 4 history nodes = 12)
    assert len(body["strategies"]) == 12
    for s in body["strategies"]:
        assert len(s["actions"]) == len(s["probs"]) == 2
        assert abs(sum(s["probs"]) - 1.0) < 1e-6


def test_solve_leduc_smoke():
    r = client.post("/solve/leduc", json={"iters": 80, "chunks": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["game"] == "leduc"
    assert len(body["strategies"]) > 0
    # Action labels match Leduc grammar; probs normalize.
    for s in body["strategies"]:
        assert 2 <= len(s["actions"]) <= 3
        assert abs(sum(s["probs"]) - 1.0) < 1e-6


def test_solve_unknown_game_404():
    r = client.post("/solve/holdem", json={"iters": 10, "chunks": 1})
    # GameName Literal -> FastAPI validation -> 422
    assert r.status_code == 422


def test_solve_preflop_smoke():
    r = client.post("/solve/preflop", json={"iters": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["iters"] == 30
    assert len(body["panels"]) == 2

    # Each panel: 169 hand-class entries with normalized probs
    for panel in body["panels"]:
        assert panel["side"] in ("SB", "BB")
        assert len(panel["actions"]) == len(panel["action_kinds"])
        assert len(panel["by_class"]) == 169
        for label, probs in panel["by_class"].items():
            assert len(probs) == len(panel["actions"])
            assert abs(sum(probs) - 1.0) < 1e-6, f"{label} not normalized: {probs}"

    # Sanity: SB with AA should not fold
    sb_panel = next(p for p in body["panels"] if p["side"] == "SB")
    fold_idx = sb_panel["actions"].index("fold")
    assert sb_panel["by_class"]["AA"][fold_idx] < 0.05


def test_solve_preflop_validation():
    r = client.post("/solve/preflop", json={"iters": 0})
    assert r.status_code == 422
    r = client.post("/solve/preflop", json={"iters": 99999})
    assert r.status_code == 422


def test_solve_preflop_with_locks():
    """Lock SB AA to 100% shove and verify response reflects it."""
    r = client.post("/solve/preflop", json={
        "iters": 30,
        "locks": [
            {"history": [], "hand": "AA", "probs": [0.0, 0.0, 1.0]},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    sb_panel = next(p for p in body["panels"] if p["side"] == "SB")
    shove_idx = sb_panel["actions"].index("shove")
    assert sb_panel["by_class"]["AA"][shove_idx] == pytest.approx(1.0, abs=1e-9)


def test_solve_preflop_invalid_lock_returns_422():
    """Probs that don't sum to 1 should be rejected."""
    r = client.post("/solve/preflop", json={
        "iters": 5,
        "locks": [
            {"history": [], "hand": "AA", "probs": [0.5, 0.0, 0.0]},
        ],
    })
    assert r.status_code == 422

    r = client.post("/solve/preflop", json={
        "iters": 5,
        "locks": [
            {"history": ["nonsense"], "hand": "AA", "probs": [1.0, 0.0, 0.0]},
        ],
    })
    assert r.status_code == 422

    r = client.post("/solve/preflop", json={
        "iters": 5,
        "locks": [
            {"history": [], "hand": "ZZZ", "probs": [1.0, 0.0, 0.0]},
        ],
    })
    assert r.status_code == 422


def test_solve_iters_validation():
    r = client.post("/solve/kuhn", json={"iters": 0, "chunks": 1})
    assert r.status_code == 422
    r = client.post("/solve/kuhn", json={"iters": 999_999_999, "chunks": 1})
    assert r.status_code == 422


def test_cors_preflight_allows_any_localhost_port():
    """Vite often falls through 5173 → 5174 → 5175 — regex CORS must cover it."""
    for port in (5173, 5174, 5175):
        r = client.options(
            "/solve/kuhn",
            headers={
                "Origin": f"http://localhost:{port}",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert r.status_code == 200, f"port {port}"
        assert r.headers.get("access-control-allow-origin") == f"http://localhost:{port}"

    # Non-localhost origin must NOT be allowed
    r = client.options(
        "/solve/kuhn",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.headers.get("access-control-allow-origin") is None
