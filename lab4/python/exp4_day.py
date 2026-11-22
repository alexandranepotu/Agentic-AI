"""Lab 4 - Experiment 4: a day that actually works (STARTER).  Tests: pytest test_exp4_day.py -v"""
from collections import Counter

from pydantic import BaseModel, Field

from llm import ask

DAY_RULES = """Plan ONE day in Rome. Schedule all five items, each exactly once:
- Borghese Gallery: 2 h. Entry ONLY at 09:00, 11:00, 13:00 or 15:00.
- Colosseum: 2 h. Entry on the hour (xx:00), from 09:00 to 15:00.
- Pantheon: 1 h. Open 09:00-19:00 (must be finished by 19:00).
- Lunch: 1 h. Must START between 12:00 and 14:00.
- Trastevere food walk: 1 h 30 min. Starts ONLY at 17:00 or 18:00.
Moving between two consecutive items takes 30 minutes. The day starts at 09:00 and must end by 20:00.
Return the schedule in time order, times as HH:MM."""

WITH_HINT = (
    DAY_RULES
    + "\nBefore writing the schedule, first make a plan: place the items with the fewest allowed start "
    "times first, then fit the others around them, and check every rule (including the 30-minute moves) "
    "before you answer."
)

class Item(BaseModel):
    # A free string on purpose: the verifier catches any other spelling as an unknown item.
    name: str = Field(description="Exactly one of: Borghese Gallery, Colosseum, Pantheon, Lunch, Trastevere food walk")
    start: str
    end: str


class Schedule(BaseModel):
    items: list[Item]


class ScheduleWithPlan(BaseModel):
    """The same output as Schedule, but the model plans BEFORE it writes the items:
    the model writes the fields in the order they are declared, so `plan` comes first."""
    plan: str = Field(description="Your reasoning first: place the items with the fewest allowed start times, "
                                  "fit the others around them and check every rule, including the 30-minute moves")
    items: list[Item]


RULES = {  # name -> (duration in minutes, allowed start times)
    "Borghese Gallery": (120, [h * 60 for h in (9, 11, 13, 15)]),
    "Colosseum": (120, [h * 60 for h in range(9, 16)]),
    "Pantheon": (60, list(range(9 * 60, 18 * 60 + 1))),
    "Lunch": (60, list(range(12 * 60, 14 * 60 + 1))),
    "Trastevere food walk": (90, [17 * 60, 18 * 60]),
}


def minutes(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def check(schedule: Schedule) -> list[str]:
    """Deterministic verifier: returns the broken rules ([] = valid)."""
    errors = []
    counts = Counter(item.name for item in schedule.items)
    for name in RULES:  # each item exactly once
        if counts[name] != 1:
            errors.append(f"{name} appears {counts[name]} times")
    for name in counts:  # a name that is not in RULES
        if name not in RULES:
            errors.append(f"unknown item {name!r}")

    timed = []  # (start, end, name) of the items whose times could be read
    for item in schedule.items:
        try:
            start, end = minutes(item.start), minutes(item.end)
        except ValueError:
            errors.append(f"{item.name}: bad time format")
            continue
        timed.append((start, end, item.name))
        if item.name not in RULES:
            continue  # nothing else to check for an unknown item
        duration, allowed = RULES[item.name]
        if end - start != duration:
            errors.append(f"{item.name}: lasts {end - start} min, must be {duration}")
        if start not in allowed:
            errors.append(f"{item.name}: cannot start at {hhmm(start)}")

    timed.sort()
    for (_, end, first), (start, _, second) in zip(timed, timed[1:]):  # consecutive items
        if start - end < 30:
            errors.append(f"{first} -> {second}: needs 30 min to move")
    if timed and (timed[0][0] < 9 * 60 or max(e for _, e, _ in timed) > 20 * 60):
        errors.append("outside 09:00-20:00")
    return errors


def sample(prompt: str, schema=Schedule, n: int = 5) -> list[tuple[Schedule | None, list[str], int]]:
    out = []
    for _ in range(n):
        r = ask(prompt, schema=schema, temperature=1.0)
        if r.parsed is None:  # malformed JSON: an invalid sample, not a crash
            out.append((None, ["unparseable output"], r.out_tokens))
        else:
            out.append((r.parsed, check(r.parsed), r.out_tokens))
    return out


def best(samples):
    """Keep only the VALID samples (no errors) and return the schedule whose first item starts latest
    (Ana hates early mornings), or None if no sample is valid."""
    valid = [schedule for schedule, errs, _ in samples if schedule is not None and not errs]
    if not valid:
        return None
    return max(valid, key=lambda s: min(minutes(i.start) for i in s.items))


if __name__ == "__main__":
    runs = [("plain", DAY_RULES, Schedule),
            ("hint in the prompt, JSON only", WITH_HINT, Schedule),
            ("hint + a field to plan in", WITH_HINT, ScheduleWithPlan)]
    for label, prompt, schema in runs:
        samples = sample(prompt, schema)
        ok = sum(1 for _, errs, _ in samples if not errs)
        print(f"\n== {label}: {ok}/{len(samples)} valid, "
              f"{sum(t for *_, t in samples) / len(samples):.0f} output tokens on average")
        for _, errs, _ in samples:
            print("   ok" if not errs else f"   {errs[0]}" + (f" (+{len(errs) - 1} more)" if len(errs) > 1 else ""))
        chosen = best(samples)
        if chosen:
            print("   chosen: " + " | ".join(f"{i.start} {i.name}" for i in sorted(chosen.items, key=lambda i: minutes(i.start))))