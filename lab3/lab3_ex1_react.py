"""Lab 3 - Ex1: a multi-hop ReAct agent (given: tools + task)."""
import json
import sys

from agent_core import run_agent

# --- Deterministic local "infrastructure" ---------------------------------
HOSTS = {
    "db-prod-01":   {"environment": "production", "packages": {"openssh-server": "9.6", "xz-utils": "5.6.1", "postgresql": "16.2"}},
    "web-edge-01":  {"environment": "production", "packages": {"nginx": "1.24.0", "log4j-core": "2.14.0", "openjdk": "17.0.9"}},
    "mail-prod-02": {"environment": "production", "packages": {"postfix": "3.8.4", "openssl": "3.0.13", "xz-utils": "5.4.6"}},
    "ci-runner-03": {"environment": "staging",    "packages": {"xz-utils": "5.6.0", "docker-ce": "26.1.0"}},
}

CVE_DB = [
    {"id": "CVE-2024-3094",  "package": "xz-utils",       "min": "5.6.0",  "max": "5.6.1",  "cvss": 10.0, "summary": "Backdoor in liblzma hooking RSA_public_decrypt in sshd."},
    {"id": "CVE-2021-44228", "package": "log4j-core",     "min": "2.0.0",  "max": "2.14.1", "cvss": 10.0, "summary": "Log4Shell: RCE via JNDI lookup in logged messages."},
    {"id": "CVE-2024-6387",  "package": "openssh-server", "min": "8.5",    "max": "9.7",    "cvss": 8.1,  "summary": "regreSSHion: race condition in sshd signal handler."},
    {"id": "CVE-2024-7347",  "package": "nginx",          "min": "1.5.13", "max": "1.27.0", "cvss": 4.7,  "summary": "Out-of-bounds read in ngx_http_mp4_module."},
]


def _v(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def list_hosts() -> str:
    """List every managed server with its environment (production or staging)."""
    return json.dumps([{"hostname": h, "environment": d["environment"]} for h, d in HOSTS.items()])


def get_installed_packages(hostname: str) -> str:
    """Return the installed packages and versions on one server.

    Args:
        hostname: Exact hostname as returned by list_hosts, e.g. 'db-prod-01'.
    """
    host = HOSTS.get(hostname)
    if host is None:
        return f"ERROR: Host '{hostname}' not found. Known hosts: {', '.join(HOSTS)}."
    return json.dumps(host["packages"])


def find_cves_for_package(package: str, version: str) -> str:
    """Return the known CVEs (id, CVSS score, summary) that affect one package at one version.

    Args:
        package: Package name, e.g. 'xz-utils'.
        version: Installed version, e.g. '5.6.1'.
    """
    try:
        v = _v(version)
    except ValueError:
        return f"ERROR: Version '{version}' is not numeric (expected e.g. '5.6.1')."
    hits = [
        {"id": c["id"], "cvss": c["cvss"], "summary": c["summary"]}
        for c in CVE_DB
        if c["package"] == package and _v(c["min"]) <= v <= _v(c["max"])
    ]
    return json.dumps(hits)  # [] means "no known CVE"


SYSTEM = (
    "You are an infrastructure security agent. Never guess: discover hosts, packages and CVEs "
    "with your tools. Call independent tools in parallel in the same turn. "
    "Final answer: one line per affected host (host, package, CVE, CVSS), then hosts you checked and found clean."
)

if __name__ == "__main__":
    result = run_agent(
        "Which of our PRODUCTION hosts are exposed to a vulnerability with CVSS >= 9.0?",
        tools=[list_hosts, get_installed_packages, find_cves_for_package],
        system_instruction=SYSTEM,
        max_steps=8,
        show_thoughts="--thoughts" in sys.argv,
    )
    print(f"\n[Final Agent Answer] (stop_reason={result.stop_reason}, steps={result.steps})\n{result.answer}")
    print(f"\nInput tokens per step: {result.prompt_tokens_per_step}  total={result.total_prompt_tokens:,}")
