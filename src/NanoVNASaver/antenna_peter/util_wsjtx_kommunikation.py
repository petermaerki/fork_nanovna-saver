"""
WSJT-X UDP broadcast listener.
Parses the WSJT-X network protocol (port 2237) and extracts
the TX audio offset frequency from Status messages.

WSJT-X UDP protocol reference:
  https://sourceforge.net/p/wsjt/wsjtx/ci/master/tree/Network/NetworkMessage.hpp

Status message (type=1):
  Magic     uint32  0xadbccbda
  Schema    uint32
  MsgType   uint32  = 1
  Id        utf8
  DialFreq  uint64  Hz
  Mode      utf8
  DXCall    utf8
  Report    utf8
  TxMode    utf8
  TxEnabled bool
  Transmitting bool
  Decoding  bool
  RxDF      uint32  (Rx audio frequency, Hz)
  TxDF      uint32  (Tx audio frequency / offset, Hz)  <-- we want this
  ...
"""
import contextlib
import logging
import socket
import struct
import threading

logger = logging.getLogger(__name__)

WSJTX_UDP_PORT = 2237
WSJTX_MAGIC = 0xADBCCBDA


def _read_utf8(data: bytes, pos: int) -> tuple[str, int]:
    """Read a length-prefixed utf8 string (uint32 length, -1 = null)."""
    if pos + 4 > len(data):
        raise ValueError("Buffer too short for utf8 length")
    (length,) = struct.unpack_from(">I", data, pos)
    pos += 4
    if length == 0xFFFFFFFF:  # null string
        return ("", pos)
    if pos + length > len(data):
        raise ValueError("Buffer too short for utf8 data")
    value = data[pos:pos + length].decode("utf-8", errors="replace")
    return (value, pos + length)


def _parse_status(data: bytes) -> int | None:
    """
    Parse a WSJT-X Status message and return TxDF (TX audio offset in Hz).
    Returns None if parsing fails.
    """
    try:
        pos = 0
        # Magic (4), Schema (4), MsgType (4) already checked by caller
        pos += 12

        # Id (utf8)
        _id, pos = _read_utf8(data, pos)

        # DialFreq (uint64)
        if pos + 8 > len(data):
            return None
        pos += 8

        # Mode (utf8)
        _mode, pos = _read_utf8(data, pos)

        # DXCall (utf8)
        _dxcall, pos = _read_utf8(data, pos)

        # Report (utf8)
        _report, pos = _read_utf8(data, pos)

        # TxMode (utf8)
        _txmode, pos = _read_utf8(data, pos)

        # TxEnabled (bool=1), Transmitting (bool=1), Decoding (bool=1)
        if pos + 3 > len(data):
            return None
        pos += 3

        # RxDF (uint32)
        if pos + 4 > len(data):
            return None
        pos += 4

        # TxDF (uint32)
        if pos + 4 > len(data):
            return None
        (tx_df,) = struct.unpack_from(">I", data, pos)
        return tx_df

    except Exception as e:
        logger.debug("WSJT-X parse_status error: %s", e)
        return None


class WsjtxListener:
    """
    Listens for WSJT-X UDP broadcasts in a background thread.
    Provides the latest TX audio offset (TxDF) in Hz.
    Thread-safe read via `tx_audio_offset_hz` property.
    """

    def __init__(self, port: int = WSJTX_UDP_PORT) -> None:
        self._port = port
        self._tx_audio_offset_hz: float | None = None  # None until first message received
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="WsjtxListener"
        )
        self._thread.start()
        logger.info("WsjtxListener started on UDP port %d", port)

    @property
    def tx_audio_offset_hz(self) -> float | None:
        """Returns the latest TxDF in Hz, or None if no WSJT-X data received yet."""
        with self._lock:
            return self._tx_audio_offset_hz

    def _listen_loop(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_REUSEPORT"):
                    with contextlib.suppress(Exception):
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                s.bind(("", self._port))
                while True:
                    data, _addr = s.recvfrom(4096)
                    self._handle(data)
        except Exception:
            logger.exception("WsjtxListener error")

    def _handle(self, data: bytes) -> None:
        if len(data) < 12:
            return
        magic, _schema, msg_type = struct.unpack_from(">III", data, 0)
        if magic != WSJTX_MAGIC:
            return
        if msg_type == 1:  # Status
            tx_df = _parse_status(data)
            if tx_df is not None:
                if not (0 <= tx_df <= 5000):
                    logger.warning("WSJT-X TxDF %d Hz außerhalb 0–5000 Hz – wird ignoriert.", tx_df)
                    return
                with self._lock:
                    self._tx_audio_offset_hz = float(tx_df)
                logger.debug("WSJT-X TxDF updated: %d Hz", tx_df)


