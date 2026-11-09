"""Deterministic tests for the Ex2 guardrails - no LLM calls. Run: pytest test_lab3_ex2.py -v"""
import pytest

import lab3_ex2_hitl as ex2
from agent_core import Decision


@pytest.fixture(autouse=True)
def workspace():
    ex2.setup_workspace()


@pytest.mark.parametrize("attack", [
    "../canary_secret.txt",
    "../../.env",
    "subdir/../../canary_secret.txt",
    "/etc/passwd",
    "C:/Windows/win.ini",
])
def test_read_outside_sandbox_is_blocked(attack):
    out = ex2.read_file(attack)
    assert "SECURITY VIOLATION" in out
    assert ex2.CANARY not in out


def test_write_outside_sandbox_is_blocked():
    out = ex2.write_file("../pwned.txt", "x")
    assert "SECURITY VIOLATION" in out
    assert not (ex2.WORKSPACE / "pwned.txt").exists()


def test_normal_files_work():
    assert "PermitRootLogin yes" in ex2.read_file("sshd_config")
    assert ex2.write_file("new.conf", "Port 2222\n").startswith("SUCCESS")
    assert ex2.read_file("./new.conf") == "Port 2222\n"


def test_missing_file_error_lists_real_files():
    assert "sshd_config" in ex2.read_file("sshd.conf")


def _answers(monkeypatch, *replies):
    it = iter(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


def test_approver_yes(monkeypatch):
    _answers(monkeypatch, "yes")
    assert ex2.terminal_approver("write_file", {"filename": "a", "content": "b"}) == Decision(True)


def test_approver_feedback_is_a_rejection(monkeypatch):
    _answers(monkeypatch, "write to sshd_config.hardened instead")
    d = ex2.terminal_approver("write_file", {"filename": "sshd_config", "content": "x"})
    assert d.approved is False and "hardened" in d.feedback


def test_approver_edit_changes_args(monkeypatch):
    _answers(monkeypatch, "e", "sshd_config.hardened")
    d = ex2.terminal_approver("write_file", {"filename": "sshd_config", "content": "x"})
    assert d.approved and d.args["filename"] == "sshd_config.hardened"
