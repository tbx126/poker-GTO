"""FastAPI app entry point.

Run with:  uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    GameName,
    PreflopRequest,
    PreflopResponse,
    SolveRequest,
    SolveResponse,
)
from api.service import solve, solve_preflop

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


@app.post("/solve/preflop", response_model=PreflopResponse)
def solve_preflop_endpoint(req: PreflopRequest) -> PreflopResponse:
    try:
        return solve_preflop(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/solve/{game}", response_model=SolveResponse)
def solve_endpoint(game: GameName, req: SolveRequest) -> SolveResponse:
    return solve(game, req)
