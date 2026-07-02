from fastapi import Request, HTTPException
import bcrypt
import hashlib

# Active tokens in memory
ACTIVE_TOKENS = {}

def hash_pin(pin: str) -> str:
    # Use secure salted bcrypt
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pin.encode('utf-8'), salt).decode('utf-8')

def verify_pin(pin: str, hashed: str) -> bool:
    # Support verifying both legacy SHA-256 (64 hex characters) and bcrypt hashes
    if len(hashed) == 64 and all(c in "0123456789abcdefABCDEF" for c in hashed):
        legacy_hash = hashlib.sha256(pin.encode('utf-8')).hexdigest()
        return legacy_hash.lower() == hashed.lower()
    try:
        return bcrypt.checkpw(pin.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def get_current_user(request: Request):
    token = request.cookies.get("auth_token")
    if not token or token not in ACTIVE_TOKENS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return ACTIVE_TOKENS[token]
