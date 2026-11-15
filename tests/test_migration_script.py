"""Safety checks for the migration wrapper using stand-in command line tools."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migrate-firebird-2.5-to-5.sh"
)


@pytest.mark.parametrize("failure", ["", "backup", "restore", "validation", "ods"])
def test_migration_publishes_only_validated_output(
    tmp_path: Path, failure: str
) -> None:
    source = tmp_path / "source with spaces.fdb"
    source.write_bytes(b"synthetic source")
    destination = tmp_path / "destination with spaces.fdb"
    commands = tmp_path / "commands"
    old = tmp_path / "old tools"
    new = tmp_path / "new tools"
    for directory in (commands, old / "bin", new):
        directory.mkdir(parents=True)

    def executable(path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body)
        path.chmod(0o700)

    executable(commands / "uname", "echo Linux\n")
    executable(
        old / "bin" / "gbak",
        'if [[ $1 == -z ]]; then echo "gbak version LI-V2.5.9"; exit 0; fi\n'
        '[[ $TEST_FAILURE != backup ]] || exit 1\n'
        'printf "synthetic backup" > "${@: -1}"\n',
    )
    executable(
        new / "gbak",
        'if [[ $1 == -z ]]; then echo "Firebird 5.0"; exit 0; fi\n'
        'printf "synthetic restore" > "${@: -1}"\n'
        '[[ $TEST_FAILURE != restore ]]\n',
    )
    executable(new / "gfix", '[[ $TEST_FAILURE != validation ]]\n')
    executable(
        new / "gstat",
        'if [[ $TEST_FAILURE == ods ]]; then echo "ODS version 11.2"; '
        'else echo "ODS version 13.1"; fi\n',
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("ISC_", "FB25_", "FB5_", "FIREBIRD"))
    }
    env.update(
        PATH=str(commands) + os.pathsep + env["PATH"],
        FB25_ROOT=str(old),
        FB5_BIN=str(new),
        ISC_PASSWORD="synthetic-password",
        TEST_FAILURE=failure,
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), str(source), str(destination)],
        env=env, capture_output=True, text=True, check=False,
    )
    assert source.read_bytes() == b"synthetic source"
    assert not list(tmp_path.glob(".tmp_fb-migration.*"))
    assert env["ISC_PASSWORD"] not in result.stdout + result.stderr
    if failure:
        assert result.returncode != 0
        assert not destination.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert destination.read_bytes() == b"synthetic restore"
        repeated = subprocess.run(
            ["bash", str(SCRIPT), str(source), str(destination)],
            env=env, capture_output=True, text=True, check=False,
        )
        assert repeated.returncode != 0
        assert "already exists" in repeated.stderr
        assert destination.read_bytes() == b"synthetic restore"
