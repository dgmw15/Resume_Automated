"""
main.py — Entry point for the Job Application Automation system.

Usage:
    # Activate venv first:
    #   .venv\\Scripts\\activate
    python main.py

The script runs indefinitely in a restart loop.
If the orchestrator crashes, it waits 30 seconds and restarts from where
the Excel tracker left off.
"""

from __future__ import annotations

import asyncio
import logging
import time

from core.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RESTART_DELAY_SECONDS = 30


async def _run() -> None:
    orchestrator = Orchestrator()
    try:
        await orchestrator.start()
        await orchestrator.run_forever()
    finally:
        await orchestrator.stop()


def main() -> None:
    while True:
        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as exc:
            logger.exception("Orchestrator crashed: %s. Restarting in %ds…", exc, RESTART_DELAY_SECONDS)
            time.sleep(RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    main()
