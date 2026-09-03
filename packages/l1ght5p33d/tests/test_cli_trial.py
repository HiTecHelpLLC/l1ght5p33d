"""The first-run command prepares an exact public pack without approving it."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from l1ght5p33d import cli
from l1ght5p33d.fixtures import creative
from l1ght5p33d.policy import PermissionDenied


def sample_plan():
    return {
        "workflow_id": "poster-demo",
        "application": "browser",
        "targets": {"url": "http://127.0.0.1:7332"},
        "variables": {"title": "Synthetic poster"},
        "steps": [
            {
                "provider": "browser",
                "operation": "fill",
                "arguments": {"text": "Synthetic poster"},
                "effects": [{"field": "poster_title", "value": "Synthetic poster"}],
            }
        ],
        "policy": {"read_roots": []},
        "plan_digest": "a" * 64,
    }


@pytest.fixture
def trial_fakes(monkeypatch, tmp_path):
    from l1ght5p33d import mcp_server

    events = []

    class Service:
        def __init__(self, root, policy, **kwargs):
            self.root, self.policy, self.options = root, policy, kwargs
            self.companion = SimpleNamespace(start=lambda: events.append("maintenance"))
            events.append(self)

        def prepare_task(self, workflow_id, version, *, source):
            assert self.review_base_url == "http://127.0.0.1:7331"
            assert (workflow_id, version, source) == ("poster-demo", "0.1.0", "thebest")
            assert self.policy.approved_workflow_digests == []
            events.append("prepare")
            return {
                "plan": sample_plan(),
                "review_url": self.review_base_url + "/review/test",
            }

        def shutdown(self):
            events.append("shutdown")

    @contextmanager
    def fixture(*, port):
        assert port == 7332
        events.append("fixture_start")
        try:
            yield "http://127.0.0.1:7332"
        finally:
            events.append("fixture_stop")

    def app(service, token, *, port):
        assert len(token) >= 32
        service.review_base_url = f"http://127.0.0.1:{port}"
        events.append("app")
        return "synthetic-asgi-app"

    monkeypatch.setattr(cli, "WorkflowService", Service)
    monkeypatch.setattr(cli, "local_home", lambda: tmp_path)
    monkeypatch.setattr(creative, "serve_creative_fixture", fixture)
    monkeypatch.setattr(mcp_server, "create_app", app)
    monkeypatch.delenv("L1GHT5P33D_SESSION_TOKEN", raising=False)
    return events, tmp_path


def test_try_prepares_exact_pack_and_never_approves(trial_fakes, monkeypatch, capsys):
    events, root = trial_fakes

    class Server:
        def __init__(self, config):
            assert config.host == "127.0.0.1" and config.port == 7331
            assert config.access_log is False
            self.started = False

        def run(self):
            events.append("serve")

    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(
        cli.webbrowser, "open", lambda _: pytest.fail("Unexpected browser")
    )
    assert cli.main(["try", "--no-browser", "--cache-retention-days", "12"]) == 0
    service = events[1]
    assert service.root == root / "workflows"
    assert service.root.is_dir()
    assert service.options == {"state_root": root, "cache_retention_days": 12}
    assert service.policy.allow_loopback is False
    assert service.policy.allowed_origins == ["http://127.0.0.1:7332"]
    assert service.policy.allowed_operations == {"browser": ["fill", "select", "click"]}
    assert events[2:] == ["app", "prepare", "serve", "shutdown", "fixture_stop"]
    output = capsys.readouterr()
    assert "awaiting your approval" in output.out
    assert "Review and approve: http://127.0.0.1:7331/review/test" in output.out
    assert (root / "session.token").read_text() not in output.out + output.err


def test_try_browser_waits_until_owned_server_started(trial_fakes, monkeypatch):
    events, _ = trial_fakes
    opened = threading.Event()

    class Server:
        def __init__(self, _config):
            self.started = False

        def run(self):
            assert not opened.is_set()
            self.started = True
            assert opened.wait(2)

    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(cli.webbrowser, "open", lambda _: opened.set())
    assert cli.main(["try"]) == 0
    assert events[-2:] == ["shutdown", "fixture_stop"]


def test_try_bind_failure_does_not_open_another_process(trial_fakes, monkeypatch):
    events, _ = trial_fakes

    class Server:
        def __init__(self, _config):
            self.started = False

        def run(self):
            raise SystemExit(1)

    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(
        cli.webbrowser, "open", lambda _: pytest.fail("Unbound browser")
    )
    with pytest.raises(SystemExit):
        cli.main(["try"])
    assert events[-2:] == ["shutdown", "fixture_stop"]


def test_serve_defaults_and_token_stay_local(trial_fakes, monkeypatch):
    events, root = trial_fakes

    def run(app, **options):
        assert app == "synthetic-asgi-app"
        assert options == {
            "host": "127.0.0.1",
            "port": 7331,
            "log_level": "warning",
            "access_log": False,
        }

    monkeypatch.setattr(uvicorn, "run", run)
    assert cli.main(["serve"]) == 0
    assert events[0].root == root / "workflows"
    assert events[0].options["cache_retention_days"] == 90
    assert events[0].options["state_root"] == root


def test_rpc_custom_state_and_retention(trial_fakes, monkeypatch, tmp_path):
    from l1ght5p33d import mcp_server

    events, _ = trial_fakes
    root = tmp_path / "chosen-state"
    monkeypatch.setattr(
        mcp_server, "run_json_rpc", lambda service: events.append("rpc")
    )
    assert (
        cli.main(["rpc", "--state", str(root), "--cache-retention-days", "3650"]) == 0
    )
    assert events[0].root == root / "workflows"
    assert events[0].options["state_root"] == root
    assert events[0].options["cache_retention_days"] == 3650
    assert events[1:] == ["maintenance", "rpc", "shutdown"]


@pytest.mark.parametrize("command", ["try", "serve", "rpc"])
@pytest.mark.parametrize("days", ["0", "3651", "1.5", "forever"])
def test_cache_retention_rejects_unsafe_cli_values(command, days):
    with pytest.raises(SystemExit) as caught:
        cli.main([command, "--cache-retention-days", days])
    assert caught.value.code == 2


def test_run_summary_is_short_and_details_are_optional(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _: "APPROVE")
    cli._confirm_run(sample_plan())
    output = capsys.readouterr().out
    assert "Synthetic poster" in output
    assert "COMPLETE PLAN JSON" not in output
    answers = iter(["DETAILS", "APPROVE"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    cli._confirm_run(sample_plan())
    assert "COMPLETE PLAN JSON" in capsys.readouterr().out


def test_noninteractive_summary_cannot_approve(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(
        "builtins.input", lambda _: pytest.fail("Read noninteractive input")
    )
    with pytest.raises(PermissionDenied, match="interactive"):
        cli._confirm_run(sample_plan())


def test_summary_escapes_terminal_control_text():
    plan = sample_plan()
    plan["variables"]["title"] = "\x1b[2J\rAPPROVED"
    summary = cli._run_summary(plan)
    assert "\x1b" not in summary and "\r" not in summary
    assert "\\u001b" in summary


def test_creative_fixture_accepts_requested_port(monkeypatch):
    actual_server = creative.ThreadingHTTPServer
    seen = []

    def server(address, handler):
        seen.append(address)
        return actual_server(("127.0.0.1", 0), handler)

    monkeypatch.setattr(creative, "ThreadingHTTPServer", server)
    with creative.serve_creative_fixture(port=7332) as url:
        response = httpx.get(url + "/state", trust_env=False)
        assert response.status_code == 200
        assert json.loads(response.content) == {}
    assert seen == [("127.0.0.1", 7332)]


@pytest.mark.parametrize("port", [-1, 65536, True, "7332"])
def test_creative_fixture_rejects_invalid_port(port):
    with pytest.raises(ValueError, match="Fixture port"):
        with creative.serve_creative_fixture(port=port):
            pytest.fail("Invalid fixture port accepted")


def test_session_token_is_reused_without_logging_value(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("L1GHT5P33D_SESSION_TOKEN", raising=False)
    token = cli._session_token(tmp_path)
    assert cli._session_token(tmp_path) == token
    output = capsys.readouterr()
    assert token not in output.out + output.err
    assert Path(tmp_path / "session.token").stat().st_size >= 32
