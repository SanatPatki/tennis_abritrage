"""De-vig methods for two-way markets. See AGENTS.md §6.1."""

from __future__ import annotations

import math


def implied_probs(o1: float, o2: float) -> tuple[float, float]:
    return 1.0 / o1, 1.0 / o2


def _bisect(f, lo: float, hi: float, tol: float = 1e-12, max_iter: int = 200) -> float:
    flo, fhi = f(lo), f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0:
        raise ValueError(f"root not bracketed: f({lo})={flo}, f({hi})={fhi}")
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) / 2 < tol:
            return mid
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def devig_multiplicative(o1: float, o2: float) -> tuple[float, float]:
    r1, r2 = implied_probs(o1, o2)
    total = r1 + r2
    return r1 / total, r2 / total


def devig_power(o1: float, o2: float) -> tuple[float, float]:
    """Solve k so that (1/o1)**k + (1/o2)**k == 1, then p_i = (1/o_i)**k."""
    r1, r2 = implied_probs(o1, o2)
    k = _bisect(lambda k: r1**k + r2**k - 1.0, 0.5, 2.0)
    return r1**k, r2**k


def devig_shin(o1: float, o2: float) -> tuple[float, float]:
    """Shin's z-model, solved numerically for the two-outcome case."""
    raise NotImplementedError(
        "devig_shin not yet implemented — default method is multiplicative (AGENTS.md §6.1)"
    )


DEVIG_METHODS = {
    "multiplicative": devig_multiplicative,
    "power": devig_power,
    "shin": devig_shin,
}
