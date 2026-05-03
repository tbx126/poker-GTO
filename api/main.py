"""FastAPI app entry point.

Run with:  uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    ActionSubmission,
    DeepCFRRequest,
    DeepCFRResponse,
    FeedbackResponse,
    GameName,
    HandHistoryUpload,
    LeakReportResponse,
    PlayerStatsResponse,
    PreflopRequest,
    PreflopResponse,
    ScenarioRequest,
    ScenarioResponse,
    SolveRequest,
    SolveResponse,
    TendencyReportResponse,
    TrainingStatsResponse,
)
from api.service import (
    detect_player_leaks,
    generate_training_scenario,
    get_player_stats,
    get_population_tendency,
    get_training_stats,
    solve,
    solve_postflop,
    solve_preflop,
    submit_training_action,
    upload_hand_history,
)

app = FastAPI(
    title="Poker GTO Solver",
    description="HTTP wrapper around the tabular CFR+ engine.",
    version="0.1.0",
)

# Allow any localhost port so the Vite dev server is reachable even when
# 5173 is taken and Vite falls through to 5174/5175. Tighten in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/solve/postflop", response_model=DeepCFRResponse)
def solve_postflop_endpoint(req: DeepCFRRequest) -> DeepCFRResponse:
    """Solve postflop using Deep CFR with neural networks."""
    try:
        return solve_postflop(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/solve/preflop", response_model=PreflopResponse)
def solve_preflop_endpoint(req: PreflopRequest) -> PreflopResponse:
    try:
        return solve_preflop(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/solve/{game}", response_model=SolveResponse)
def solve_endpoint(game: GameName, req: SolveRequest) -> SolveResponse:
    return solve(game, req)


# ----- MDA endpoints -----


@app.post("/mda/upload")
def upload_hand_history_endpoint(req: HandHistoryUpload) -> dict:
    """Upload hand history for analysis."""
    try:
        return upload_hand_history(req.raw_text, req.format)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.get("/mda/player/{player_name}", response_model=PlayerStatsResponse)
def get_player_stats_endpoint(player_name: str) -> PlayerStatsResponse:
    """Get player statistics."""
    try:
        return get_player_stats(player_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/mda/tendency/{situation}", response_model=TendencyReportResponse)
def get_tendency_endpoint(situation: str) -> TendencyReportResponse:
    """Get population tendency report."""
    try:
        return get_population_tendency(situation)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/mda/leaks/{player_name}", response_model=LeakReportResponse)
def detect_leaks_endpoint(player_name: str) -> LeakReportResponse:
    """Detect leaks in player's game."""
    try:
        return detect_player_leaks(player_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ----- GTO Trainer endpoints -----


@app.post("/trainer/scenario", response_model=ScenarioResponse)
def generate_scenario_endpoint(req: ScenarioRequest) -> ScenarioResponse:
    """Generate training scenario."""
    try:
        return generate_training_scenario(req.difficulty, req.situation_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/trainer/action", response_model=FeedbackResponse)
def submit_action_endpoint(req: ActionSubmission) -> FeedbackResponse:
    """Submit action for training scenario."""
    try:
        return submit_training_action(req.scenario_id, req.action, req.time_taken_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/trainer/stats", response_model=TrainingStatsResponse)
def get_training_stats_endpoint() -> TrainingStatsResponse:
    """Get training statistics."""
    try:
        return get_training_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
