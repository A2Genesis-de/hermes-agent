"""Regression for #68523 — one systemctl timeout must not abort fleet restarts.

On hosts with many profile-backed ``a2assistant-gateway*.service`` units,
``a2assistant update`` used to wrap the entire per-scope unit loop in a single
``except subprocess.TimeoutExpired``. A timeout on unit N skipped units
N+1…, leaving later gateways on pre-update in-memory modules while the
checkout on disk was already new (mixed-generation crashes).
"""

from __future__ import annotations

import subprocess

import pytest

from hermes_cli.update_cmd import _for_each_systemd_gateway_unit, _service_unit_supports_graceful_sigusr1_restart, _warn_incomplete_gateway_fleet_restart


def _list_units_stdout(names: list[str]) -> str:
    return "\n".join(f"{name}.service loaded active running" for name in names)


class TestFleetRestartTimeoutIsolation:
    def test_timeout_on_middle_unit_continues_remaining_units(self):
        units = [
            "a2assistant-gateway-xiaomo1",
            "a2assistant-gateway-xiaomo2",
            "a2assistant-gateway-xiaomo3",
            "a2assistant-gateway-xiaomo4",
            "a2assistant-gateway-xiaomo5",
            "a2assistant-gateway-xiaomo6",
            "a2assistant-gateway-xiaomo7",
            "a2assistant-gateway",
        ]
        restarted: list[str] = []
        failed: list[str] = []
        timeout_cmds: list = []

        def process_unit(svc_name: str) -> None:
            if svc_name == "a2assistant-gateway-xiaomo5":
                raise subprocess.TimeoutExpired(
                    cmd=["systemctl", "--user", "--no-ask-password", "restart", svc_name],
                    timeout=15,
                )
            restarted.append(svc_name)

        def on_unit_timeout(svc_name: str, exc: subprocess.TimeoutExpired) -> None:
            failed.append(svc_name)
            timeout_cmds.append(exc.cmd)

        _for_each_systemd_gateway_unit(
            _list_units_stdout(units),
            process_unit=process_unit,
            on_unit_timeout=on_unit_timeout,
        )

        assert failed == ["a2assistant-gateway-xiaomo5"]
        assert restarted == [
            "a2assistant-gateway-xiaomo1",
            "a2assistant-gateway-xiaomo2",
            "a2assistant-gateway-xiaomo3",
            "a2assistant-gateway-xiaomo4",
            "a2assistant-gateway-xiaomo6",
            "a2assistant-gateway-xiaomo7",
            "a2assistant-gateway",
        ]
        assert set(restarted) | set(failed) == set(units)
        assert timeout_cmds == [
            ["systemctl", "--user", "--no-ask-password", "restart", "a2assistant-gateway-xiaomo5"]
        ]

    def test_non_gateway_units_in_list_output_are_ignored(self):
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "a2assistant-gateway-coder.service loaded active running",
                    "not-a-service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["a2assistant-gateway-coder"]

    def test_hermes_serve_units_are_included(self):
        # #83438 — hermes update restarted hermes-gateway* units but left
        # hermes-serve* (the Desktop app's backend) on stale pre-update code.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "hermes-serve.service loaded active running",
                    "hermes-serve-work.service loaded active running",
                    "a2assistant-gateway.service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["hermes-serve", "hermes-serve-work", "a2assistant-gateway"]

    def test_hermes_dashboard_units_are_included(self):
        # #125297 — the same blind spot for the systemd-supervised dashboard: the
        # unit pass skipped hermes-dashboard*, so a successful update left the
        # dashboard on pre-update code with outcome "deferred" and nothing
        # restarted it. Reconciliation already credits hermes-dashboard{,-<profile>}
        # unit restarts; the pass must produce one.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            "\n".join(
                [
                    "ssh.service loaded active running",
                    "hermes-dashboard.service loaded active running",
                    "hermes-dashboard-work.service loaded active running",
                    "hermes-serve.service loaded active running",
                    "",
                ]
            ),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["hermes-dashboard", "hermes-dashboard-work", "hermes-serve"]

    def test_hermes_dashboard_near_prefix_is_rejected(self):
        # Same strict shape on the dashboard side: a bare
        # ``startswith("hermes-dashboard")`` gate would also accept the
        # unrelated ``hermes-dashboardd.service``.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["hermes-dashboardd", "hermes-dashboard-work"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["hermes-dashboard-work"]

    def test_hermes_server_near_prefix_is_rejected(self):
        # Review on #83595: a bare ``startswith("hermes-serve")`` gate also
        # accepts the unrelated ``hermes-server.service``. Only the exact
        # base unit or the hyphenated profile family should pass.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["hermes-server"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == []

    def test_hermes_gateway_near_prefix_is_rejected(self):
        # Same strict shape on the gateway side: profile units are
        # ``hermes-gateway-<profile>``, so a hypothetical
        # ``hermes-gatewayd.service`` must not enter the restart path.
        seen: list[str] = []

        _for_each_systemd_gateway_unit(
            _list_units_stdout(["hermes-gatewayd", "a2assistant-gateway-coder"]),
            process_unit=seen.append,
            on_unit_timeout=lambda *_: pytest.fail("unexpected timeout"),
        )

        assert seen == ["a2assistant-gateway-coder"]


class TestGracefulSigusr1Eligibility:
    def test_gateway_units_are_eligible(self):
        assert _service_unit_supports_graceful_sigusr1_restart("a2assistant-gateway")
        assert _service_unit_supports_graceful_sigusr1_restart(
            "a2assistant-gateway-work"
        )

    def test_serve_units_are_not_eligible(self):
        # hermes-serve doesn't run gateway/run.py, so it never installs the
        # SIGUSR1 handler — sending it the signal would just terminate the
        # process (the default action) instead of draining gracefully.
        assert not _service_unit_supports_graceful_sigusr1_restart("hermes-serve")
        assert not _service_unit_supports_graceful_sigusr1_restart(
            "hermes-serve-work"
        )

    def test_process_errors_other_than_timeout_still_propagate(self):
        def process_unit(_svc_name: str) -> None:
            raise RuntimeError("not a timeout")

        with pytest.raises(RuntimeError, match="not a timeout"):
            _for_each_systemd_gateway_unit(
                _list_units_stdout(["a2assistant-gateway"]),
                process_unit=process_unit,
                on_unit_timeout=lambda *_: pytest.fail("timeout handler must not run"),
            )


class TestIncompleteFleetRestartWarning:
    def test_warns_with_exact_unrestarted_units(self, capsys):
        _warn_incomplete_gateway_fleet_restart(
            ["a2assistant-gateway-xiaomo5", "a2assistant-gateway-xiaomo6", "a2assistant-gateway-xiaomo5"]
        )
        out = capsys.readouterr().out
        assert "Update incomplete" in out
        assert out.count("a2assistant-gateway-xiaomo5") == 1
        assert "a2assistant-gateway-xiaomo6" in out
        assert "pre-update code" in out

