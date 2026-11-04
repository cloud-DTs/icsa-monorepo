import pytest

from simulator.SimulationLoop import coerce_value, generate_value


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ("true", True), ("false", False)])
def test_boolean_api_values_keep_their_type(value, expected):
    assert coerce_value(value, "BOOLEAN") is expected


@pytest.mark.parametrize("value", [1, 0, "yes", [], None])
def test_boolean_api_values_reject_ambiguous_inputs(value):
    with pytest.raises(ValueError):
        coerce_value(value, "BOOLEAN")


@pytest.mark.parametrize("data_type", ["INTEGER", "LONG"])
def test_integer_api_values_keep_large_integer_precision(data_type):
    assert coerce_value("9007199254740993", data_type) == 9007199254740993


@pytest.mark.parametrize("value", [True, "nan", "inf", "1.5"])
@pytest.mark.parametrize("data_type", ["INTEGER", "LONG"])
def test_integer_api_values_reject_inexact_or_nonfinite_values(value, data_type):
    with pytest.raises(ValueError):
        coerce_value(value, data_type)


def test_long_uniform_generation_does_not_use_a_float_range():
    value = 9007199254740993
    assert generate_value({"mode": "uniform", "min": str(value), "max": str(value)}, "LONG") == value


@pytest.mark.parametrize("value", [False, True])
def test_fixed_boolean_generation(value):
    assert generate_value({"mode": "fixed", "value": value}, "BOOLEAN") is value


def test_vector_string_generation_preserves_strings():
    assert generate_value({"mode": "vector_custom", "vector": "ready,stopped"}, "VECTOR_STRING") == ["ready", "stopped"]


@pytest.mark.parametrize("config,data_type", [
    ({"mode": "vector_uniform", "vec_min": "1,2", "vec_max": "3"}, "VECTOR_DOUBLE"),
    ({"mode": "vector_custom", "vector": "1,nan"}, "VECTOR_DOUBLE"),
    ({"mode": "uniform", "min": "nan", "max": "2"}, "DOUBLE"),
    ({"mode": "uniform", "min": "5", "max": "2"}, "INTEGER"),
    ({"mode": "normal", "stddev": "-1"}, "DOUBLE"),
    ({"mode": "unknown"}, "STRING"),
    ({"mode": "vector_uniform", "vec_min": "a", "vec_max": "b"}, "VECTOR_STRING"),
])
def test_invalid_generation_settings_do_not_become_fake_readings(config, data_type):
    with pytest.raises(ValueError):
        generate_value(config, data_type)
