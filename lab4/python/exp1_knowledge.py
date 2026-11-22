"""Lab 4 - Experiment 1: what does the model actually know? (given, nothing to complete)"""
import sys

from llm import QuotaExhausted, ask

PROBES = [
    "What is today's date?",
    "What is the cheapest flight from Iasi to Rome next Tuesday, and how much does it cost?",
    "Which concerts are on in Rome in the second week of May 2027?",
    "Is the Borghese Gallery in Rome open on Mondays, and how do you get tickets?",
]

if __name__ == "__main__":
    for q in PROBES:
        try:
            r = ask(q)
        except QuotaExhausted as e:  # every next call would fail the same way: stop
            sys.exit(f"\n[stopped] {e}")
        except TimeoutError as e:  # one slow answer: report it and go on
            print(f"\n### {q}\n[timeout] {e}")
            continue
        print(f"\n### {q}\n{r.text.strip()[:600]}")