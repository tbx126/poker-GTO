"""All-in equity for the 169-class preflop abstraction.

`equity_table()` returns a 169×169 numpy matrix `M` where M[i, j] is the
expected showdown equity of class i against class j over a uniformly
random board, conditioned on no card conflict between the two combos.

The first call generates and caches to `data/preflop_equity_169.npy`
(~228KB). Default 500 MC samples per ordered pair gives ~±2% noise; the
sampled diagonal element should sit near 0.5.

Inner loop is integer-only (uint64 masks); no Card object allocation.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

import numpy as np

from engine.evaluator import evaluate7
from engine.hand_class import all_classes, class_combos


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CACHE_FILE = _DATA_DIR / "preflop_equity_169.npy"
_DEFAULT_SAMPLES = 500
_DECK_BITS = (1 << 52) - 1


def _combo_masks_for_class(label: str) -> list[int]:
    """Precomputed list of uint64 hole-card masks for one class."""
    return [c1.mask | c2.mask for c1, c2 in class_combos(label)]


def class_vs_class_equity(
    masks_a: list[int],
    masks_b: list[int],
    samples: int,
    rng: random.Random,
) -> float:
    """Monte Carlo expected equity of class-A combos vs class-B combos.

    Rejects samples where the two combos share a card."""
    n_a = len(masks_a)
    n_b = len(masks_b)
    wins = 0.0
    n = 0
    while n < samples:
        ma = masks_a[rng.randrange(n_a)]
        mb = masks_b[rng.randrange(n_b)]
        if ma & mb:
            continue
        # Sample 5 board cards from the 48 not in ma|mb
        used = ma | mb
        board_mask = 0
        picked = 0
        while picked < 5:
            idx = rng.randrange(52)
            bit = 1 << idx
            if used & bit:
                continue
            used |= bit
            board_mask |= bit
            picked += 1
        sa = evaluate7(ma | board_mask)
        sb = evaluate7(mb | board_mask)
        if sa > sb:
            wins += 1.0
        elif sa == sb:
            wins += 0.5
        n += 1
    return wins / n if n else 0.5


def build_equity_table(
    samples_per_pair: int = _DEFAULT_SAMPLES,
    seed: int = 42,
    progress: bool = True,
) -> np.ndarray:
    """Build the full 169×169 expected-equity matrix.

    Diagonals (class vs same class) are sampled too — they should land
    near 0.5 since the matchup is symmetric over draws.
    Off-diagonals: M[i, j] sampled, M[j, i] = 1 - M[i, j] (no second sample)."""
    classes = all_classes()
    n = len(classes)
    masks_per_class = [_combo_masks_for_class(c.label) for c in classes]

    M = np.full((n, n), 0.5, dtype=np.float32)
    rng = random.Random(seed)
    started = time.perf_counter()
    total_pairs = n + (n * (n - 1)) // 2

    done = 0
    for i in range(n):
        eq_diag = class_vs_class_equity(masks_per_class[i], masks_per_class[i], samples_per_pair, rng)
        M[i, i] = eq_diag
        done += 1
        for j in range(i + 1, n):
            eq = class_vs_class_equity(masks_per_class[i], masks_per_class[j], samples_per_pair, rng)
            M[i, j] = eq
            M[j, i] = 1.0 - eq
            done += 1
        if progress and (i % 20 == 19 or i == n - 1):
            elapsed = time.perf_counter() - started
            pct = 100.0 * done / total_pairs
            print(f"  equity: {done:>6}/{total_pairs} ({pct:5.1f}%)  elapsed {elapsed:6.1f}s", flush=True)

    return M


_TABLE_CACHE: np.ndarray | None = None


def equity_table(
    samples_per_pair: int = _DEFAULT_SAMPLES,
    force_rebuild: bool = False,
) -> np.ndarray:
    """Load from disk (memoised) or compute. Returns float32 169×169."""
    global _TABLE_CACHE
    if _TABLE_CACHE is not None and not force_rebuild:
        return _TABLE_CACHE
    if _CACHE_FILE.exists() and not force_rebuild:
        m = np.load(_CACHE_FILE)
        if m.shape == (169, 169):
            _TABLE_CACHE = m
            return m
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"building preflop equity table ({samples_per_pair} samples/pair)...", flush=True)
    M = build_equity_table(samples_per_pair=samples_per_pair)
    np.save(_CACHE_FILE, M)
    _TABLE_CACHE = M
    return M


if __name__ == "__main__":
    import sys

    s = int(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_SAMPLES
    M = equity_table(samples_per_pair=s, force_rebuild=True)
    print(f"\ntable saved to {_CACHE_FILE}")
    print(f"AA vs 22:  {M[0, 12]:.3f}  (textbook ~0.80)")
    print(f"AA vs KK:  {M[0, 1]:.3f}  (textbook ~0.82)")
    print(f"AKs vs 22: {M[13, 12]:.3f} (textbook ~0.50)")
    print(f"72o vs AA: {M[168, 0]:.3f} (textbook ~0.13)")
