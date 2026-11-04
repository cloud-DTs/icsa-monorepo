"""Pure dispatch policy for the MEPSO demonstration scenarios.

Power is signed from the distribution-grid perspective: positive values mean consumption/import/charging and negative values mean export/discharging or a demand reduction.
"""


def calculate_dispatch(state):
    requested = max(0.0, _number(state.get("requestedPower")))
    direction = str(state.get("serviceDirection") or "NONE").strip().upper()
    ts1_limit = _positive_limit(state.get("ts1ExchangeLimit"))
    ts2_limit = _positive_limit(state.get("ts2ExchangeLimit"))

    if requested and direction == "UPWARD":
        return _upward_dispatch(requested, ts1_limit, ts2_limit)
    if requested and direction == "DOWNWARD":
        return _downward_dispatch(
            requested,
            ts1_limit,
            ts2_limit,
            _number(state.get("ec1PVPower")),
            _number(state.get("ec2PVPower")),
        )
    if str(state.get("ts1VoltageStatus") or "").strip().upper() == "HIGH_VOLTAGE":
        absorption = min(6.0, ts1_limit)
        battery = min(4.0, absorption)
        return _result(
            battery,
            absorption - battery,
            0.0,
            0.0,
            0.0,
            "NONE",
            absorption,
            0.0,
            "LOCAL_DSO_SUPPORT",
        )
    return _result(0.0, 0.0, 0.0, 0.0, 0.0, "NONE", 0.0, 0.0, "MONITORING")


def _upward_dispatch(requested, ts1_limit, ts2_limit):
    # The scenario's state-aware 8/4 split is the preferred allocation. For a smaller request it scales proportionally; for a larger one the remainder is added without violating either 10 MW substation limit.
    ts1 = min(ts1_limit, requested * 2.0 / 3.0)
    ts2 = min(ts2_limit, requested - ts1)
    ts1 += min(ts1_limit - ts1, requested - ts1 - ts2)
    delivered = ts1 + ts2
    ec1_dsr = min(3.0, ts1)
    ec2_dsr = min(1.0, ts2)
    return _result(
        -(ts1 - ec1_dsr),
        -ec1_dsr,
        -(ts2 - ec2_dsr),
        -ec2_dsr,
        delivered,
        "UPWARD",
        -ts1,
        -ts2,
        "UPWARD_SERVICE",
    )


def _downward_dispatch(requested, ts1_limit, ts2_limit, ec1_pv, ec2_pv):
    ts1 = min(ts1_limit, requested / 2.0)
    ts2 = min(ts2_limit, requested - ts1)
    ts1 += min(ts1_limit - ts1, requested - ts1 - ts2)
    delivered = ts1 + ts2
    # Local PV is consumed before grid import, so battery charging is PV plus
    # the requested positive exchange at the substation.
    return _result(
        min(10.0, max(0.0, ec1_pv) + ts1),
        0.0,
        min(10.0, max(0.0, ec2_pv) + ts2),
        0.0,
        delivered,
        "DOWNWARD",
        ts1,
        ts2,
        "DOWNWARD_SERVICE",
    )


def _result(
    ec1_battery,
    ec1_dsr,
    ec2_battery,
    ec2_dsr,
    delivered,
    direction,
    ts1_exchange,
    ts2_exchange,
    mode,
):
    return {
        "ec1BatteryPower": round(ec1_battery, 6),
        "ec1DSRPower": round(ec1_dsr, 6),
        "ec2BatteryPower": round(ec2_battery, 6),
        "ec2DSRPower": round(ec2_dsr, 6),
        "deliveredPower": round(delivered, 6),
        "deliveredServiceDirection": direction,
        "ts1ExchangePower": round(ts1_exchange, 6),
        "ts2ExchangePower": round(ts2_exchange, 6),
        "decisionMode": mode,
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _positive_limit(value):
    parsed = _number(value)
    return parsed if parsed > 0 else 10.0
