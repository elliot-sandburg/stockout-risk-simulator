"""Replenishment formulas and a Monte Carlo simulator for stockout risk (v1).

Units: demand in units per day, lead times in whole days, order quantity in units.
Daily demand is a normal draw floored at zero, plus an optional spike on some days.
Unmet demand during a stockout is lost, not backordered.

Three reorder points are supported:
- static: textbook formula that ignores lead-time variability
- closed form: normal approximation that includes lead-time variability
- simulated: the target quantile of simulated lead-time demand, spikes included
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Sequence

import numpy as np

_STD_NORMAL = NormalDist()


# ---------------------------------------------------------------------------
# Closed-form math
# ---------------------------------------------------------------------------

def z_for_service_level(csl: float) -> float:
    """Standard normal quantile for a cycle service level, e.g. 0.95 -> 1.645."""
    _check_csl(csl)
    return _STD_NORMAL.inv_cdf(csl)


def daily_demand_moments(
    base_mean: float,
    base_sd: float,
    spike_prob: float = 0.0,
    spike_size: float = 0.0,
) -> tuple[float, float]:
    """Mean and standard deviation of one day's demand, spikes included.

    Exact when base_mean is at least about five times base_sd, because then
    flooring the normal draw at zero is negligible.
    """
    mean = base_mean + spike_prob * spike_size
    variance = base_sd**2 + spike_prob * (1.0 - spike_prob) * spike_size**2
    return mean, math.sqrt(variance)


def lead_time_demand_sd(
    daily_mean: float,
    daily_sd: float,
    lead_mean: float,
    lead_sd: float,
) -> float:
    """SD of demand over a random lead time, with lead time and demand independent."""
    return math.sqrt(lead_mean * daily_sd**2 + daily_mean**2 * lead_sd**2)


def closed_form_reorder_point(
    daily_mean: float,
    daily_sd: float,
    lead_mean: float,
    lead_sd: float,
    csl: float,
) -> float:
    """Expected demand over lead time plus z times its standard deviation."""
    z = z_for_service_level(csl)
    return daily_mean * lead_mean + z * lead_time_demand_sd(daily_mean, daily_sd, lead_mean, lead_sd)


def static_reorder_point(
    daily_mean: float,
    daily_sd: float,
    lead_mean: float,
    csl: float,
) -> float:
    """Textbook reorder point that ignores lead-time variability."""
    z = z_for_service_level(csl)
    return daily_mean * lead_mean + z * daily_sd * math.sqrt(lead_mean)


def fill_rate_closed_form(
    daily_mean: float,
    daily_sd: float,
    lead_mean: float,
    lead_sd: float,
    csl: float,
    order_qty: float,
) -> float:
    """Fill rate for lost sales under normal lead-time demand: 1 - sigma * G(z) / Q.

    G(z) is the standard normal loss function, phi(z) - z * (1 - Phi(z)), and sigma is
    the SD of demand over lead time. Assumes each replenishment cycle consumes one order quantity.
    """
    z = z_for_service_level(csl)
    sigma = lead_time_demand_sd(daily_mean, daily_sd, lead_mean, lead_sd)
    loss = _STD_NORMAL.pdf(z) - z * (1.0 - _STD_NORMAL.cdf(z))
    return 1.0 - sigma * loss / order_qty


def exact_csl_normal_demand(
    reorder_point: float,
    daily_mean: float,
    daily_sd: float,
    lead_days: Sequence[int],
    lead_probs: Sequence[float],
) -> float:
    """Exact cycle service level for normal daily demand (no spikes) and a discrete lead time.

    For a lead time of L days, demand over those days is exactly normal with mean d*L and
    SD sigma*sqrt(L). The answer is the lead-time-weighted average of
    Phi((ROP - d*L) / (sigma*sqrt(L))).
    """
    if daily_sd <= 0:
        raise ValueError("daily_sd must be positive for this calculation")
    days, probs = _check_lead_time(lead_days, lead_probs)
    z_scores = (reorder_point - daily_mean * days) / (daily_sd * np.sqrt(days))
    cdf_values = np.vectorize(_STD_NORMAL.cdf)(z_scores)
    return float(np.sum(probs * cdf_values))


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationResult:
    cycle_service_level: float   # share of cycles with no stockout
    fill_rate: float             # average share of one order quantity met from stock
    mean_shortage_units: float   # average units of lost demand per cycle
    cycles: int


def sample_daily_demand(
    rng: np.random.Generator,
    shape,
    base_mean: float,
    base_sd: float,
    spike_prob: float = 0.0,
    spike_size: float = 0.0,
) -> np.ndarray:
    """Draw daily demand: a normal draw floored at zero, plus spike_size on spike days."""
    demand = np.maximum(rng.normal(base_mean, base_sd, size=shape), 0.0)
    if spike_prob > 0.0 and spike_size != 0.0:
        demand = demand + spike_size * (rng.random(size=shape) < spike_prob)
    return demand


def simulate_lead_time_demand(
    base_mean: float,
    base_sd: float,
    lead_days: Sequence[int],
    lead_probs: Sequence[float],
    cycles: int = 100_000,
    seed: int = 0,
    spike_prob: float = 0.0,
    spike_size: float = 0.0,
) -> np.ndarray:
    """Total demand over one lead time, one simulated value per replenishment cycle.

    Each cycle draws a lead time from lead_days and lead_probs, then sums that many
    days of simulated demand.
    """
    days, probs = _check_lead_time(lead_days, lead_probs)
    _check_demand(base_sd, spike_prob, spike_size)
    if cycles < 1:
        raise ValueError("cycles must be at least 1")

    rng = np.random.default_rng(seed)
    lengths = rng.choice(days, size=cycles, p=probs)
    max_len = int(days.max())
    daily = sample_daily_demand(rng, (cycles, max_len), base_mean, base_sd, spike_prob, spike_size)
    in_lead_time = np.arange(max_len) < lengths[:, None]
    return (daily * in_lead_time).sum(axis=1)


def simulated_reorder_point(
    base_mean: float,
    base_sd: float,
    lead_days: Sequence[int],
    lead_probs: Sequence[float],
    csl: float,
    cycles: int = 100_000,
    seed: int = 0,
    spike_prob: float = 0.0,
    spike_size: float = 0.0,
) -> float:
    """Smallest reorder point whose simulated cycle service level reaches csl.

    This is the csl quantile of simulated lead-time demand, so it reflects the full
    demand and lead-time distributions, spikes included, with no normal approximation.
    """
    _check_csl(csl)
    demand = simulate_lead_time_demand(
        base_mean, base_sd, lead_days, lead_probs,
        cycles=cycles, seed=seed, spike_prob=spike_prob, spike_size=spike_size,
    )
    return float(np.quantile(demand, csl, method="inverted_cdf"))


def simulate_cycles(
    base_mean: float,
    base_sd: float,
    lead_days: Sequence[int],
    lead_probs: Sequence[float],
    reorder_point: float,
    order_qty: float,
    cycles: int = 100_000,
    seed: int = 0,
    spike_prob: float = 0.0,
    spike_size: float = 0.0,
) -> SimulationResult:
    """Cycle service level and fill rate for a given reorder point.

    A cycle is a stockout if lead-time demand exceeds the reorder point. Fill rate
    assumes each cycle consumes one order quantity and that unmet demand is lost.
    """
    if order_qty <= 0:
        raise ValueError("order_qty must be positive")
    demand = simulate_lead_time_demand(
        base_mean, base_sd, lead_days, lead_probs,
        cycles=cycles, seed=seed, spike_prob=spike_prob, spike_size=spike_size,
    )
    shortage = np.maximum(demand - reorder_point, 0.0)
    return SimulationResult(
        cycle_service_level=float(np.mean(demand <= reorder_point)),
        fill_rate=float(1.0 - shortage.mean() / order_qty),
        mean_shortage_units=float(shortage.mean()),
        cycles=cycles,
    )


# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------

def _check_csl(csl: float) -> None:
    if not 0.0 < csl < 1.0:
        raise ValueError(f"cycle service level must be strictly between 0 and 1, got {csl}")


def _check_demand(base_sd: float, spike_prob: float, spike_size: float) -> None:
    if base_sd < 0:
        raise ValueError("base_sd cannot be negative")
    if not 0.0 <= spike_prob <= 1.0:
        raise ValueError("spike_prob must be between 0 and 1")
    if spike_size < 0:
        raise ValueError("spike_size cannot be negative")


def _check_lead_time(lead_days, lead_probs):
    days = np.asarray(lead_days, dtype=float)
    probs = np.asarray(lead_probs, dtype=float)
    if days.ndim != 1 or days.size == 0 or days.shape != probs.shape:
        raise ValueError("lead_days and lead_probs must be non-empty 1-D sequences of equal length")
    if np.any(days < 1) or np.any(days != np.round(days)):
        raise ValueError("lead times must be whole numbers of days, at least 1")
    if np.any(probs < 0) or not np.isclose(probs.sum(), 1.0):
        raise ValueError("lead-time probabilities must be non-negative and sum to 1")
    return days.astype(int), probs / probs.sum()