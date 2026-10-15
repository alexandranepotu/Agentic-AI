from enum import Enum
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client()

class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class LogAnalysis(BaseModel):
    summary: str = Field(description="One-sentence technical summary of the event")
    severity: SeverityLevel = Field(description="The severity level of the incident based on the log")
    error_code: int = Field(description="Integer HTTP or system error code extracted from the log, or -1 if none exists")
    is_compromised: bool = Field(description="True if active unauthorized access succeeded, false otherwise")
    recommended_fix: list[str] = Field(description="List of concrete remediation steps to fix the vulnerability")

SYSTEM_PROMPT = """You are an expert Security Information and Event Management (SIEM) Analyst.
Extract a structured incident record from the provided raw server log.
Pay attention to the schema rules:
- Set severity to HIGH or CRITICAL if unauthorized root access succeeded.
- Extract any exact integer error code, or output -1 if none is present.
- Set is_compromised to true ONLY if the log shows successful unauthorized access.
- Provide concrete and actionable steps in the recommended_fix list."""

def parse_server_log(raw_log: str) -> LogAnalysis:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"Analyze the following raw server log:\n{raw_log}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=LogAnalysis,
        ),
    )
    # Validate and deserialize JSON string directly into the Pydantic object
    return LogAnalysis.model_validate_json(response.text)

if __name__ == "__main__":
    sample = (
        "2026-10-15 02:11:44 [ALERT] sshd[9012]: Accepted password for root "
        "from 198.51.100.77 port 44122 ssh2 (ErrorCode=401 bypassed via PAM bug)"
    )
    print(parse_server_log(sample).model_dump_json(indent=2))

# --- Automated Unit Test (Run with: pytest test_module2_structured.py) ---
def test_ssh_breach_log_parsing():
    sample_log = (
        "2026-10-15 02:11:44 [ALERT] sshd[9012]: Accepted password for root "
        "from 198.51.100.77 port 44122 ssh2 (ErrorCode=401 bypassed via PAM bug)"
    )
    result = parse_server_log(sample_log)

    assert result.severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]
    assert result.error_code == 401
    assert result.is_compromised is True
    assert len(result.recommended_fix) >= 1
