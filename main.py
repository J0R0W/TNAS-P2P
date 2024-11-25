import socket
import threading

# Function to handle receiving messages
def receive_messages(sock):
    while True:
        try:
            message = sock.recv(1024).decode()
            if message:
                print(f"\nPeer: {message}")
            else:
                break
        except:
            print("Connection closed.")
            break

# Function to send messages
def send_messages(sock):
    while True:
        message = input("You: ")
        sock.send(message.encode())

# Main function
def main():
    host = input("Enter your host (e.g., 127.0.0.1): ")
    port = int(input("Enter your port (e.g., 5000): "))
    peer_host = input("Enter peer's host (e.g., 127.0.0.1): ")
    peer_port = int(input("Enter peer's port (e.g., 5001): "))

    # Create a socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind to your host and port
    sock.bind((host, port))

    # Listen for incoming connections
    sock.listen(1)
    print(f"Listening on {host}:{port}...")

    # Connect to the peer
    try:
        sock.connect((peer_host, peer_port))
        print(f"Connected to peer at {peer_host}:{peer_port}")
    except:
        print(f"Waiting for peer to connect to {host}:{port}...")
        conn, addr = sock.accept()
        print(f"Peer connected from {addr}")
        sock = conn

    # Start threads for sending and receiving messages
    threading.Thread(target=receive_messages, args=(sock,)).start()
    threading.Thread(target=send_messages, args=(sock,)).start()

if _name_ == "_main_":
    main()
