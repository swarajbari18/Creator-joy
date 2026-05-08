from __future__ import annotations

import logging


def configure_debug_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    for noisy in ("httpcore", "httpx", "urllib3", "langsmith", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

