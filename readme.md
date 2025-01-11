# P2P File Sharing Application

A simple Peer-to-Peer (P2P) file sharing application written in Python. The application allows decentralized file sharing between peers, supports parallel downloads, and provides fault tolerance by retrying failed chunk downloads from other peers.

## Features

- **File Discovery**: Automatically queries peers to check who has a requested file.
- **Parallel Downloads**: Downloads file chunks in parallel from multiple peers.
- **File Chunking**: Downloads files in chunks and reassembles them upon completion.
- **Tracker Integration**: Tracks and manages active peers for efficient file sharing.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/J0R0W/TNAS-P2P
   cd TNAS-P2P
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Starting the Tracker

The tracker manages the list of active peers. Start the tracker first:
```bash
python tracker.py
```
The tracker will run on `http://127.0.0.1:8080` by default.

### Starting a Peer

Each peer hosts files for sharing and can request files from other peers. To start a peer:
```bash
python client.py --port <port>
```
Replace `<port>` with the desired port number (e.g., 5000).

### Adding Files to Share

To share files, place them in the `p2p` folder within the peer's directory. These files will automatically be available for other peers to download. **Only files in the `p2p` folder are used by the application for sharing or downloading.**

### Downloading a File

1. Use the `GET` command to request a file from the network:
   ```bash
   > GET <filename>
   ```
   Replace `<filename>` with the name of the file you want to download (e.g., `example.txt`).

2. The application will:
   - Query peers to check who has the file.
   - Download the file in chunks from the available peers.
   - Retry failed chunk downloads from other peers if necessary.

## Example Workflow

1. Start the tracker:
   ```bash
   python tracker.py
   ```

2. Start Peer 1 on port 5000 and add files to its `p2p` folder:
   ```bash
   python client.py --port 5000
   ```

3. Start Peer 2 on port 5001:
   ```bash
   python client.py --port 5001
   ```

4. From Peer 2, request a file available in Peer 1's `p2p` folder:
   ```bash
   > GET example.txt
   ```

5. Peer 2 downloads `example.txt` in chunks from Peer 1, displaying a progress bar during the download.

## Requirements

The application requires Python 3.7 or higher and the dependencies listed in `requirements.txt`. To install the dependencies:
```bash
pip install -r requirements.txt
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

