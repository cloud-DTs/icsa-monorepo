"""Pure EV charging decision logic owned by the Battery twin.

No AWS calls, no I/O - just inputs -> outputs, so it can be reasoned about and
unit-tested on its own. The surrounding Strategy Lambda collects the inputs
(Collector + hot-reader pulls) and publishes the result through Feedback.

This is an ENERGY BALANCE, not a weighted formula: it splits the power that is
actually available between the EV and the battery, with the EV taking priority.

The car always comes first, from every source available; the battery gets only
what is left over. The two branches differ only in WHERE the energy comes from.

  green >= 75%  (renewables cheap - buy from the grid)
      available = gridMax * priceFactor + PV
      EV        = min(chargerMax, available)
      battery   = what the car could not take

  green < 75%   (grid brown/expensive - do not buy from it)
      available = batteryMaxDischarge + PV
      EV        = min(chargerMax, available)
      battery   = only the PV the car could not take
                  (never the battery's own discharge - it cannot charge itself)

The price only affects the green branch, because that is the only one that buys
energy from the grid. In the brown branch the energy comes from the battery and
from PV, both already paid for, so the price is irrelevant there.

The battery's own charge level is deliberately NOT part of the decision: it is
produced by the simulator, and a stray low value would silently turn a scenario
into 0 kW. Availability is assumed. It is still logged by the Strategy Lambda.
"""

# Share of renewables in the grid (%) at or above which grid energy is treated as
# cheap and green, so the grid is used to charge. Below it the grid counts as
# brown and is left untouched.
GREEN_ENERGY_THRESHOLD = 75.0

# Reference grid price, EUR/kWh. Roughly the Austrian household rate, and the
# point where the price has NO effect: at this value the factor is exactly 1.0,
# so the demo scenarios come out unchanged.
PRICE_BASELINE = 0.25
# Floor for the factor, so even an absurd price still allows some charging
# instead of dropping the car to zero.
MIN_PRICE_FACTOR = 0.3


def price_factor(electricity_price):
    """How much of the grid's capacity is worth buying at this price.

    1.0 at or below the baseline - cheaper energy does not let us exceed the
    hardware limits, so there is nothing to gain above 1.0. Above the baseline it
    falls off inversely: twice the price, half the draw.

    A missing or non-positive price (0.0 is what _as_float returns when the pull
    finds nothing) is treated as "no information" and leaves the split untouched,
    rather than silently behaving like free electricity.
    """
    if electricity_price is None or electricity_price <= 0.0:
        return 1.0
    return max(MIN_PRICE_FACTOR, min(1.0, PRICE_BASELINE / electricity_price))


def calculate_power_split(
    green_energy_percentage,
    pv_production,
    grid_max_power,
    charger_max_power,
    battery_max_charging_power,
    battery_max_discharging_power,
    is_plugged,
    electricity_price=None,
    battery_charge_percent=None,
):
    """Return (actChargeEV, actBatteryCharge) in kW.

    actChargeEV      - what the Charger applies to the EV
    actBatteryCharge - what the battery charges ITSELF with

    battery_charge_percent is the current state of charge. When given, it gates
    both ends: an empty battery stops feeding the car, a full one stops
    accepting. Passing None disables both gates, which is what the pure power
    split did before state of charge was tracked.
    """
    if not is_plugged:
        return 0.0, 0.0

    pv_production = max(0.0, pv_production)
    grid_max_power = max(0.0, grid_max_power)

    # An empty battery cannot feed the car; a full one cannot take more in.
    discharge_available = battery_max_discharging_power
    charge_headroom = battery_max_charging_power
    if battery_charge_percent is not None:
        if battery_charge_percent <= BATTERY_RESERVE_PERCENT:
            discharge_available = 0.0
        if battery_charge_percent >= 100.0:
            charge_headroom = 0.0

    if green_energy_percentage >= GREEN_ENERGY_THRESHOLD:
        # Green: draw from the grid, but only as much of it as the price
        # justifies. The car is served FIRST from everything available - the
        # affordable grid share AND all PV - and only what it cannot take is
        # left for the battery.
        #
        # That is what keeps the car whole when the price rises: the grid share
        # shrinks, PV covers the gap, and the battery absorbs the shortfall.
        usable_grid = grid_max_power * price_factor(electricity_price)
        available = usable_grid + pv_production
        act_charge_ev = min(charger_max_power, available)
        battery_charge_power = min(
            charge_headroom, max(0.0, available - act_charge_ev)
        )
    else:
        # Brown and expensive: do not touch the grid. The CAR has priority and is
        # fed from both sources at once - the battery discharges into it and all
        # PV goes the same way.
        act_charge_ev = min(charger_max_power, discharge_available + pv_production)
        # Only the PV the car could not absorb is left for the battery.
        pv_taken_by_car = max(0.0, act_charge_ev - discharge_available)
        pv_left = max(0.0, pv_production - pv_taken_by_car)
        battery_charge_power = min(charge_headroom, pv_left)

    return _clamp(act_charge_ev, charger_max_power), _clamp(
        battery_charge_power, battery_max_charging_power
    )


# --------------------------------------------------------------------------- #
# State of charge
# --------------------------------------------------------------------------- #
# Below this level the battery keeps what is left for itself and stops feeding
# the car. Above 100% it obviously stops accepting.
BATTERY_RESERVE_PERCENT = 20.0

# Simulated seconds per real second. The scenarios span 05:00 to 21:00, so at
# real time the demo would take sixteen hours; at x120 it fits in ~8.5 minutes
# while the INTERVALS stay proportional - the four-hour gap between 08:00 and
# 12:00 really does take four times longer on screen than a one-hour gap.
TIME_ACCELERATION = 120.0

# Never integrate over more than this many real seconds in one step. Without it,
# a Lambda that has not run for an hour would apply a single enormous jump.
MAX_STEP_SECONDS = 300.0


def net_battery_power(
    green_energy_percentage,
    act_charge_ev,
    battery_charge_power,
    battery_max_discharging_power,
    battery_charge_percent=None,
):
    """Signed power seen by the battery, in kW. Positive charges, negative drains.

    In the green branch the car runs off the grid, so the battery only ever
    charges. In the brown branch the battery is what feeds the car, so it drains
    by whatever share of the car's draw it had to cover.

    battery_charge_percent must be gated the SAME way as in
    calculate_power_split: a battery at or below the reserve contributed nothing,
    so it must not be counted as discharging. Without this the two would disagree
    - the split would correctly refuse to discharge while this reported a drain.
    """
    if green_energy_percentage >= GREEN_ENERGY_THRESHOLD:
        return battery_charge_power

    discharge_available = battery_max_discharging_power
    if (battery_charge_percent is not None
            and battery_charge_percent <= BATTERY_RESERVE_PERCENT):
        discharge_available = 0.0

    discharged = min(discharge_available, act_charge_ev)
    return battery_charge_power - discharged


def next_state_of_charge(
    current_percent,
    net_power_kw,
    total_capacity_kwh,
    elapsed_seconds,
):
    """Integrate the net power over the elapsed time into a new SoC percentage.

    elapsed_seconds is REAL time; it is clamped and then scaled by
    TIME_ACCELERATION. Returns the new percentage, clamped to [0, 100].
    """
    if total_capacity_kwh <= 0.0 or elapsed_seconds is None or elapsed_seconds <= 0.0:
        return _percent(current_percent)

    simulated_hours = min(elapsed_seconds, MAX_STEP_SECONDS) * TIME_ACCELERATION / 3600.0
    delta_percent = net_power_kw * simulated_hours / total_capacity_kwh * 100.0
    return _percent(current_percent + delta_percent)


def grid_power_drawn(
    green_energy_percentage,
    pv_production,
    act_charge_ev,
    battery_charge_power,
):
    """How much of the delivered power is actually bought from the grid, in kW.

    Brown grid: nothing is bought at all - the car runs off the battery and PV.

    Green grid: everything delivered (car + battery) minus whatever PV covered.
    PV is used first because it is free, so the more sun there is the less has to
    come from the grid - at PV 10 kW the draw falls from 25 to 22 even though the
    car still gets its full 22 kW.
    """
    if green_energy_percentage < GREEN_ENERGY_THRESHOLD:
        return 0.0

    delivered = act_charge_ev + max(0.0, battery_charge_power)
    covered_by_pv = min(max(0.0, pv_production), delivered)
    return _round2(max(0.0, delivered - covered_by_pv))


def signed_power(value, max_charge, max_discharge):
    """Clamp a signed battery power to [-max_discharge, +max_charge].

    Separate from _clamp, which floors at zero: that one is for the car's
    charging power, which can never be negative, while this one must keep the
    sign that tells charging from discharging.
    """
    value = max(-abs(max_discharge), min(value, abs(max_charge)))
    return _round2(value)


def _round2(value):
    """Truncate toward zero at two decimals, keeping the sign."""
    sign = -1.0 if value < 0 else 1.0
    return sign * (int(abs(value) * 100.0) / 100.0)


def _percent(value):
    """Clamp a state of charge to [0, 100] at two decimals."""
    value = max(0.0, min(100.0, value))
    return int(value * 100.0) / 100.0


def _clamp(value, upper):
    """Keep a power value inside [0, upper] and at two decimals.

    Truncates rather than rounds: round() can push a result just above the limit
    it was clamped to, and a power value must never exceed its hardware cap.
    """
    value = max(0.0, min(value, max(0.0, upper)))
    return int(value * 100.0) / 100.0
