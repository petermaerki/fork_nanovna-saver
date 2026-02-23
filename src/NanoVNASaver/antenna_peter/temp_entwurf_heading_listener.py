import socket

def main():
    UDP_IP = "127.0.0.1"
    UDP_PORT = 12000
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Höre auf GridTracker UDP Port {UDP_PORT}...")
    while True:
        data = sock.recvfrom(4096)[0]
        decoded_data = data.decode('utf-8', errors='ignore')
        print(f"Empfangen: {decoded_data}")

if __name__ == "__main__":
    main()
