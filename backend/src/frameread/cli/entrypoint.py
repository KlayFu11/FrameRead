import sys


def run() -> None:
    # 容器 live 检查只有 3s；先分发标准库路径，避免加载数据库、Web 和 Typer 依赖。
    if sys.argv[1:3] == ["health", "live"]:
        from frameread.observability.liveness import main

        raise SystemExit(main(sys.argv[3:], prog="frameread health live"))

    from frameread.cli.main import run as run_cli

    run_cli()
