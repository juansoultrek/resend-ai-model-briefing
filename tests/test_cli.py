from ai_model_briefing.cli import main


def test_help_exits_successfully(capsys: object) -> None:
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0


def test_empty_command_exits_successfully() -> None:
    assert main([]) == 0
