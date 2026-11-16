import os
import secrets
import subprocess
import sysconfig
from pathlib import Path

from argon2 import PasswordHasher
from typer.testing import CliRunner

from frameread.cli.main import app


def test_set_password_is_atomic_and_requires_explicit_replacement(tmp_path):
    target = tmp_path / "admin_password_hash"
    password = secrets.token_urlsafe(24)
    runner = CliRunner()
    args = ["admin", "set-password", "--out", str(target)]
    assert runner.invoke(app, args, input=f"{password}\n{password}\n").exit_code == 0
    original = target.read_bytes()
    assert original.startswith(b"$argon2id$")
    assert PasswordHasher().verify(original.decode().strip(), password)
    assert runner.invoke(app, args, input="other\nother\n").exit_code != 0
    for invalid in ("\n\n", "first\nsecond\n"):
        assert runner.invoke(app, [*args, "--force"], input=invalid).exit_code != 0
        assert target.read_bytes() == original
    assert runner.invoke(app, [*args, "--force"], input=f"{password}\n{password}\n").exit_code == 0
    assert target.read_bytes() != original
    assert list(tmp_path.iterdir()) == [target]


def test_installed_cli_reads_redirected_stdin_without_echo(tmp_path):
    executable = Path(sysconfig.get_path("scripts")) / ("frameread.exe" if os.name == "nt" else "frameread")
    password = secrets.token_urlsafe(24)
    target = tmp_path / "admin_password_hash"
    result = subprocess.run(  # noqa: S603
        [str(executable), "admin", "set-password", "--out", str(target)],
        input=f"{password}\n{password}\n",
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert password not in result.stdout and password not in result.stderr
    assert PasswordHasher().verify(target.read_text().strip(), password)
