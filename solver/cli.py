"""Command-line entry to train CFR+ on toy games.

Usage:
  python -m solver.cli kuhn --iters 20000
  python -m solver.cli leduc --iters 5000
"""

from __future__ import annotations

import argparse
import sys

from solver.cfr import CFRPlus, exploitability
from solver.games.kuhn import KuhnGame


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("game", choices=["kuhn", "leduc"])
    p.add_argument("--iters", type=int, default=10000)
    p.add_argument("--report-every", type=int, default=2000)
    args = p.parse_args()

    if args.game == "kuhn":
        game = KuhnGame()
    else:
        from solver.games.leduc import LeducGame
        game = LeducGame()

    solver = CFRPlus(game)
    print(f"training CFR+ on {args.game} for {args.iters} iters")

    chunk = max(1, args.report_every)
    done = 0
    while done < args.iters:
        step = min(chunk, args.iters - done)
        solver.train(step)
        done += step
        eps = exploitability(game, solver.average_strategies())
        print(f"iter {done:>6}  exploitability = {eps:.6f}")

    print("\naverage strategy (top infosets):")
    items = sorted(solver.strategy_sum.keys())[:20]
    for key in items:
        avg = solver.average_strategy(key)
        probs = " ".join(f"{x:.3f}" for x in avg)
        print(f"  {key:<20} -> {probs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
