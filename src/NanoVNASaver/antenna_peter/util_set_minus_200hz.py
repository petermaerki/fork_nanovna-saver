from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

# All known FT8 frequencies in Hz
_FT8_FREQUENCIES_HZ: frozenset[int] = frozenset(
    {
        1_840_000,
        3_573_000,
        5_357_000,
        7_074_000,
        10_136_000,
        14_074_000,
        18_100_000,
        21_074_000,
        24_915_000,
        28_074_000,
    }
)

REDUCE_HZ = 200


def is_ft8_frequency(freq_hz: float) -> bool:
    """Return True if freq_hz exactly matches a known FT8 frequency."""
    return int(freq_hz) in _FT8_FREQUENCIES_HZ


def set_frequency_minus_200hz(hostname: str, port: int, freq_hz: float) -> None:
    """If freq_hz is exactly an FT8 frequency, set rigctl to that frequency minus 200 Hz.

    Uses the rigctl 'F <freq>' command over a TCP socket connection.
    Does nothing if freq_hz is not an FT8 frequency.
    """
    freq_int = int(freq_hz)
    if freq_int not in _FT8_FREQUENCIES_HZ:
        logger.debug(
            "set_frequency_minus_200hz: %d Hz is not an FT8 frequency – skipped",
            freq_int,
        )
        return

    target_hz = freq_int - REDUCE_HZ
    try:
        with socket.create_connection((hostname, port), timeout=1) as s:
            cmd = f"F {target_hz}\n"
            s.sendall(cmd.encode("ascii"))
            logger.info(
                "Rigctl frequency set to %d Hz (FT8 %d Hz - %d Hz)",
                target_hz,
                freq_int,
                REDUCE_HZ,
            )
    except Exception:
        logger.exception(
            "set_frequency_minus_200hz: failed to set rigctl frequency to %d Hz",
            target_hz,
        )
