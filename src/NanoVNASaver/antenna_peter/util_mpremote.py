#  Magnetic Loop Antenna Control for NanoVNASaver
#
#  MicroPython device communication utilities
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import logging
import subprocess

import serial.tools.list_ports

logger = logging.getLogger(__name__)


def mp_exec(device: str, cmd: str) -> None:
    args = ["mpremote", "connect", device, "resume","exec", cmd]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    logger.info(f'mpremote connect {device} resume exec "{cmd}"')
    logger.debug(f"mpremote result: {result.stdout}")
    if result.returncode != 0:
        logger.error(f"mpremote error: {result.stderr}")

def get_device() -> str:
    """Find the connected device with specific vendor and product IDs.
    
    Returns:
        Device path like /dev/ttyACM1
        
    Raises:
        RuntimeError: If no matching device is found
    """
    idVendor = 0x2e8a
    idProduct = 0x0005
    
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid == idVendor and port.pid == idProduct:
            logger.info(f"Found device at {port.device} (VID:PID {port.vid:04x}:{port.pid:04x})")
            return port.device
    
    raise RuntimeError(f"No device found with VID:PID {idVendor:04x}:{idProduct:04x}")



