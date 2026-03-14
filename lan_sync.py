"""
utils/lan_sync.py
──────────────────
Federated LAN Sync — Disaster Command Center v4 ELITE

Syncs incidents between command laptops over local area network.
Uses TCP sockets on port 5555. No internet required.

Protocol messages:
    SYNC_REQUEST     — request full incident list from peer
    SYNC_RESPONSE    — send full incident list to peer
    INCIDENT_UPDATE  — push single incident update
    HEARTBEAT        — keepalive / node discovery

Conflict resolution: last_write_wins (by updated_at timestamp)
"""

import os
import sys
import json
import time
import socket
import threading
import uuid
from typing import Dict, List, Optional, Callable, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCIDENTS_FILE = os.path.join(BASE_DIR, "data", "incident_table.json")
SYNC_LOG_FILE = os.path.join(BASE_DIR, "logs", "sync_log.json")

# ── Configuration ──
SYNC_PORT = 5555
BUFFER_SIZE = 65536  # 64KB per message
SOCKET_TIMEOUT = 3.0
HEARTBEAT_INTERVAL = 30  # seconds
MAX_MESSAGE_SIZE = 1024 * 512  # 512KB

# ── Node identity ──
_node_id = str(uuid.uuid4())[:8].upper()

# ── Server state ──
_server_thread: Optional[threading.Thread] = None
_server_running = False
_connected_peers: Dict[str, Dict] = {}  # peer_id → {ip, last_seen}
_sync_callbacks: List[Callable] = []


def _load_incidents() -> List[Dict]:
    """Load local incidents from disk."""
    try:
        if os.path.exists(INCIDENTS_FILE):
            with open(INCIDENTS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_incidents(incidents: List[Dict]) -> None:
    """Save incident list to disk."""
    try:
        os.makedirs(os.path.dirname(INCIDENTS_FILE), exist_ok=True)
        with open(INCIDENTS_FILE, "w") as f:
            json.dump(incidents, f, indent=2, default=str)
    except Exception:
        pass


def _log_sync(event_type: str, peer_ip: str = "", details: str = "") -> None:
    """Append sync event to log file."""
    try:
        os.makedirs(os.path.dirname(SYNC_LOG_FILE), exist_ok=True)
        logs = []
        if os.path.exists(SYNC_LOG_FILE):
            with open(SYNC_LOG_FILE, "r") as f:
                logs = json.load(f)
        logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "node_id": _node_id,
            "event": event_type,
            "peer_ip": peer_ip,
            "details": details,
        })
        if len(logs) > 500:
            logs = logs[-500:]
        with open(SYNC_LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


def _build_message(msg_type: str, payload: Dict) -> bytes:
    """Serialize a protocol message to bytes."""
    msg = {
        "type": msg_type,
        "node_id": _node_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "payload": payload,
    }
    return (json.dumps(msg) + "\n").encode("utf-8")


def _parse_message(raw: bytes) -> Optional[Dict]:
    """Parse received bytes into message dict."""
    try:
        text = raw.decode("utf-8").strip()
        return json.loads(text)
    except Exception:
        return None


def _merge_incidents(local: List[Dict], remote: List[Dict]) -> Tuple[List[Dict], int]:  # type: ignore
    """
    Merge remote incidents into local list using last_write_wins.

    Args:
        local: Local incident list
        remote: Remote incident list from peer

    Returns:
        (merged_list, new_or_updated_count)
    """
    from typing import Tuple
    local_map: Dict[str, Dict] = {inc.get("incident_id", ""): inc for inc in local}
    updated = 0

    for remote_inc in remote:
        rid = remote_inc.get("incident_id")
        if not rid:
            continue

        if rid not in local_map:
            # New incident from peer
            local_map[rid] = remote_inc
            updated += 1
        else:
            # Compare timestamps — last write wins
            local_ts = local_map[rid].get("updated_at", local_map[rid].get("created_at", ""))
            remote_ts = remote_inc.get("updated_at", remote_inc.get("created_at", ""))
            if remote_ts > local_ts:
                local_map[rid] = remote_inc
                updated += 1

    return list(local_map.values()), updated


def _handle_client(conn: socket.socket, addr: tuple) -> None:
    """Handle an incoming peer connection."""
    peer_ip = addr[0]
    try:
        conn.settimeout(SOCKET_TIMEOUT)
        raw = conn.recv(MAX_MESSAGE_SIZE)
        if not raw:
            return

        msg = _parse_message(raw)
        if not msg:
            return

        msg_type = msg.get("type")
        peer_node_id = msg.get("node_id", "UNKNOWN")
        payload = msg.get("payload", {})

        # Register peer
        _connected_peers[peer_node_id] = {
            "ip": peer_ip,
            "node_id": peer_node_id,
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        if msg_type == "SYNC_REQUEST":
            # Send our full incident list
            local_incidents = _load_incidents()
            response = _build_message("SYNC_RESPONSE", {"incidents": local_incidents})
            conn.sendall(response)
            _log_sync("SYNC_REQUEST_RECEIVED", peer_ip, f"Sent {len(local_incidents)} incidents")

        elif msg_type == "INCIDENT_UPDATE":
            # Merge single or multiple incidents
            incoming = payload.get("incidents", [])
            if "incident" in payload:
                incoming = [payload["incident"]]
            local = _load_incidents()
            merged, updated = _merge_incidents(local, incoming)
            _save_incidents(merged)
            # Notify callbacks
            for cb in _sync_callbacks:
                try:
                    cb({"type": "INCIDENT_UPDATE", "updated": updated, "peer_ip": peer_ip})
                except Exception:
                    pass
            _log_sync("INCIDENT_UPDATE_RECEIVED", peer_ip, f"Merged {updated} incident(s)")

        elif msg_type == "HEARTBEAT":
            # Reply with our heartbeat
            ack = _build_message("HEARTBEAT", {"status": "alive", "incident_count": len(_load_incidents())})
            conn.sendall(ack)
            _log_sync("HEARTBEAT", peer_ip, "")

    except socket.timeout:
        pass
    except Exception as e:
        _log_sync("ERROR", peer_ip, str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _server_loop() -> None:
    """TCP server main loop — listens for peer connections."""
    global _server_running
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", SYNC_PORT))
        server_sock.listen(10)
        server_sock.settimeout(1.0)

        _log_sync("SERVER_STARTED", "", f"Listening on port {SYNC_PORT}")

        while _server_running:
            try:
                conn, addr = server_sock.accept()
                t = threading.Thread(target=_handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                break

        server_sock.close()
    except Exception as e:
        _log_sync("SERVER_ERROR", "", str(e))
    finally:
        _server_running = False


def start_sync_server() -> Dict:
    """
    Start the LAN sync server in a background thread.

    Returns:
        Dict with success status and node_id
    """
    global _server_thread, _server_running

    if _server_running:
        return {"success": True, "already_running": True, "node_id": _node_id}

    _server_running = True
    _server_thread = threading.Thread(target=_server_loop, daemon=True)
    _server_thread.start()

    return {
        "success": True,
        "node_id": _node_id,
        "port": SYNC_PORT,
        "status": "Server started",
    }


def stop_sync_server() -> None:
    """Stop the LAN sync server."""
    global _server_running
    _server_running = False


def sync_with_peer(peer_ip: str, port: int = SYNC_PORT) -> Dict:
    """
    Connect to a peer and synchronize incidents.

    Args:
        peer_ip: IP address of the peer node
        port: TCP port (default 5555)

    Returns:
        Dict with sync results
    """
    try:
        # Request peer's incidents
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((peer_ip, port))

        request = _build_message("SYNC_REQUEST", {})
        sock.sendall(request)

        # Receive response
        chunks = []
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        sock.close()

        raw_response = b"".join(chunks)
        response = _parse_message(raw_response)

        if not response or response.get("type") != "SYNC_RESPONSE":
            return {"success": False, "error": "Invalid sync response from peer"}

        remote_incidents = response.get("payload", {}).get("incidents", [])
        local = _load_incidents()
        merged, updated = _merge_incidents(local, remote_incidents)
        _save_incidents(merged)

        # Register peer
        peer_node_id = response.get("node_id", "UNKNOWN")
        _connected_peers[peer_node_id] = {
            "ip": peer_ip,
            "node_id": peer_node_id,
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        _log_sync("SYNC_COMPLETED", peer_ip,
                  f"Remote: {len(remote_incidents)}, Updated: {updated}")

        return {
            "success": True,
            "peer_ip": peer_ip,
            "peer_node_id": peer_node_id,
            "remote_incidents": len(remote_incidents),
            "local_incidents_after": len(merged),
            "incidents_updated": updated,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    except ConnectionRefusedError:
        return {"success": False, "error": f"Peer {peer_ip}:{port} refused connection"}
    except socket.timeout:
        return {"success": False, "error": f"Connection to {peer_ip}:{port} timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def push_incident_to_peer(peer_ip: str, incident: Dict,
                            port: int = SYNC_PORT) -> Dict:
    """
    Push a single incident update to a specific peer.

    Args:
        peer_ip: Peer IP address
        incident: Incident dict to push
        port: TCP port

    Returns:
        Push result dict
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((peer_ip, port))
        msg = _build_message("INCIDENT_UPDATE", {"incidents": [incident]})
        sock.sendall(msg)
        sock.close()
        _log_sync("INCIDENT_PUSHED", peer_ip, incident.get("incident_id", "?"))
        return {"success": True, "peer_ip": peer_ip, "incident_id": incident.get("incident_id")}
    except Exception as e:
        return {"success": False, "error": str(e), "peer_ip": peer_ip}


def ping_peer(peer_ip: str, port: int = SYNC_PORT) -> Dict:
    """
    Send a heartbeat to check if a peer is online.

    Args:
        peer_ip: Peer IP address
        port: TCP port

    Returns:
        Dict with online status and peer info
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((peer_ip, port))
        msg = _build_message("HEARTBEAT", {})
        sock.sendall(msg)
        raw = sock.recv(BUFFER_SIZE)
        sock.close()

        response = _parse_message(raw)
        if response and response.get("type") == "HEARTBEAT":
            peer_payload = response.get("payload", {})
            return {
                "online": True,
                "peer_ip": peer_ip,
                "peer_node_id": response.get("node_id"),
                "peer_incident_count": peer_payload.get("incident_count", "?"),
                "latency_ms": "< 3000",
            }
        return {"online": False, "peer_ip": peer_ip, "error": "Invalid heartbeat response"}
    except Exception as e:
        return {"online": False, "peer_ip": peer_ip, "error": str(e)}


def register_sync_callback(callback: Callable) -> None:
    """Register a callback to be called when incidents are synced."""
    _sync_callbacks.append(callback)


def get_connected_peers() -> Dict[str, Dict]:
    """Return dict of known connected peers."""
    return dict(_connected_peers)


def get_sync_status() -> Dict:
    """Return current sync server status."""
    return {
        "node_id": _node_id,
        "server_running": _server_running,
        "port": SYNC_PORT,
        "connected_peers": len(_connected_peers),
        "peers": get_connected_peers(),
        "local_incidents": len(_load_incidents()),
    }


def get_sync_log(limit: int = 20) -> List[Dict]:
    """Return recent sync log entries."""
    try:
        if os.path.exists(SYNC_LOG_FILE):
            with open(SYNC_LOG_FILE, "r") as f:
                logs = json.load(f)
            return logs[-limit:]
    except Exception:
        pass
    return []



