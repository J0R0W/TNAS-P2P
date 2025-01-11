import threading
import time
import socket
from flask import Flask, request, jsonify

app = Flask(__name__)

# Global list of active peers
peers = []
# Lock to protect concurrent access to `peers`
peers_lock = threading.Lock()


@app.route('/register', methods=['POST'])
def register_peer():
    """
    Registers a peer with the tracker.
    Expected payload: {"peer": "IP:PORT"}
    """
    data = request.json
    peer = data.get('peer', None)
    if peer:
        with peers_lock:
            if peer not in peers:
                peers.append(peer)
    return jsonify({"status": "ok", "peers": peers})


@app.route('/get_peers', methods=['GET'])
def get_peers():
    """
    Returns the list of active peers.
    """
    with peers_lock:
        current_peers = list(peers)
    return jsonify({"peers": current_peers})


def ping_peer(peer):
    """
    Tries to open a TCP connection to the peer.
    Returns True if successful, otherwise False.
    """
    try:
        host, port = peer.split(":")
        port = int(port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)  # 2 seconds timeout
            s.connect((host, port))
        return True
    except:
        return False


def peer_monitor_thread():
    """
    Periodically checks if peers are still alive.
    If a peer is not reachable, remove it from the list.
    """
    while True:
        time.sleep(60)  # Wait 60s between checks
        with peers_lock:
            to_remove = []
            for p in peers:
                if not ping_peer(p):
                    to_remove.append(p)
            # Remove dead peers
            for dead_peer in to_remove:
                print(f"[Tracker] Removing inactive peer: {dead_peer}")
                peers.remove(dead_peer)


if __name__ == "__main__":
    # Start background thread for periodic peer monitoring
    monitor = threading.Thread(target=peer_monitor_thread, daemon=True)
    monitor.start()

    # Run the tracker on port 8080
    app.run(host='0.0.0.0', port=8080)
