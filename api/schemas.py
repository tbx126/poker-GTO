"""Request / response schemas for the solver API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


GameName = Literal["kuhn", "leduc"]
PanelSide = Literal["SB", "BB"]


class SolveRequest(BaseModel):
    iters: int = Field(default=2000, ge=1, le=200_000, description="CFR+ iterations to run")
    chunks: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Trajectory points to record (iters split evenly).",
    )


class TrajectoryPoint(BaseModel):
    iter: int
    exploitability: float


class StrategyEntry(BaseModel):
    """Average strategy at one infoset.

    `actions` and `probs` are aligned arrays — easier on the frontend than
    a map, and keeps action ordering deterministic."""

    infoset: str
    actions: list[str]
    probs: list[float]


class SolveResponse(BaseModel):
    game: GameName
    iters: int
    final_exploitability: float
    trajectory: list[TrajectoryPoint]
    strategies: list[StrategyEntry]
    elapsed_ms: int


# ----- preflop subgame -----


class PreflopLock(BaseModel):
    """Pin one (history, hand-class) infoset to a fixed strategy.

    `history` is the action sequence leading to the locked infoset, e.g.
    `[]` for the SB's first decision or `["open"]` for BB facing the open.
    `probs` must align with the actions of that infoset and sum to 1."""

    history: list[str] = Field(default_factory=list)
    hand: str
    probs: list[float]


class TreeConfig(BaseModel):
    """Heads-up bet ladder. All values in big blinds.

    Validated by the solver — invalid ladders (e.g. open >= 3bet) are
    rejected with a 422."""

    stack: float = Field(default=100.0, gt=0)
    sb_blind: float = Field(default=0.5, gt=0)
    bb_blind: float = Field(default=1.0, gt=0)
    open_to: float = Field(default=2.5, gt=0)
    threebet_to: float = Field(default=9.0, gt=0)
    fourbet_to: float | None = Field(default=None, ge=0)


class PreflopRequest(BaseModel):
    iters: int = Field(default=80, ge=1, le=2000, description="CFR+ iterations")
    locks: list[PreflopLock] = Field(default_factory=list)
    tree: TreeConfig = Field(default_factory=TreeConfig)


class PreflopPanel(BaseModel):
    side: PanelSide
    title: str
    subtitle: str
    history: list[str]                          # the infoset history this panel maps to
    actions: list[str]                          # solver-side action labels
    action_kinds: list[str]                     # frontend color-bucket per action
    by_class: dict[str, list[float]]            # 169 hand-class labels -> probs


class PreflopResponse(BaseModel):
    iters: int
    final_exploitability: float
    elapsed_ms: int
    panels: list[PreflopPanel]                  # [OOP_BB_defense, IP_SB_open]
