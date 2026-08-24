# Copyright (c) 2026, René Moser <mail@renemoser.net>
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests of the command line interface."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from cloudstack_openapi import __version__
from cloudstack_openapi.cli import main


def test_generates_yaml_to_stdout(listapis_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--from-json", str(listapis_file)]) == 0

    document = yaml.safe_load(capsys.readouterr().out)
    assert document["openapi"] == "3.2.0"
    assert "/listZones" in document["paths"]


def test_writes_yaml_to_a_file(listapis_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "openapi.yaml"
    assert main(["--from-json", str(listapis_file), "-o", str(out)]) == 0

    assert yaml.safe_load(out.read_text(encoding="utf-8"))["openapi"] == "3.2.0"
    # The summary goes to stderr so stdout stays pipeable.
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "7 commands" in captured.err


def test_output_extension_selects_json(listapis_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert main(["--from-json", str(listapis_file), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["openapi"] == "3.2.0"


def test_format_flag_overrides_the_extension(listapis_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert main(["--from-json", str(listapis_file), "-o", str(out), "--format", "yaml"]) == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.read_text(encoding="utf-8"))


def test_document_options_are_passed_through(listapis_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = [
        "--from-json",
        str(listapis_file),
        "--format",
        "json",
        "--server-url",
        "https://cloud.example.com/client/api",
        "--title",
        "Example Cloud",
        "--api-version",
        "4.22.0.0",
        "--self",
        "https://example.com/openapi.json",
    ]
    assert main(argv) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["info"]["title"] == "Example Cloud"
    assert document["info"]["version"] == "4.22.0.0"
    assert document["servers"][0]["url"] == "https://cloud.example.com/client/api"
    assert document["$self"] == "https://example.com/openapi.json"


def test_api_version_defaults_to_unknown_offline(listapis_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--from-json", str(listapis_file), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["info"]["version"] == "unknown"


def test_dump_listapis_writes_a_reusable_catalogue(listapis_file: Path, tmp_path: Path, apis: list[dict[str, Any]]) -> None:
    dumped = tmp_path / "raw.json"
    assert main(["--from-json", str(listapis_file), "--dump-listapis", str(dumped), "-o", str(tmp_path / "o.yaml")]) == 0

    # The raw catalogue is saved verbatim, so it can be fed back in with --from-json.
    payload = json.loads(dumped.read_text(encoding="utf-8"))
    assert payload["count"] == len(apis)
    assert payload["api"] == apis


def test_output_is_byte_identical_across_runs(listapis_file: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a.yaml", tmp_path / "b.yaml"
    for out in (first, second):
        assert main(["--from-json", str(listapis_file), "-o", str(out)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_probing_needs_a_live_endpoint(listapis_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--from-json", str(listapis_file), "--probe-response-keys"]) == 1
    assert "needs a live endpoint" in capsys.readouterr().err


def test_missing_input_file_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--from-json", str(tmp_path / "nope.json")]) == 1
    assert "nope.json" in capsys.readouterr().err


def test_source_flags_are_mutually_exclusive(listapis_file: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--from-api", "--from-json", str(listapis_file)])


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_quiet_suppresses_the_summary(listapis_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--from-json", str(listapis_file), "-o", str(tmp_path / "o.yaml"), "--quiet"]) == 0
    assert capsys.readouterr().err == ""


def test_live_source_is_the_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Without --from-json the endpoint is queried and its version is adopted."""
    from cloudstack_openapi import cli

    client = object()
    monkeypatch.setattr(cli, "create_client", lambda endpoint: client)
    monkeypatch.setattr(cli, "fetch_listapis", lambda c: [{"name": "listZones", "isasync": False, "response": []}])
    monkeypatch.setattr(cli, "fetch_api_version", lambda c: "4.22.0.0")
    monkeypatch.setattr(cli, "probe_response_keys", lambda c, apis: {"listZones": ("zone", True)})

    assert main(["--format", "json", "--probe-response-keys"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["info"]["version"] == "4.22.0.0"
    payload = document["paths"]["/listZones"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "zone" in payload["properties"]["listzonesresponse"]["properties"]


def test_endpoint_is_passed_to_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloudstack_openapi import cli

    seen: list[str | None] = []
    monkeypatch.setattr(cli, "create_client", lambda endpoint: seen.append(endpoint))
    monkeypatch.setattr(cli, "fetch_listapis", lambda c: [{"name": "listZones", "isasync": False, "response": []}])
    monkeypatch.setattr(cli, "fetch_api_version", lambda c: "unknown")

    assert main(["--endpoint", "https://cloud.example.com/client/api", "-o", "/dev/null"]) == 0
    assert seen == ["https://cloud.example.com/client/api"]


def test_dependency_errors_are_reported(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from cloudstack_openapi import cli
    from cloudstack_openapi.errors import DependencyError

    def missing(endpoint: str | None) -> object:
        raise DependencyError("the 'cs' library is required")

    monkeypatch.setattr(cli, "create_client", missing)

    assert main([]) == 1
    assert "the 'cs' library is required" in capsys.readouterr().err


@pytest.mark.parametrize("command", [[sys.executable, "-m", "cloudstack_openapi"], ["cloudstack-openapi"]])
def test_entry_points_are_wired_up(command: list[str], listapis_file: Path) -> None:
    """Both `python -m cloudstack_openapi` and the console script reach the CLI."""
    result = subprocess.run([*command, "--from-json", str(listapis_file), "--format", "json"], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["openapi"] == "3.2.0"
