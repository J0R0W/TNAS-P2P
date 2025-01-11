import socket
import requests
import threading
import os
import argparse
import math


# Configuration
TRACKER_URL = "http://127.0.0.1:8080"
P2P_FOLDER = "p2p"
CHUNK_SIZE = 1024  # 1 MB per chunk (anpassbar)


def handle_client_connection(conn, addr):
    """
    Sends the entire file after sending 'OK <size>\n'.
    """
    try:
        data = conn.recv(1024).decode('utf-8').strip()
        if not data.startswith("REQUEST"):
            conn.sendall("ERROR Invalid request.\n".encode('utf-8'))
            return

        # "REQUEST filename"
        _, filename = data.split(" ", 1)
        file_path = os.path.join(P2P_FOLDER, filename)

        if not os.path.isfile(file_path):
            conn.sendall("NOTFOUND\n".encode('utf-8'))
            return

        file_size = os.path.getsize(file_path)
        # Send header
        header = f"OK {file_size}\n"
        conn.sendall(header.encode('utf-8'))

        # Send file data
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                conn.sendall(chunk)

    except Exception as e:
        print(f"[Server] Error handling request from {addr}: {e}")
    finally:
        conn.close()

def recv_line(sock):
    """
    Receives a single line (delimited by b'\n') from the socket.
    Returns the line (ohne '\n') als str.
    """
    data = b""
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break  # connection closed
        if chunk == b"\n":
            break
        data += chunk
    return data.decode('utf-8')


def request_file_size(peer, filename):
    """
    Connect to 'peer', request the file.
    Parse the first line: 'OK <size>' or 'NOTFOUND'.
    Returns the file size (int) or None if not found.
    Does NOT download the file data here (just reads the first line).
    """
    host, port = peer.split(":")
    port = int(port)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(f"REQUEST {filename}\n".encode('utf-8'))

            # Read exactly one line
            line = recv_line(s).strip()
            if not line:
                return None
            if line.startswith("NOTFOUND"):
                return None
            if not line.startswith("OK "):
                return None
            # "OK 12345" => size = 12345
            size_str = line.split(" ", 1)[1]
            try:
                file_size = int(size_str)
            except ValueError:
                return None

            return file_size
    except:
        return None


def server_thread(port):
    """
    Runs a simple server to seed files in the p2p folder.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('0.0.0.0', port))
        server_sock.listen(5)
        print(f"[Server] Listening on port {port}...")

        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(target=handle_client_connection, args=(conn, addr), daemon=True)
            t.start()


def register_with_tracker(peer_address):
    """
    Registers the peer with the tracker and retrieves the list of other peers.
    """
    try:
        response = requests.post(f"{TRACKER_URL}/register", json={"peer": peer_address})
        if response.status_code == 200:
            peers = response.json().get("peers", [])
            print(f"[Tracker] Registered successfully. Current peers: {peers}")
            return peers
        else:
            print("[Tracker] Failed to register with the tracker.")
            return []
    except Exception as e:
        print(f"[Tracker] Error contacting tracker: {e}")
        return []


def get_peers_from_tracker():
    """
    Retrieves the list of active peers from the tracker.
    """
    try:
        response = requests.get(f"{TRACKER_URL}/get_peers")
        if response.status_code == 200:
            peers = response.json().get("peers", [])
            return peers
        else:
            print("[Tracker] Failed to get peers from the tracker.")
            return []
    except Exception as e:
        print(f"[Tracker] Error contacting tracker: {e}")
        return []


def request_file_size(peer, filename):
    """
    Connects to 'peer' and requests the size of 'filename'.
    Returns the file size (int) or None if not found/error.
    """
    try:
        host, port = peer.split(":")
        port = int(port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((host, port))
            req = f"REQUEST {filename}\n"
            s.sendall(req.encode('utf-8'))

            header = s.recv(1024).decode('utf-8').strip()
            if header.startswith("NOTFOUND"):
                return None
            if not header.startswith("OK "):
                return None
            file_size = int(header.split(" ")[1])
            return file_size
    except:
        return None


def download_chunk_to_file(peer, filename, start, end, chunk_index, chunks_dir):
    """
    Downloads the ENTIRE file from 'peer', but only keeps [start:end).
    Saves it to:  <chunks_dir>/<chunk_index>.part
    Returns True on success, False on error.
    """
    host, port = peer.split(":")
    port = int(port)
    print(f"[Client] Downloading chunk {chunk_index} [{start}:{end}] from peer {peer}...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))

            # Request the file
            s.sendall(f"REQUEST {filename}\n".encode('utf-8'))

            # 1) Read header line
            line = recv_line(s).strip()  # e.g. "OK 262144"
            if not line or line.startswith("NOTFOUND"):
                print(f"[Client] Peer {peer} does not have {filename}.")
                return False
            if not line.startswith("OK "):
                print(f"[Client] Unexpected header from {peer}: {line}")
                return False

            # parse file size
            size_str = line.split(" ", 1)[1]
            total_size = int(size_str)

            # We'll download the entire file into memory (be careful if it's big!)
            file_data = b""
            received = 0
            while received < total_size:
                chunk = s.recv(4096)
                if not chunk:
                    break
                file_data += chunk
                received += len(chunk)

            if len(file_data) < total_size:
                print(f"[Client] Connection closed early from {peer}")
                return False

            # Now slice out [start:end)
            # If start/end are out of range, clamp them
            if start >= len(file_data):
                # This chunk is beyond EOF, produce empty file
                chunk_data = b""
            else:
                chunk_data = file_data[start:end]

            # Save chunk to disk
            out_path = os.path.join(chunks_dir, f"{chunk_index}.part")
            with open(out_path, 'wb') as f:
                f.write(chunk_data)

        return True
    except Exception as e:
        print(f"[Client] Error downloading chunk [{start}:{end}] from {peer}: {e}")
        return False


def parallel_download(filename, peers):
    """
    1) Bestimme file_size über 'request_file_size' bei einem beliebigen Peer.
    2) Erzeuge einen Ordner "filename_chunks" für die .part-Dateien.
    3) Starte Threads: Jeder Thread lädt [start, end) in eine .part-Datei.
    4) Warte auf Fertigstellung.
    5) Füge alle .part-Dateien zusammen und lösche sie.
    """
    if not peers:
        print("[Client] No peers available for parallel download.")
        return

    # 1) Determine file size
    file_size = None
    for p in peers:
        fs = request_file_size(p, filename)
        if fs is not None and fs > 0:
            file_size = fs
            break

    if file_size is None:
        print(f"[Client] Could not find '{filename}' on any peer.")
        return

    print(f"[Client] File size of '{filename}' is {file_size} bytes.")

    # 2) Create chunk directory
    chunk_dir = os.path.join(P2P_FOLDER, f"{filename}_chunks")
    if not os.path.exists(chunk_dir):
        os.makedirs(chunk_dir)

    # 3) Calculate number of chunks
    #    We'll use e.g. CHUNK_SIZE = 4 KB or 1 MB, je nachdem
    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    print(f"[Client] Downloading in {total_chunks} chunks...")

    # We'll keep a list of threads
    threads = []
    num_peers = len(peers)

    for i in range(total_chunks):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, file_size)
        assigned_peer = peers[i % num_peers]  # round-robin

        t = threading.Thread(
            target=download_chunk_to_file, 
            args=(assigned_peer, filename, start, end, i, chunk_dir),
            daemon=True
        )
        threads.append(t)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for all to finish
    for t in threads:
        t.join()

    # 4) Combine all .part files
    local_path = os.path.join(P2P_FOLDER, filename)
    with open(local_path, 'wb') as out_f:
        for i in range(total_chunks):
            part_path = os.path.join(chunk_dir, f"{i}.part")
            if os.path.exists(part_path):
                with open(part_path, 'rb') as p_f:
                    out_f.write(p_f.read())
                # Optional: remove the chunk file
                os.remove(part_path)

    # Optional: remove the chunk_dir if it's empty
    try:
        os.rmdir(chunk_dir)
    except OSError:
        pass

    print(f"[Client] Completed parallel download of '{filename}'. File is in '{local_path}'.")



def main():
    parser = argparse.ArgumentParser(description="P2P Client with Tracker (Parallel Downloads)")
    parser.add_argument('--port', type=int, required=True, help="Port to listen on.")
    args = parser.parse_args()
    port = args.port

    # Ensure the p2p folder exists
    if not os.path.exists(P2P_FOLDER):
        os.makedirs(P2P_FOLDER)

    # Start server (Seeder) thread
    t_server = threading.Thread(target=server_thread, args=(port,), daemon=True)
    t_server.start()

    # Register with the tracker
    my_address = f"127.0.0.1:{port}"
    peers = register_with_tracker(my_address)

    # CLI
    print("[CLI] Commands:")
    print("  LIST                  -> List all known peers")
    print("  GET <filename>        -> Download file from all known peers (in parallel)")
    print("  PEERS                 -> List all known peers (excluding self)")
    print("  FILES                 -> List files in p2p folder")
    print("  EXIT                  -> Exit the program")

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                continue

            cmd_parts = user_input.split()
            cmd = cmd_parts[0].upper()

            if cmd == "LIST":
                print(f"[CLI] Known peers: {peers}")

            elif cmd == "PEERS":
                # Re-fetch peers from tracker
                peers = get_peers_from_tracker()
                other_peers = [peer for peer in peers if peer != my_address]
                print(f"[CLI] Other known peers: {other_peers}")

            elif cmd == "FILES":
                files = os.listdir(P2P_FOLDER)
                print(f"[CLI] Files in p2p folder: {files}")

            elif cmd == "GET" and len(cmd_parts) == 2:
                filename = cmd_parts[1]
                # Always refresh peer list before download
                peers = get_peers_from_tracker()
                # Exclude self
                active_peers = [p for p in peers if p != my_address]
                parallel_download(filename, active_peers)

            elif cmd == "EXIT":
                print("[CLI] Exiting...")
                break

            else:
                print("[CLI] Unknown command.")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[CLI] Error: {e}")


if __name__ == "__main__":
    main()
