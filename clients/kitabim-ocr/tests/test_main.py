from pathlib import Path
from unittest.mock import patch

import pytest

import main


def test_build_parser_default_command():
    parser = main.build_parser()
    args = parser.parse_args([])
    assert (args.command or "app") == "app"


def test_build_parser_app_command():
    parser = main.build_parser()
    args = parser.parse_args(["app"])
    assert args.command == "app"


def test_build_parser_preview_command():
    parser = main.build_parser()
    args = parser.parse_args(["preview", "workdir"])
    assert args.command == "preview"
    assert args.workdir == "workdir"


def test_build_parser_push_command():
    parser = main.build_parser()
    args = parser.parse_args(["push", "workdir", "--base-url", "http://x"])
    assert args.command == "push"
    assert args.base_url == "http://x"


def test_cmd_app_requires_kitabim_base_url_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("KITABIM_BASE_URL", raising=False)
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with pytest.raises(SystemExit, match="KITABIM_BASE_URL"):
        main.cmd_app()


def test_cmd_app_requires_kitabim_work_dir_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("KITABIM_WORK_DIR", raising=False)

    with pytest.raises(SystemExit, match="KITABIM_WORK_DIR"):
        main.cmd_app()


def test_cmd_app_starts_server_with_env_config(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with patch("main.serve_app") as mock_serve_app:
        main.cmd_app(engine="savitr")

    mock_serve_app.assert_called_once()
    client_arg, work_root_arg = mock_serve_app.call_args.args
    assert isinstance(client_arg, main.KitabimClient)
    assert client_arg.base_url == "http://localhost:8000"
    assert work_root_arg == Path("/tmp/work")
    assert mock_serve_app.call_args.kwargs.get("engine") == "savitr"


def test_build_parser_engine_option():
    parser = main.build_parser()
    args = parser.parse_args(["app", "--engine", "savitr"])
    assert args.command == "app"
    assert args.engine == "savitr"


def test_build_parser_concurrency_option():
    parser = main.build_parser()
    args = parser.parse_args(["app", "--concurrency", "2"])
    assert args.command == "app"
    assert args.concurrency == 2


def test_cmd_app_passes_concurrency(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with patch("main.serve_app") as mock_serve_app:
        main.cmd_app(concurrency=1)

    mock_serve_app.assert_called_once()
    assert mock_serve_app.call_args.kwargs.get("concurrency") == 1


def test_build_parser_concurrency_and_engine_before_subcommand():
    # A value passed before the subcommand must not be discarded by the
    # app subparser's own (unset) default for the same option.
    parser = main.build_parser()
    args = parser.parse_args(["--concurrency", "2", "--engine", "savitr", "app"])
    assert args.command == "app"
    assert args.concurrency == 2
    assert args.engine == "savitr"


def test_build_parser_concurrency_and_engine_after_subcommand_still_win():
    parser = main.build_parser()
    args = parser.parse_args(
        [
            "--concurrency",
            "1",
            "--engine",
            "surya",
            "app",
            "--concurrency",
            "3",
            "--engine",
            "savitr",
        ]
    )
    assert args.concurrency == 3
    assert args.engine == "savitr"


def test_cmd_app_loads_config_from_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.delenv("KITABIM_BASE_URL", raising=False)
    monkeypatch.delenv("KITABIM_WORK_DIR", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "KITABIM_BASE_URL=http://localhost:9000\nKITABIM_WORK_DIR=~/dotenv-work\n"
    )
    monkeypatch.setattr(main, "DOTENV_PATH", dotenv_path)

    with patch("main.serve_app") as mock_serve_app:
        main.cmd_app()

    mock_serve_app.assert_called_once()
    client_arg, work_root_arg = mock_serve_app.call_args.args
    assert client_arg.base_url == "http://localhost:9000"
    assert work_root_arg == Path.home() / "dotenv-work"


def test_cmd_app_env_var_overrides_dotenv_file(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("KITABIM_BASE_URL=http://from-dotenv\n")
    monkeypatch.setattr(main, "DOTENV_PATH", dotenv_path)
    monkeypatch.setenv("KITABIM_BASE_URL", "http://from-shell-env")
    with patch("main.serve_app") as mock_serve_app:
        main.cmd_app()

    client_arg, _ = mock_serve_app.call_args.args
    assert client_arg.base_url == "http://from-shell-env"


def test_cmd_push_passes_original_filename(tmp_path: Path):
    workdir_path = tmp_path / "work"
    wd = main.OcrWorkDir.create(
        workdir_path,
        source_pdf=workdir_path / "book.pdf",
        total_pages=1,
        original_filename="ئۇيغۇر_تارىخى.pdf",
    )
    (workdir_path / "book.pdf").write_bytes(b"%PDF-1.4")
    wd.set_page(1, text="text", is_toc=False, confidence=1.0, status="ocrd")
    wd.save()

    with patch.object(
        main.KitabimClient, "push_new_book", return_value={"bookId": "123"}
    ) as mock_push:
        main.cmd_push(workdir_path, "http://localhost:8000")

    mock_push.assert_called_once()
    assert mock_push.call_args.kwargs["filename"] == "ئۇيغۇر_تارىخى.pdf"


def test_cmd_push_resubmits_as_new_book_when_book_deleted_on_cloud(tmp_path: Path):
    workdir_path = tmp_path / "work"
    wd = main.OcrWorkDir.create(
        workdir_path,
        source_pdf=workdir_path / "book.pdf",
        total_pages=1,
        book_id="deleted_cloud_book",
        original_filename="book.pdf",
    )
    (workdir_path / "book.pdf").write_bytes(b"%PDF-1.4")
    wd.set_page(1, text="text", is_toc=False, confidence=1.0, status="ocrd")
    wd.save()

    with (
        patch.object(
            main.KitabimClient, "book_exists", return_value=False
        ) as mock_exists,
        patch.object(
            main.KitabimClient, "push_new_book", return_value={"bookId": "new_cloud_id"}
        ) as mock_push_new,
    ):
        main.cmd_push(workdir_path, "http://localhost:8000")

    mock_exists.assert_called_once_with("deleted_cloud_book")
    mock_push_new.assert_called_once()
    reloaded = main.OcrWorkDir.load(workdir_path)
    assert reloaded.book_id == "new_cloud_id"
    assert reloaded.uploaded is True


def test_build_parser_setup_savitr_command():
    parser = main.build_parser()
    args = parser.parse_args(
        ["setup-savitr", "--output", "/tmp/model", "--q-bits", "8"]
    )
    assert args.command == "setup-savitr"
    assert args.output == "/tmp/model"
    assert args.q_bits == 8


def test_cmd_setup_savitr_invokes_converter():
    with patch(
        "engine.savitr_engine.convert_surya_mlx_model", return_value="/custom/model"
    ) as mock_conv:
        main.cmd_setup_savitr(output_path="/custom/model", q_bits=4)

    mock_conv.assert_called_once_with(output_dir="/custom/model", q_bits=4)
