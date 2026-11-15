import asyncio
import sys

# psycopg 异步驱动在 Windows 上需要 SelectorEventLoop；生产运行于 Linux 容器
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
