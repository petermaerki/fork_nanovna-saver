import socket
import sys

# This script listens for WSJT-X UDP broadcast messages (default port 2237)
# and prints all received messages to the console.

def listen_wsjt_udp(port=2237):
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
			s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			# Try to set SO_REUSEPORT for non-blocking listening (if available)
			if hasattr(socket, 'SO_REUSEPORT'):
				try:
					s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
				except Exception:
					pass
			s.bind(("", port))
			print(f"Listening for WSJT-X UDP messages on port {port} (shared)...")
			while True:
				data, addr = s.recvfrom(4096)
				print(f"From {addr}: {data.decode(errors='replace')}")
	except Exception as e:
		print(f"Error: {e}")

if __name__ == "__main__":
	port = 2237
	if len(sys.argv) > 1:
		port = int(sys.argv[1])
	listen_wsjt_udp(port)