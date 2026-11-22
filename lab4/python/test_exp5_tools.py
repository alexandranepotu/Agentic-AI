import time

import pytest

import exp5_tools as ex5
from exp5_tools import Arg, Plan, Step, execute


@pytest.fixture(autouse=True)
def fast_tools(monkeypatch):
    monkeypatch.setattr(ex5, "TOOL_LATENCY", 0.3)


def step(sid, tool, **args):
    return Step(id=sid, why="test", tool=tool, args=[Arg(name=k, value=str(v)) for k, v in args.items()])


def test_a_reference_is_replaced_by_the_earlier_result():
    plan = Plan(steps=[step("s1", "nearest_airport", town="Vaslui"),
                       step("s2", "flight_price", origin="@s1", destination="Rome", date="12 May")])
    results = execute(plan, parallel=False)
    assert results["s1"] == "Iasi"
    assert '"price_eur": 142' in results["s2"]


def test_parallel_runs_independent_steps_at_the_same_time():
    plan = Plan(steps=[step(f"s{i}", "weather", city=c) for i, c in enumerate(["Rome", "Barcelona", "Lisbon"], 1)])
    t0 = time.perf_counter()
    execute(plan, parallel=False)
    sequential = time.perf_counter() - t0
    t0 = time.perf_counter()
    results = execute(plan, parallel=True)
    parallel = time.perf_counter() - t0
    assert sequential >= 0.85 and parallel < 0.6, (sequential, parallel)
    assert results["s3"] == "21 C, windy"


def test_a_dependent_step_waits_for_its_input_even_in_parallel():
    plan = Plan(steps=[step("s2", "flight_price", origin="@s1", destination="Barcelona", date="12 May"),
                       step("s1", "nearest_airport", town="Botosani")])
    results = execute(plan, parallel=True)
    assert '"price_eur": 156' in results["s2"]


def test_a_reference_to_a_missing_step_does_not_hang():
    plan = Plan(steps=[step("s1", "weather", city="@s9")])
    results = execute(plan, parallel=True)
    assert "No weather data" in results["s1"]


def test_bad_arguments_become_an_error_result():
    plan = Plan(steps=[step("s1", "hotel_price", city="Rome", nights="three")])
    assert execute(plan, parallel=False)["s1"].startswith("ERROR")