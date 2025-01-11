import socket
import requests
import threading
import os
import argparse
import math
import time
from tqdm import tqdm  # progress bar

# Configuration
TRACKER_URL = "http://127.0.0.1:8080"
P2P_FOLDER = "p2p"
CHUNK_SIZE = 1024  # 1 MB per chunk (adjustable)
MAX_RETRIES = 3            # Maximum number of retries per chunk


def recv_line(sock):
    """
    Receives a single line (delimited by b'\n') from the socket.
    Returns the line (without '\n') as a string.
    """
    data = b""
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break  # Connection closed
        if chunk == b"\n":
            break
        data += chunk
    return data.decode('utf-8')


def handle_client_connection(conn, addr):
    """
    Handles incoming connections to serve requested files.
    Expects request: "REQUEST <filename>"
    Returns: "OK <file_size>\n" followed by file content
    """
    try:
        data = conn.recv(1024).decode('utf-8').strip()
        if not data.startswith("REQUEST"):
            conn.sendall("ERROR Invalid request.\n".encode('utf-8'))
            return

        _, filename = data.split(" ", 1)
        file_path = os.path.join(P2P_FOLDER, filename)

        if not os.path.isfile(file_path):
            conn.sendall("NOTFOUND\n".encode('utf-8'))
            return

        # Send file size
        file_size = os.path.getsize(file_path)
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

def get_available_peers_for_file(peers, filename):
    """
    Check which peers have the specified file.
    Returns a list of peers that have the file.
    """
    available_peers = []
    for peer in peers:
        if request_file_size(peer, filename) is not None:
            available_peers.append(peer)
    return available_peers


def get_peers_from_tracker():
    """
    Retrieves the list of active peers from the tracker.
    """
    try:
        response = requests.get(f"{TRACKER_URL}/get_peers")
        if response.status_code == 200:
            peers = response.json().get("peers", [])
            print(f"[Tracker] Current peers: {peers}")
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
    Returns the file size (int) or None if not found.
    """
    try:
        host, port = peer.split(":")
        port = int(port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))
            req = f"REQUEST {filename}\n"
            s.sendall(req.encode('utf-8'))

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


def download_chunk_to_file(peer, filename, start, end, chunk_index, chunks_dir, lock, failed_chunks):
    """
    Downloads a chunk from 'peer' and saves it to a temporary file.
    If the download fails, it adds the chunk index to 'failed_chunks'.
    """
    host, port = peer.split(":")
    port = int(port)

    #print(f"[Client] Attempting to download chunk {chunk_index} [{start}:{end}] from {peer}...")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(f"REQUEST {filename}\n".encode('utf-8'))

            # Read header line
            line = recv_line(s).strip()
            if not line or line.startswith("NOTFOUND"):
                tqdm.write(f"[Client] Peer {peer} does not have {filename}.")
                raise Exception("File not found on peer.")
            if not line.startswith("OK "):
                tqdm.write(f"[Client] Unexpected header from {peer}: {line}")
                raise Exception("Unexpected header.")

            # Parse file size
            size_str = line.split(" ", 1)[1]
            total_size = int(size_str)

            # Download entire file
            file_data = b""
            received = 0
            while received < total_size:
                chunk = s.recv(4096)
                if not chunk:
                    break
                file_data += chunk
                received += len(chunk)

            if len(file_data) < total_size:
                raise Exception("Incomplete file received.")

            # Extract the relevant chunk data
            if start >= len(file_data):
                chunk_data = b""  # Chunk is beyond EOF
            else:
                chunk_data = file_data[start:end]

            # Save chunk to disk
            out_path = os.path.join(chunks_dir, f"{chunk_index}.part")
            with open(out_path, 'wb') as f:
                f.write(chunk_data)

        #print(f"[Client] Successfully downloaded chunk {chunk_index} from {peer}.")
        return True

    except Exception as e:
        tqdm.write(f"[Client] Error downloading chunk {chunk_index} from {peer}: {e}")
        with lock:
            failed_chunks.append(chunk_index)
        return False



def parallel_download(filename, peers):
    """
    Downloads the file in parallel from available peers.
    Failed chunks are retried with other peers.
    """
    if not peers:
        tqdm.write("[Client] No peers available for download.")
        return

    # 1. Check which peers have the file
    available_peers = get_available_peers_for_file(peers, filename)
    if not available_peers:
        tqdm.write(f"[Client] No peers have the file '{filename}'.")
        return

    # 2. Determine file size from the first available peer
    file_size = request_file_size(available_peers[0], filename)
    if file_size is None:
        tqdm.write(f"[Client] Could not determine file size for '{filename}'.")
        return

    tqdm.write(f"[Client] File size of '{filename}' is {file_size} bytes.")

    # 3. Create chunk directory
    chunk_dir = os.path.join(P2P_FOLDER, f"{filename}_chunks")
    if not os.path.exists(chunk_dir):
        os.makedirs(chunk_dir)

    # 4. Calculate number of chunks
    total_chunks = math.ceil(file_size / CHUNK_SIZE)
    tqdm.write(f"[Client] Downloading in {total_chunks} chunks...")

    # 5. Thread-safe list for failed chunks
    failed_chunks = []
    lock = threading.Lock()

    # 6. Create Progress-Bar
    progress_bar = tqdm(total=total_chunks, desc=f"Downloading {filename}", unit="chunk")

    # 7. Download chunks in parallel
    def thread_download(chunk_index, assigned_peer):
        start = chunk_index * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, file_size)
        success = download_chunk_to_file(assigned_peer, filename, start, end, chunk_index, chunk_dir, lock, failed_chunks)
        if success:
            progress_bar.update(1)  # Update progress bar for successful download

    threads = []
    num_peers = len(available_peers)

    for i in range(total_chunks):
        assigned_peer = available_peers[i % num_peers]  # Round-robin
        t = threading.Thread(target=thread_download, args=(i, assigned_peer), daemon=True)
        threads.append(t)

    # Start threads
    for t in threads:
        t.start()

    # Wait for all threads to finish
    for t in threads:
        t.join()

    # 8. Retry failed chunks
    retry_attempts = 3
    for attempt in range(retry_attempts):
        if not failed_chunks:
            break  # All chunks downloaded
        tqdm.write(f"[Client] Retrying {len(failed_chunks)} failed chunks (Attempt {attempt + 1}/{retry_attempts})...")

        retry_threads = []
        for chunk_index in failed_chunks[:]:
            assigned_peer = available_peers[(chunk_index + attempt) % num_peers]

            t = threading.Thread(
                target=thread_download,
                args=(chunk_index, assigned_peer),
                daemon=True
            )
            retry_threads.append(t)

        # Start retry threads
        for t in retry_threads:
            t.start()

        # Wait for all retry threads
        for t in retry_threads:
            t.join()

    progress_bar.close()  # Close the progress bar when done

    if failed_chunks:
        tqdm.write(f"[Client] Download incomplete. Missing chunks: {failed_chunks}")
        return

    # 9. Combine chunks into a single file
    local_path = os.path.join(P2P_FOLDER, filename)
    with open(local_path, 'wb') as out_f:
        for i in range(total_chunks):
            part_path = os.path.join(chunk_dir, f"{i}.part")
            if os.path.exists(part_path):
                with open(part_path, 'rb') as p_f:
                    out_f.write(p_f.read())
                os.remove(part_path)

    # Clean up chunk directory
    try:
        os.rmdir(chunk_dir)
    except OSError:
        pass

    #print(f"[Client] Successfully downloaded '{filename}' to '{local_path}'.")

def main():
    parser = argparse.ArgumentParser(description="P2P Client with Tracker (Parallel Downloads)")
    parser.add_argument('--port', type=int, required=True, help="Port to listen on.")
    args = parser.parse_args()
    port = args.port

    # Ensure the p2p folder exists
    if not os.path.exists(P2P_FOLDER):
        os.makedirs(P2P_FOLDER)

    # Start server thread (Seeder)
    t_server = threading.Thread(target=server_thread, args=(port,), daemon=True)
    t_server.start()

    # Register with the tracker
    my_address = f"127.0.0.1:{port}"
    peers = register_with_tracker(my_address)

    # Command-line interface for the client
    print("[CLI] Commands:")
    print("  LIST                  -> List all known peers")
    print("  PEERS                 -> Refresh and list all known peers (excluding self)")
    print("  FILES                 -> List files in p2p folder")
    print("  GET <filename>        -> Download file from peers in parallel")
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
                # Refresh peer list before download
                peers = get_peers_from_tracker()
                # Exclude self
                active_peers = [p for p in peers if p != my_address]
                if not active_peers:
                    print("[Client] No other peers available.")
                    continue
                parallel_download(filename, active_peers)

            elif cmd == "EXIT":
                print("[CLI] Exiting...")
                break

            else:
                print("[CLI] Unknown command.")
        except KeyboardInterrupt:
            print("\n[CLI] Exiting...")
            break
        except Exception as e:
            print(f"[CLI] Error: {e}")


if __name__ == "__main__":
    main()
