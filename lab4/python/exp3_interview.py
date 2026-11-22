"""Lab 4 - Experiment 3: ask before you plan (STARTER).

    python exp3_interview.py              # you answer the questions
    python exp3_interview.py --vague      # step A: what happens when nobody asks
    python exp3_interview.py --simulate   # a simulated traveler with a hidden profile answers
"""
import sys
from typing import Literal

from pydantic import BaseModel, Field

from llm import ask

FIRST_MESSAGE = "Plan me a nice 4-day trip in May."
MAX_QUESTIONS = 8


class TravelBrief(BaseModel):
    origin: str | None = Field(None, description="City the trip starts from")
    destination: str | None = Field(None, description="City or region, or 'open' if the traveler wants suggestions")
    dates: str | None = Field(None, description="Arrival and departure dates, e.g. '12-16 May'")
    travelers: int | None = Field(None, description="How many people travel")
    budget_eur: int | None = Field(None, description="Total budget for the whole trip, in EUR")
    interests: list[str] = Field(default_factory=list, description="What they enjoy doing")
    pace: Literal["relaxed", "balanced", "packed"] | None = None
    avoid: list[str] = Field(default_factory=list, description="Things they do not want")


class InterviewTurn(BaseModel):
    brief: TravelBrief = Field(description="Everything learned so far; unknown fields stay null")
    next_question: str = Field(description="ONE short question about the most important unknown, or '' when done")


REQUIRED = ["origin", "destination", "dates", "travelers", "budget_eur", "interests"]

INTERVIEWER = (
    "You are the interviewer of a trip-planning platform. You do NOT plan the trip: never suggest "
    "destinations, hotels, activities or itineraries, and never answer for the traveler. "
    "Your only job is to fill the brief with what the traveler has actually said in the conversation. "
    "Do NOT guess and do NOT invent defaults: a field the traveler did not state stays null "
    "(an empty list for interests and avoid). "
    "For 'dates' write the exact days only when the traveler gave them (e.g. '12-16 May'); "
    "a month alone or a number of days alone is not enough, so leave 'dates' null and ask for the exact days. "
    "If the traveler says they have no destination in mind and want suggestions, write 'open' as the destination. "
    "Always return the full brief with everything learned so far, including from earlier turns. "
    "Then ask ONE short question, about the single most important unknown (never several questions at once, "
    "never something the traveler already answered). Priority: destination, dates, number of travelers, "
    "origin city, budget, interests, then pace and things to avoid. "
    "When nothing is missing, set next_question to an empty string."
)


def missing_required(brief: TravelBrief) -> list[str]:
    """The harness decides when the brief is complete, not the model."""
    return [name for name in REQUIRED if getattr(brief, name) in (None, "", [])]


# --- A simulated traveler for hands-free testing ---------------------------
PERSONA = (
    "You are Ana, a student from Iasi. Hidden facts about your trip: 2 people (you and a friend), "
    "12-16 May, total budget 1000 EUR, you love street food and old history, you hate early mornings, "
    "you have no destination in mind and want a suggestion in Italy. "
    "Answer ONLY the question asked, in one short sentence, like a real person would. Never volunteer extra facts."
)


def simulated_answer(transcript: str, question: str) -> str:
    return ask(f"Conversation so far:\n{transcript}\nThe planner asks: {question}\nYour reply:",
               system=PERSONA, temperature=0.7).text.strip()


def interview(first_message: str, answer_fn) -> tuple[TravelBrief, int]:
    transcript = f"Traveler: {first_message}"
    brief = TravelBrief()
    for asked in range(MAX_QUESTIONS):
        turn: InterviewTurn = ask(f"Conversation so far:\n{transcript}",
                                  system=INTERVIEWER, schema=InterviewTurn).parsed
        brief = turn.brief
        missing = missing_required(brief)
        if not missing:  # the harness says the brief is complete, whatever the model put in next_question
            return brief, asked
        # an empty question while something is still missing: ask about it ourselves
        question = turn.next_question or f"Could you tell me about this: {missing[0]}?"
        print(f"\n[Planner] {question}")
        reply = answer_fn(transcript, question)
        print(f"[Traveler] {reply}")
        transcript += f"\nPlanner: {question}\nTraveler: {reply}"
    return brief, MAX_QUESTIONS


if __name__ == "__main__":
    if "--vague" in sys.argv:
        print(ask(FIRST_MESSAGE).text)
        sys.exit()
    answer_fn = simulated_answer if "--simulate" in sys.argv else (lambda _t, _q: input("> ").strip())
    print(f"[Traveler] {FIRST_MESSAGE}")
    brief, questions = interview(FIRST_MESSAGE, answer_fn)
    print(f"\n[Brief after {questions} questions] missing: {missing_required(brief) or 'nothing'}")
    print(brief.model_dump_json(indent=2))