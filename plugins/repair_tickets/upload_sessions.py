import time
import uuid
import threading
from typing import Dict, Any

# In-memory store for upload sessions
# Format: { "token": { "ticket_id": str, "expires_at": float, "received": bool, "count": int } }
_sessions: Dict[str, Dict[str, Any]] = {}
_sessions_lock = threading.Lock()

SESSION_TTL = 15 * 60  # 15 minutes

def create_session(ticket_id: str) -> str:
    # Cleanup expired sessions first
    cleanup_sessions()
    
    token = str(uuid.uuid4())
    with _sessions_lock:
        _sessions[token] = {
            "ticket_id": ticket_id,
            "expires_at": time.time() + SESSION_TTL,
            "received": False,
            "count": 0
        }
    return token

def get_session(token: str) -> Dict[str, Any]:
    with _sessions_lock:
        session = _sessions.get(token)
        if not session:
            return None
        if time.time() > session["expires_at"]:
            del _sessions[token]
            return None
        return session

def mark_received(token: str):
    with _sessions_lock:
        if token in _sessions:
            _sessions[token]["received"] = True
            _sessions[token]["count"] += 1

def cleanup_sessions():
    now = time.time()
    with _sessions_lock:
        expired = [k for k, v in _sessions.items() if now > v["expires_at"]]
        for k in expired:
            del _sessions[k]

def clear_sessions_for_ticket(ticket_id: str):
    with _sessions_lock:
        to_delete = [k for k, v in _sessions.items() if v["ticket_id"] == ticket_id]
        for k in to_delete:
            del _sessions[k]
