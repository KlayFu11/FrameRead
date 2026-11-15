from pathlib import Path

from typer.testing import CliRunner

from frameread.cli.main import app

runner = CliRunner()

EXPECTED_FILES = {
    "master_key",
    "pg_superuser_password",
    "pg_migrate_password",
    "pg_app_password",
    "redis_password",
    "database_dsn_migrate",
    "database_dsn_app",
    "redis_url",
}


def test_init_creates_expected_files(tmp_path: Path):
    target = tmp_path / "secrets"
    result = runner.invoke(app, ["secrets", "init", "--dir", str(target)])
    assert result.exit_code == 0, result.output
    assert {p.name for p in target.iterdir()} == EXPECTED_FILES
    master = (target / "master_key").read_text()
    assert len(master.removesuffix("\n")) == 64
    bytes.fromhex(master.removesuffix("\n"))
    app_dsn = (target / "database_dsn_app").read_text()
    assert app_dsn.startswith("postgresql+psycopg://frameread_app:")
    assert (target / "pg_app_password").read_text().removesuffix("\n") in app_dsn
    assert "redis://" in (target / "redis_url").read_text()


def test_init_does_not_print_secret_values(tmp_path: Path):
    target = tmp_path / "secrets"
    result = runner.invoke(app, ["secrets", "init", "--dir", str(target)])
    for name in EXPECTED_FILES:
        assert (target / name).read_text().removesuffix("\n") not in result.output


def test_init_refuses_when_any_file_exists(tmp_path: Path):
    target = tmp_path / "secrets"
    target.mkdir()
    (target / "master_key").write_text("keep-me\n")
    result = runner.invoke(app, ["secrets", "init", "--dir", str(target)])
    assert result.exit_code == 1
    assert (target / "master_key").read_text() == "keep-me\n"
    assert {p.name for p in target.iterdir()} == {"master_key"}


def test_init_twice_keeps_first_contents(tmp_path: Path):
    target = tmp_path / "secrets"
    assert runner.invoke(app, ["secrets", "init", "--dir", str(target)]).exit_code == 0
    before = {p.name: p.read_text() for p in target.iterdir()}
    assert runner.invoke(app, ["secrets", "init", "--dir", str(target)]).exit_code == 1
    assert {p.name: p.read_text() for p in target.iterdir()} == before
