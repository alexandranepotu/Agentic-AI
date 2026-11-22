"""Lab 4 - Experiment 5: three ways to use the same tools (STARTER).  Tests: pytest test_exp5_tools.py -v

    python exp5_tools.py                  # all 4 questions x 3 modes, one run each
    python exp5_tools.py loop 3           # one mode on one question
    python exp5_tools.py --runs 3         # repeat every cell 3 times
    python exp5_tools.py --verbose        # print every tool call (loop) and every plan (plan, parallel)
    python exp5_tools.py --sum            # the loop also gets a sum_eur tool
"""
import datetime
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from google.genai import errors

from agent_core import run_agent
from llm import ask

TOOL_LATENCY = 1.0  # seconds: pretend every tool is a slow web API
TOOL_WAIT = [0.0]   # total seconds spent waiting on tools (one at a time)

FLIGHTS = {("Iasi", "Rome"): 142, ("Iasi", "Barcelona"): 118, ("Iasi", "Bucharest"): 39,
           ("Bucharest", "Lisbon"): 167, ("Suceava", "Rome"): 131, ("Suceava", "Barcelona"): 156}
HOTEL_PER_NIGHT = {"Rome": 96, "Barcelona": 121, "Lisbon": 74}
WEATHER = {"Rome": "24 C, sunny", "Barcelona": "22 C, cloudy", "Lisbon": "21 C, windy"}
NEAREST_AIRPORT = {"Vaslui": "Iasi", "Botosani": "Suceava", "Iasi": "Iasi"}


def _city(name: str) -> str:
    """'Rome (FCO)', ' rome ' and 'ROME' all mean Rome: real tools normalise their input."""
    return re.sub(r"\s*\(.*?\)", "", name).strip().title()


def _wait():
    time.sleep(TOOL_LATENCY)
    TOOL_WAIT[0] += TOOL_LATENCY


# --- Tools (deterministic, slow on purpose) ---------------------------------
def nearest_airport(town: str) -> str:
    """Only for Romanian towns WITHOUT an airport (e.g. Vaslui): returns just the city of the nearest airport.
    Never use it for a city that has an airport, such as Iasi, Rome or Barcelona.

    Args:
        town: Town name, e.g. 'Vaslui'.
    """
    _wait()
    return NEAREST_AIRPORT.get(_city(town), f"Unknown town {town}.")


def flight_price(origin: str, destination: str, date: str) -> str:
    """Cheapest one-way economy ticket for one adult, in EUR.

    Args:
        origin: Departure city, e.g. 'Iasi'.
        destination: Arrival city, e.g. 'Rome'.
        date: Travel date, e.g. '12 May'.
    """
    _wait()
    price = FLIGHTS.get((_city(origin), _city(destination)))
    if price is None:
        if _city(destination) == "Lisbon":
            return "No direct flight Iasi-Lisbon. Connect via Bucharest: price Iasi->Bucharest and Bucharest->Lisbon."
        return f"No flights found {origin}->{destination}."
    return json.dumps({"route": f"{origin}->{destination}", "date": date, "price_eur": price})


def hotel_price(city: str, nights: int) -> str:
    """Total price in EUR of a double room in a central 3-star hotel.

    Args:
        city: City name, e.g. 'Rome'.
        nights: Number of nights.
    """
    _wait()
    per_night = HOTEL_PER_NIGHT.get(_city(city))
    if per_night is None:
        return f"No hotels found in {city}."
    return json.dumps({"city": city, "nights": int(nights), "total_eur": per_night * int(nights)})


def weather(city: str) -> str:
    """Current weather in a city.

    Args:
        city: City name, e.g. 'Lisbon'.
    """
    _wait()
    return WEATHER.get(_city(city), f"No weather data for {city}.")


def sum_eur(amounts: list[float]) -> str:
    """Add up a list of EUR amounts exactly. Use it for every total, never add numbers yourself.

    Args:
        amounts: The amounts in EUR to add up, e.g. [142, 288].
    """
    total = sum((Decimal(str(a)) for a in amounts), Decimal(0))  # Decimal: no floating-point surprises
    return json.dumps({"total_eur": float(total)})


TOOLS = {f.__name__: f for f in (nearest_airport, flight_price, hotel_price, weather)}

QUESTIONS = {
    1: ("From Iasi on 12 May: is Rome or Barcelona cheaper for one person, flight plus 3 hotel nights?", "430"),
    2: ("What is the weather right now in Rome, Barcelona and Lisbon?", "windy"),
    3: ("What does it cost one person to get from Iasi to Lisbon on 12 May, plus 3 hotel nights?", "428"),
    4: ("I live in Vaslui. On 12 May, is it cheaper to fly from my nearest airport to Rome or to Barcelona?", "118"),
}
SYSTEM = ("You are a travel assistant. Use the tools for every price and every forecast; never guess numbers. "
          # checkpoint 4: without today's date the model uses the year it remembers from training
          f"Today is {datetime.date.today():%d %B %Y}, so a date without a year means its next occurrence.")
VERBOSE = "--verbose" in sys.argv


# --- Mode 1: the loop you built in Lab 3 -------------------------------------
def mode_loop(question: str) -> tuple[str, int, int, float]:
    tools, system = list(TOOLS.values()), SYSTEM
    if "--sum" in sys.argv:  # give the loop a calculator
        tools, system = tools + [sum_eur], SYSTEM + " Never add numbers yourself: use sum_eur."
    TOOL_WAIT[0] = 0.0
    res = run_agent(question, tools=tools, system_instruction=system, max_steps=8, verbose=VERBOSE)
    return res.answer, res.steps, res.total_prompt_tokens, TOOL_WAIT[0]  # the loop runs tools one by one


# --- Modes 2 and 3: plan once, run the tools in code, answer once -------------
class Arg(BaseModel):
    name: str
    value: str = Field(description="A literal value, or @s1 to use the result of step s1 (only when that result is a single value)")


class Step(BaseModel):
    id: str = Field(description="s1, s2, ...")
    why: str
    tool: Literal["nearest_airport", "flight_price", "hotel_price", "weather"]
    args: list[Arg]


class Plan(BaseModel):
    steps: list[Step]


PLANNER = (
    SYSTEM + " Write the COMPLETE list of tool calls needed to answer, before any tool runs. "
    "Tools: nearest_airport(town) (only for towns without an airport), flight_price(origin, destination, date), hotel_price(city, nights), weather(city). "
    "Give each step an id s1, s2, ... A later step may use an earlier step's result by writing @s1 as an argument value."
)
SOLVER = "Answer the question using ONLY the evidence below. If the evidence is not enough, say exactly what is missing."

REF = re.compile(r"@s\d+")


def run_step(step: Step, results: dict[str, str]) -> str:
    args = {a.name: REF.sub(lambda m: results.get(m.group(0)[1:], m.group(0)), a.value) for a in step.args}
    try:
        return TOOLS[step.tool](**args)
    except Exception as e:  # bad arguments must become a result, never a crash
        return f"ERROR: {step.tool} failed: {type(e).__name__}: {e}"


def execute(plan: Plan, parallel: bool) -> dict[str, str]:
    """Run the plan; with parallel=True, every step whose inputs are ready runs at the same time."""
    results: dict[str, str] = {}
    pending = list(plan.steps)
    while pending:
        # a step is READY when every @s reference in its args already has a result
        ready = [s for s in pending
                 if all(ref[1:] in results for a in s.args for ref in REF.findall(a.value))]
        if not ready:  # a reference to a step that does not exist: run the first pending step as-is
            ready = [pending[0]]
        if parallel:
            with ThreadPoolExecutor() as pool:
                outputs = list(pool.map(lambda s: run_step(s, results), ready))
        else:
            outputs = [run_step(s, results) for s in ready]
        for step, output in zip(ready, outputs):
            results[step.id] = output
        done = {s.id for s in ready}
        pending = [s for s in pending if s.id not in done]
    return results


def mode_plan(question: str, parallel: bool) -> tuple[str, int, int, float]:
    plan_reply = ask(question, system=PLANNER, schema=Plan)
    t0 = time.perf_counter()
    results = execute(plan_reply.parsed, parallel)
    tool_seconds = time.perf_counter() - t0
    lines = [f"{s.id} = {s.tool}({', '.join(f'{a.name}={a.value}' for a in s.args)}) -> {results[s.id]}"
             for s in plan_reply.parsed.steps]
    if VERBOSE:
        print("\n".join(f"   {line}" for line in lines))
    solved = ask(f"Question: {question}\nEvidence:\n" + "\n".join(lines), system=SOLVER)
    return solved.text, 2, plan_reply.in_tokens + solved.in_tokens, tool_seconds


MODES = {"loop": mode_loop,
         "plan": lambda q: mode_plan(q, parallel=False),
         "parallel": lambda q: mode_plan(q, parallel=True)}

if __name__ == "__main__":
    argv, args, runs = sys.argv[1:], [], 1
    while argv:
        a = argv.pop(0)
        if a == "--runs":
            runs = int(argv.pop(0))
        elif not a.startswith("--"):
            args.append(a)
    modes = [args[0]] if args else list(MODES)
    qs = [int(args[1])] if len(args) > 1 else list(QUESTIONS)
    print("| question | mode | correct | LLM calls | input tokens | tool seconds | total seconds |")
    print("|---|---|---|---|---|---|---|")
    for q in qs:
        question, expected = QUESTIONS[q]
        for mode in modes:
            rows = []
            for _ in range(runs):
                t0 = time.perf_counter()
                try:
                    answer, calls, tokens, tool_s = MODES[mode](question)
                except errors.APIError as e:  # the provider gave up after retries: a failed cell, not a crash
                    answer, calls, tokens, tool_s = f"provider error {e.code}", 0, 0, 0.0
                rows.append((expected in answer.replace(",", ""), calls, tokens, tool_s, time.perf_counter() - t0))
                if not rows[-1][0]:
                    print(f"|   | wrong: {answer.strip()[:140].replace(chr(10), ' ')} | | | | | |")
            med = lambda i: statistics.median(r[i] for r in rows)
            print(f"| {q} | {mode} | {sum(r[0] for r in rows)}/{runs} | {med(1):g} | {med(2):,.0f} "
                  f"| {med(3):.1f} | {med(4):.1f} |")