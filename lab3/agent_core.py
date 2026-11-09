"""agent_core.py - the reusable agent harness you build during Lab 3."""
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()
client = genai.Client()
MODEL = os.getenv("LAB_MODEL", "gemini-3.5-flash-lite")

@dataclass
class AgentResult:
    answer: str
    stop_reason: str
    steps: int
    prompt_tokens_per_step: list[int] = field(default_factory=list)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(self.prompt_tokens_per_step)

@dataclass
class Decision:
    approved: bool
    args: dict | None = None
    feedback: str = ""

Approver = Callable[[str, dict], Decision]

def call_llm(contents, config, retries: int = 5):
    for attempt in range(retries):
        try:
            return client.models.generate_content(model=MODEL, contents=contents, config=config)
        except errors.APIError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                wait = 2 ** attempt * 5
                print(f"  .. provider error {e.code}, retrying in {wait}s")
                time.sleep(wait)
            else:
                raise

def execute_tool(tools_map: dict[str, Callable], name: str, args: dict) -> str:
    """Gate: known tool? then run it. Every failure must become a readable string."""
    if name not in tools_map:
        return f"ERROR: Unknown tool '{name}'. Available tools: {', '.join(tools_map.keys())}."
    
    try:
        result = tools_map[name](**args)
        return str(result)
    except TypeError as e:
        return f"ERROR: Bad arguments for {name}: {e}"
    except Exception as e:
        return f"ERROR: {name} failed: {e}"

def run_agent(
    user_prompt: str,
    tools: list[Callable],
    system_instruction: str,
    max_steps: int = 8,
    requires_approval: frozenset[str] = frozenset(),
    approver: Approver | None = None,
    show_thoughts: bool = False,
    verbose: bool = True,
) -> AgentResult:
    tools_map = {fn.__name__: fn for fn in tools}
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=(types.ThinkingConfig(include_thoughts=True, thinking_level="high")
                         if show_thoughts else None),
    )
    messages = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]
    tokens: list[int] = []
    seen: Counter = Counter()

    for step in range(1, max_steps + 1):
        try:
            response = call_llm(messages, config)
        except errors.APIError as e:
            return AgentResult(f"STOPPED: provider error {e.code}: {e.message}", "provider_error", step, tokens)

        prompt_tokens = response.usage_metadata.prompt_token_count or 0
        tokens.append(prompt_tokens)
        
        if verbose:
            print(f"\n--- [Step {step}/{max_steps}] input tokens: {prompt_tokens:,} ---")
            
        content = response.candidates[0].content
        if verbose and content and content.parts:
            for part in content.parts:
                if part.thought and part.text:
                    print(f"  [Thought] {part.text.strip()[:300]}")

        if not response.function_calls:
            return AgentResult(response.text or "", "done", step, tokens)

        # 1. Append the model turn AS-IS
        messages.append(content)
        parts = []

        for call in response.function_calls:
            args = dict(call.args or {})
            if verbose:
                print(f"  -> [Tool Call] {call.name}({json.dumps(args)[:200]})")

            # STRETCH: Stuck-agent detector
            call_sig = (call.name, json.dumps(args, sort_keys=True))
            seen[call_sig] += 1
            if seen[call_sig] >= 3:
                return AgentResult(f"STOPPED: Stuck repeating {call.name}", "stuck", step, tokens)
            elif seen[call_sig] == 2:
                output = "NOTE: Repeated call with identical arguments. Use the earlier result."
            else:
                # HITL Policy Layer
                if call.name in requires_approval:
                    decision = approver(call.name, args) if approver else Decision(False, feedback="No approver configured")
                    if not decision.approved:
                        output = f"DENIED BY OPERATOR: {decision.feedback}. Adjust your plan."
                    else:
                        run_args = decision.args if decision.args is not None else args
                        output = execute_tool(tools_map, call.name, run_args)
                        if decision.args:
                            output = f"(Arguments edited by operator) {output}"
                else:
                    output = execute_tool(tools_map, call.name, args)

            if verbose:
                print(f"  <- [Tool Output] {output[:160]}")
                
            # Append ONE function_response part per call
            parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": output}
                )
            )

        # Append ALL parts in ONE message (role="user" for Gemini function responses)
        messages.append(types.Content(role="user", parts=parts))

    return AgentResult(
        f"STOPPED after {max_steps} steps without a final answer. Raise max_steps or narrow the task.",
        "max_steps", max_steps, tokens,
    )