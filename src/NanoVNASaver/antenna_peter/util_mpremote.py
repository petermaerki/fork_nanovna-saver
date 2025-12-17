import logging
import subprocess

logger = logging.getLogger(__name__)


def mp_exec(cmd: str) -> None:
    args = ["mpremote", "resume","exec", cmd]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    logger.info(f'mpremote resume exec "{cmd}"')
    logger.debug(f"mpremote result: {result.stdout}")
    if result.returncode != 0:
        logger.error(f"mpremote error: {result.stderr}")

