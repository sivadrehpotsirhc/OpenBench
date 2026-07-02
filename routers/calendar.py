"""
routers/calendar.py
Calendar sync routes.
"""
from fastapi import APIRouter, HTTPException, Request
from services.calendar_service import push_to_google_calendar
from plugins.repair_tickets.db import db_get_ticket, db_save_cal_event_id
from google_auth_oauthlib.flow import Flow
from config import CREDENTIALS_PATH, TOKEN_PATH
import os
from services.calendar_service import SCOPES

router = APIRouter()

@router.post("/sync/{ticket_id}")
def sync_ticket(ticket_id: str):
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    try:
        result = push_to_google_calendar(ticket)
    except ValueError as ve:
        raise HTTPException(status_code=401, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync to calendar: {e}")
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to sync to calendar")
    
    db_save_cal_event_id(ticket_id, result["event_id"])
    return result

@router.get("/auth-url")
def get_auth_url(request: Request):
    if not os.path.exists(CREDENTIALS_PATH):
        raise HTTPException(status_code=404, detail="credentials.json not found. Please upload credentials.json.")
    
    redirect_uri = f"{request.url.scheme}://{request.url.netloc}/api/calendar/callback"
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return {"auth_url": auth_url}

@router.get("/callback")
def calendar_callback(request: Request, code: str):
    redirect_uri = f"{request.url.scheme}://{request.url.netloc}/api/calendar/callback"
    flow = Flow.from_client_secrets_file(
        CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    flow.fetch_token(code=code)
    
    creds = flow.credentials
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
        
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content="""
        <html>
            <head>
                <title>Authentication Successful</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f7f9fa; }
                    .card { background: white; padding: 30px; border-radius: 8px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                    h1 { color: #2ecc71; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>Google Calendar Connected!</h1>
                    <p>You can close this tab and return to the application.</p>
                    <script>
                        setTimeout(function() { window.close(); }, 3000);
                    </script>
                </div>
            </body>
        </html>
    """)
