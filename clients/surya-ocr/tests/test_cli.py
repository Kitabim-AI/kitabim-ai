from pathlib import Path
from unittest.mock import patch

import pytest

import cli


def test_build_parser_app_command():
    parser = cli.build_parser()
    args = parser.parse_args(["app"])
    assert args.command == "app"


def test_build_parser_preview_command():
    parser = cli.build_parser()
    args = parser.parse_args(["preview", "workdir"])
    assert args.command == "preview"
    assert args.workdir == "workdir"


def test_build_parser_push_command():
    parser = cli.build_parser()
    args = parser.parse_args(["push", "workdir", "--base-url", "http://x"])
    assert args.command == "push"
    assert args.base_url == "http://x"


def test_cmd_app_requires_kitabim_base_url_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("KITABIM_BASE_URL", raising=False)
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with pytest.raises(SystemExit, match="KITABIM_BASE_URL"):
        cli.cmd_app()


def test_cmd_app_requires_kitabim_work_dir_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("KITABIM_WORK_DIR", raising=False)

    with pytest.raises(SystemExit, match="KITABIM_WORK_DIR"):
        cli.cmd_app()


def test_cmd_app_starts_server_with_env_config(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with patch("cli.serve_app") as mock_serve_app:
        cli.cmd_app()

    mock_serve_app.assert_called_once()
    client_arg, work_root_arg = mock_serve_app.call_args.args
    assert isinstance(client_arg, cli.KitabimClient)
    assert client_arg.base_url == "http://localhost:8000"
    assert work_root_arg == Path("/tmp/work")


def test_cmd_app_loads_config_from_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.delenv("KITABIM_BASE_URL", raising=False)
    monkeypatch.delenv("KITABIM_WORK_DIR", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "KITABIM_BASE_URL=http://localhost:9000\nKITABIM_WORK_DIR=~/dotenv-work\n"
    )
    monkeypatch.setattr(cli, "DOTENV_PATH", dotenv_path)

    with patch("cli.serve_app") as mock_serve_app:
        cli.cmd_app()

    mock_serve_app.assert_called_once()
    client_arg, work_root_arg = mock_serve_app.call_args.args
    assert client_arg.base_url == "http://localhost:9000"
    assert work_root_arg == Path.home() / "dotenv-work"


def test_cmd_app_env_var_overrides_dotenv_file(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("KITABIM_BASE_URL=http://from-dotenv\n")
    monkeypatch.setattr(cli, "DOTENV_PATH", dotenv_path)
    monkeypatch.setenv("KITABIM_BASE_URL", "http://from-shell-env")
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with patch("cli.serve_app") as mock_serve_app:
        cli.cmd_app()

    client_arg, _ = mock_serve_app.call_args.args
    assert client_arg.base_url == "http://from-shell-env"
