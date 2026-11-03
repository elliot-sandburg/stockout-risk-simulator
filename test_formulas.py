"""Formula tests for replenishment.py.

Where the closed-form math is exact, the simulator must match it. Where the math is an
approximation, the simulator must match the exact expression, and the approximation error
is bounded explicitly. Simulation tolerances are at least about nine standard errors at
400,000 cycles, so a fixed seed passes reliably while a real modeling error still fails.

Run from the project folder with: pytest -q
"""

import math

import numpy as np
import pytest

from replenishment import (
    closed_form_reorder_point,
    daily_demand_moments,
    exact_csl_normal_demand,
    fill_rate_closed_form,
    sample_daily_demand,
    simulate_cycles,
    simulated_reorder_point,
    static_reorder_point,
    z_for_service_level,
)

BASE_MEAN = 50.0   # units per day; SD is 20% of the mean, so flooring at zero is negligible
BASE_SD = 10.0
ORDER_QTY = 500.0
CYCLES = 400_000
SEED = 7
CSL_TOL = 0.005    # at least about nine standard errors at 400,000 cycles

FIXED_LEAD = 10

# Discrete lead time, uniform over 18 to 22 days: mean 20 days, variance 2 days squared.
VARIABLE_DAYS = [18, 19, 20, 21, 22]
VARIABLE_PROBS = [0.2, 0.2, 0.2, 0.2, 0.2]
VARIABLE_MEAN = 20.0
VARIABLE_SD = math.sqrt(2.0)


def test_z_matches_standard_normal_quantiles():
    assert z_for_service_level(0.5) == pytest.approx(0.0, abs=1e-12)
    assert z_for_service_level(0.85) == pytest.approx(1.0364, abs=1e-4)
    assert z_for_service_level(0.95) == pytest.approx(1.6449, abs=1e-4)


def test_fixed_lead_time_closed_form_reduces_to_textbook_formula():
    closed = closed_form_reorder_point(BASE_MEAN, BASE_SD, FIXED_LEAD, 0.0, 0.95)
    textbook = static_reorder_point(BASE_MEAN, BASE_SD, FIXED_LEAD, 0.95)
    assert closed == pytest.approx(textbook)


@pytest.mark.parametrize("csl", [0.85, 0.95, 0.99])
def test_fixed_lead_time_csl_matches_formula(csl):
    rop = closed_form_reorder_point(BASE_MEAN, BASE_SD, FIXED_LEAD, 0.0, csl)
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, [FIXED_LEAD], [1.0], rop, ORDER_QTY, cycles=CYCLES, seed=SEED
    )
    assert abs(result.cycle_service_level - csl) < CSL_TOL


def test_fixed_lead_time_fill_rate_matches_loss_function():
    csl = 0.95
    rop = closed_form_reorder_point(BASE_MEAN, BASE_SD, FIXED_LEAD, 0.0, csl)
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, [FIXED_LEAD], [1.0], rop, ORDER_QTY, cycles=CYCLES, seed=SEED
    )
    expected = fill_rate_closed_form(BASE_MEAN, BASE_SD, FIXED_LEAD, 0.0, csl, ORDER_QTY)
    assert abs(result.fill_rate - expected) < 0.0005


@pytest.mark.parametrize("csl", [0.85, 0.95])
def test_variable_lead_time_csl_matches_exact_expression(csl):
    rop = closed_form_reorder_point(BASE_MEAN, BASE_SD, VARIABLE_MEAN, VARIABLE_SD, csl)
    exact = exact_csl_normal_demand(rop, BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS)
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS, rop, ORDER_QTY,
        cycles=CYCLES, seed=SEED,
    )
    assert abs(result.cycle_service_level - exact) < CSL_TOL


@pytest.mark.parametrize("csl", [0.85, 0.90, 0.95, 0.98])
def test_closed_form_error_is_bounded_under_variable_lead_time(csl):
    # The normal approximation is not exact when lead time varies. Measured in v1 for
    # this spread: about -2.0 points at an 85% target and +0.2 points at a 95% target.
    rop = closed_form_reorder_point(BASE_MEAN, BASE_SD, VARIABLE_MEAN, VARIABLE_SD, csl)
    exact = exact_csl_normal_demand(rop, BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS)
    assert abs(exact - csl) < 0.025


@pytest.mark.parametrize("csl", [0.85, 0.95])
def test_simulated_reorder_point_hits_target_under_variable_lead_time(csl):
    rop = simulated_reorder_point(
        BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS, csl, cycles=CYCLES, seed=SEED
    )
    exact = exact_csl_normal_demand(rop, BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS)
    assert abs(exact - csl) < CSL_TOL


def test_static_formula_under_protects_when_lead_time_varies():
    rop = static_reorder_point(BASE_MEAN, BASE_SD, VARIABLE_MEAN, 0.95)
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, VARIABLE_DAYS, VARIABLE_PROBS, rop, ORDER_QTY,
        cycles=CYCLES, seed=SEED,
    )
    assert result.cycle_service_level < 0.85


def test_spike_moments_match_formulas():
    rng = np.random.default_rng(SEED)
    spike_prob, spike_size = 0.02, 200.0
    draws = sample_daily_demand(rng, 2_000_000, BASE_MEAN, BASE_SD, spike_prob, spike_size)
    mean, sd = daily_demand_moments(BASE_MEAN, BASE_SD, spike_prob, spike_size)
    assert draws.mean() == pytest.approx(mean, abs=0.1)
    assert draws.std() == pytest.approx(sd, abs=0.3)


def test_spikes_open_a_gap_the_normal_formula_misses():
    csl = 0.95
    spike_prob, spike_size = 0.02, 200.0
    mean, sd = daily_demand_moments(BASE_MEAN, BASE_SD, spike_prob, spike_size)
    rop = closed_form_reorder_point(mean, sd, FIXED_LEAD, 0.0, csl)
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, [FIXED_LEAD], [1.0], rop, ORDER_QTY,
        cycles=CYCLES, seed=SEED, spike_prob=spike_prob, spike_size=spike_size,
    )
    assert result.cycle_service_level < csl - 0.03


def test_simulated_reorder_point_closes_the_spike_gap():
    # Set the reorder point with one seed and check it with another, so the check is not
    # made on the same draws that produced the reorder point.
    csl = 0.95
    spike_prob, spike_size = 0.02, 200.0
    rop = simulated_reorder_point(
        BASE_MEAN, BASE_SD, [FIXED_LEAD], [1.0], csl,
        cycles=CYCLES, seed=SEED, spike_prob=spike_prob, spike_size=spike_size,
    )
    result = simulate_cycles(
        BASE_MEAN, BASE_SD, [FIXED_LEAD], [1.0], rop, ORDER_QTY,
        cycles=CYCLES, seed=SEED + 1, spike_prob=spike_prob, spike_size=spike_size,
    )
    assert abs(result.cycle_service_level - csl) < CSL_TOL


def test_same_seed_gives_identical_results():
    args = dict(
        base_mean=BASE_MEAN, base_sd=BASE_SD, lead_days=[10], lead_probs=[1.0],
        reorder_point=600.0, order_qty=ORDER_QTY, cycles=50_000, seed=3,
    )
    assert simulate_cycles(**args) == simulate_cycles(**args)


def test_bad_inputs_raise_value_error():
    with pytest.raises(ValueError):
        z_for_service_level(1.0)
    with pytest.raises(ValueError):
        simulate_cycles(BASE_MEAN, BASE_SD, [0], [1.0], 500.0, ORDER_QTY, cycles=10)
    with pytest.raises(ValueError):
        simulate_cycles(BASE_MEAN, BASE_SD, [10, 11], [0.5, 0.6], 500.0, ORDER_QTY, cycles=10)
    with pytest.raises(ValueError):
        simulate_cycles(BASE_MEAN, BASE_SD, [10.5], [1.0], 500.0, ORDER_QTY, cycles=10)
    with pytest.raises(ValueError):
        simulated_reorder_point(BASE_MEAN, BASE_SD, [10], [1.0], 1.2, cycles=10)