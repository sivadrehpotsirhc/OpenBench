import os
import uuid
import datetime
import bcrypt
import sqlite3
import html
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Form, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from core.db import get_conn
from plugins.software_repo.db import session_is_alive

router = APIRouter()

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(PLUGIN_DIR, "tools_library")
os.makedirs(LIBRARY_DIR, exist_ok=True)

# Helper to render the HTML Login page
def render_login_page(error_msg: str = None):
    error_html = ""
    if error_msg:
        escaped_error = html.escape(error_msg)
        error_html = f"""
        <div class="bg-red-950/40 border border-red-800/80 text-red-200 px-4 py-3 rounded-xl relative mb-6 text-xs font-medium" role="alert">
            <span class="block sm:inline">{escaped_error}</span>
        </div>
        """
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Software Repository - Guest Portal</title>
        <script src="/static/js/tailwind.js"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="/static/css/app.css">
        <style>
            body {{
                font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
                background-color: var(--bg);
                color: var(--text);
            }}
            .font-mono {{
                font-family: 'IBM Plex Mono', monospace;
            }}
            .login-card {{
                background: rgba(var(--surface-rgb), 0.92);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border: 1px solid var(--border2);
                border-radius: 8px;
            }}
        </style>
    </head>
    <body class="flex items-center justify-center min-h-screen relative overflow-hidden px-4">
        <!-- Ambient forge glow -->
        <div class="absolute w-[500px] h-[500px] rounded-full bg-[rgba(249,115,22,0.04)] blur-[120px] top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>

        <div class="w-full max-w-md p-8 login-card relative z-10">
            <div class="text-center mb-8">
                <!-- App logo placeholder matching OpenBench -->
                <div class="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-[var(--ember-glow)] border border-[rgba(249,115,22,0.25)] text-[var(--accent-hot)] mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-6 h-6">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                </div>
                <h1 class="text-2xl font-bold tracking-tight text-[var(--text)]">OpenBench</h1>
                <p class="text-xs text-[var(--textdim)] mt-1.5 uppercase tracking-wider font-semibold font-mono">Software Portal</p>
            </div>
            
            {error_html}
            
            <form action="/tools/auth" method="POST" class="space-y-5">
                <div class="space-y-2">
                    <label for="token" class="block text-xs font-semibold text-[var(--textdim)] uppercase tracking-wider">Session Token</label>
                    <input type="text" name="token" id="token" placeholder="00000000-0000-0000-0000-000000000000" required 
                           class="w-full px-4 py-2.5 bg-[var(--bg)] border border-[var(--border)] rounded-lg text-[var(--text)] placeholder-[var(--muted)] text-sm focus:outline-none focus:border-[var(--blue)] focus:ring-2 focus:ring-[var(--blue-glow)] transition duration-150">
                </div>
                <div class="space-y-2">
                    <label for="pin" class="block text-xs font-semibold text-[var(--textdim)] uppercase tracking-wider">6-Digit PIN</label>
                    <input type="password" name="pin" id="pin" placeholder="••••••" required maxlength="6"
                           class="w-full px-4 py-2.5 bg-[var(--bg)] border border-[var(--border)] rounded-lg text-[var(--text)] placeholder-[var(--muted)] tracking-widest text-sm focus:outline-none focus:border-[var(--blue)] focus:ring-2 focus:ring-[var(--blue-glow)] transition duration-150 text-center font-bold">
                </div>
                <button type="submit"
                        class="w-full py-3 bg-[var(--accent-deep)] hover:bg-[var(--accent)] border border-[var(--accent-deep)] rounded-lg font-mono lowercase font-medium text-[var(--bg)] transition-all duration-150 active:scale-[0.99]">
                    connect to library
                </button>
            </form>
        </div>
    </body>
    </html>
    """

# Helper to render the library page
def render_library_page(grouped_tools: dict):
    categories_html = ""
    if not grouped_tools:
        categories_html = """
        <div class="empty-state bg-[var(--surface)] border border-[var(--border)] rounded-lg">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 mx-auto text-[var(--muted)] mb-4">
                <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
            </svg>
            <p class="text-[var(--text)] text-lg font-semibold">No tools available</p>
            <p class="text-[var(--textdim)] text-sm mt-1">Ask the technician to add software to the library.</p>
        </div>
        """
    else:
        for cat_name, tools in grouped_tools.items():
            tools_list_html = ""
            for tool in tools:
                escaped_name = html.escape(tool["name"])
                escaped_desc = html.escape(tool["description"] or "No description provided.")
                escaped_ver = html.escape(tool["version"] or "1.0")
                escaped_size = html.escape(str(tool["file_size_kb"]))
                portable_badge = '<span class="px-2 py-0.5 bg-[var(--ember-glow)] border border-[var(--accent-deep)] text-[var(--accent-hot)] rounded-md text-[10px] font-mono font-medium lowercase tracking-wider">portable</span>' if tool["is_portable"] else ''
                tools_list_html += f"""
                <div class="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 flex flex-col justify-between hover:border-[var(--accent-deep)] transition duration-150">
                    <div>
                        <div class="flex items-start justify-between gap-3 mb-2">
                            <h3 class="text-base font-bold text-[var(--text)]">{escaped_name}</h3>
                            {portable_badge}
                        </div>
                        <p class="text-[var(--textdim)] text-xs leading-relaxed mb-4 line-clamp-3">{escaped_desc}</p>
                    </div>
                    <div class="border-t border-[var(--border)] pt-4 flex items-center justify-between text-xs text-[var(--textdim)]">
                        <div class="flex items-center gap-1.5 font-mono tdim">
                            <span class="bg-[var(--surface2)] px-1.5 py-0.5 rounded-md text-[var(--text)]">v{escaped_ver}</span>
                            <span>•</span>
                            <span>{escaped_size} KB</span>
                        </div>
                        <a href="/tools/download/{tool["id"]}"
                           class="px-4 py-2 bg-[var(--accent-deep)] hover:bg-[var(--accent)] border border-[var(--accent-deep)] text-[var(--bg)] font-mono lowercase font-medium rounded-lg transition duration-150 text-xs">
                            download
                        </a>
                    </div>
                </div>
                """
            
            categories_html += f"""
            <div class="mb-10">
                <div class="flex items-center gap-3 mb-4 border-b border-[var(--border)] pb-2">
                    <span class="w-1.5 h-6 bg-[var(--accent)] rounded-full"></span>
                    <h2 class="text-lg font-bold text-[var(--text)] tracking-tight">{html.escape(cat_name)}</h2>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {tools_list_html}
                </div>
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Software Portal - Library</title>
        <script src="/static/js/tailwind.js"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="/static/css/app.css">
        <style>
            body {{
                font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
                background-color: var(--bg);
                color: var(--text);
            }}
            .font-mono {{
                font-family: 'IBM Plex Mono', monospace;
            }}
        </style>
    </head>
    <body class="min-h-screen flex flex-col relative overflow-hidden">
        <!-- Ambient forge glow -->
        <div class="absolute w-[600px] h-[600px] rounded-full bg-[rgba(249,115,22,0.03)] blur-[130px] -top-40 -left-40 pointer-events-none"></div>

        <header class="bg-[var(--surface)] border-b border-[var(--border)] py-4 px-6 flex justify-between items-center relative z-10">
            <div class="flex items-center gap-3">
                <div class="flex items-center justify-center w-8 h-8 rounded-lg bg-[var(--ember-glow)] border border-[rgba(249,115,22,0.25)] text-[var(--accent-hot)]">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-4 h-4">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                </div>
                <div class="flex flex-col">
                    <h1 class="text-sm font-bold text-[var(--text)] tracking-tight leading-none">OpenBench</h1>
                    <span class="text-[10px] text-[var(--textdim)] font-semibold font-mono tracking-wider mt-0.5 uppercase">Software Library</span>
                </div>
            </div>
            <form action="/tools/logout" method="POST">
                <button type="submit" class="px-4 py-2 bg-[var(--surface)] border border-[var(--border2)] text-[var(--text)] rounded-lg hover:bg-[var(--surface2)] hover:border-[var(--accent-deep)] text-xs font-mono lowercase font-medium transition duration-150 active:scale-[0.98]">
                    disconnect
                </button>
            </form>
        </header>
        
        <main class="flex-grow max-w-7xl w-full mx-auto px-6 py-10 relative z-10">
            {categories_html}
        </main>
        
        <footer class="bg-[var(--surface)]/30 border-t border-[var(--border)]/40 py-6 text-center text-xs text-[var(--textdim)] relative z-10 font-medium">
            &copy; {datetime.datetime.now().year} OpenBench. For authorized shop and customer use only.
        </footer>
    </body>
    </html>
    """

# --- Routes ---

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def serve_login(request: Request):
    return HTMLResponse(content=render_login_page(), status_code=200)

@router.post("/auth")
def authenticate_guest(
    token: str = Form(...),
    pin: str = Form(...),
):
    generic_error = "Invalid Token or PIN"

    # Input validation
    try:
        uuid.UUID(token)
    except ValueError:
        return HTMLResponse(content=render_login_page(generic_error), status_code=401)

    if len(pin) != 6 or not pin.isdigit():
        return HTMLResponse(content=render_login_page(generic_error), status_code=401)

    # Database credential checks
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as con:
        row = con.execute("""
            SELECT pin_hash, expires_at, revoked
            FROM tool_sessions
            WHERE id = ?
        """, (token,)).fetchone()
        
        if not row:
            return HTMLResponse(content=render_login_page(generic_error), status_code=401)
        
        if row["revoked"] or row["expires_at"] <= now:
            return HTMLResponse(content=render_login_page(generic_error), status_code=401)
            
        pin_hash = row["pin_hash"]
        
        # Verify PIN
        try:
            if not bcrypt.checkpw(pin.encode('utf-8'), pin_hash.encode('utf-8')):
                return HTMLResponse(content=render_login_page(generic_error), status_code=401)
        except Exception:
            return HTMLResponse(content=render_login_page(generic_error), status_code=401)

        # Update last_used
        con.execute("""
            UPDATE tool_sessions
            SET last_used = ?
            WHERE id = ?
        """, (now, token))

    # Successful authentication
    response = RedirectResponse(url="/tools/library", status_code=303)
    response.set_cookie(
        key="tools_session",
        value=token,
        path="/tools",
        httponly=True,
        samesite="strict"
    )
    return response

@router.post("/logout")
def logout_guest():
    response = RedirectResponse(url="/tools", status_code=303)
    response.set_cookie(
        key="tools_session",
        value="",
        path="/tools",
        httponly=True,
        samesite="strict",
        max_age=-1,
        expires="Thu, 01 Jan 1970 00:00:00 GMT"
    )
    return response

@router.get("/library", response_class=HTMLResponse)
def serve_library(tools_session: Optional[str] = Cookie(None)):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if not tools_session or not session_is_alive(tools_session):
        return RedirectResponse(url="/tools", status_code=303)

    with get_conn() as con:
        rows = con.execute("""
            SELECT t.id, t.name, t.description, t.version, t.filename, t.file_size_kb, t.is_portable,
                   c.name as category_name, c.icon as category_icon
            FROM tools t
            INNER JOIN tool_categories c ON t.category_id = c.id
            WHERE t.is_active = 1
            ORDER BY c.sort_order ASC, t.name ASC
        """).fetchall()

    # Group by category name (e.g. "🔬 Diagnostics")
    grouped = {}
    for r in rows:
        cat = f"{r['category_icon'] or ''} {r['category_name']}".strip()
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(dict(r))

    return HTMLResponse(content=render_library_page(grouped), status_code=200)

@router.get("/download/{tool_id}")
def download_tool(
    tool_id: int,
    request: Request,
    tools_session: Optional[str] = Cookie(None)
):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if not tools_session or not session_is_alive(tools_session):
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_conn() as con:
        # Check active tool exists
        row = con.execute("""
            SELECT filename, is_active
            FROM tools
            WHERE id = ?
        """, (tool_id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        if not row["is_active"]:
            raise HTTPException(status_code=404, detail="Tool is inactive")
            
        filename = row["filename"]

        # Safe Path Traversal Check
        # Resolve path to prevent directory traversal
        target_path = os.path.abspath(os.path.join(LIBRARY_DIR, filename))
        print("DEBUG: LIBRARY_DIR =", LIBRARY_DIR)
        print("DEBUG: Target Path =", target_path)
        print("DEBUG: Exists =", os.path.exists(target_path))
        lib_abs = os.path.abspath(LIBRARY_DIR)
        if os.path.commonpath([lib_abs, target_path]) != lib_abs:
            raise HTTPException(status_code=400, detail="Invalid path traversal attempt")

        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="File missing on disk")

        # Capture Client IP and record download audit
        client_ip = request.client.host if request.client else "unknown"
        # Standardize for testclient
        if client_ip == "testclient":
            client_ip = "testclient"
            
        con.execute("""
            INSERT INTO tool_downloads (session_id, tool_id, client_ip)
            VALUES (?, ?, ?)
        """, (tools_session, tool_id, client_ip))

    return FileResponse(target_path, media_type="application/octet-stream", filename=filename)
