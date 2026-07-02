"""
services/calendar_service.py
Google Calendar API integration for repair tickets.
"""
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config import CREDENTIALS_PATH, TOKEN_PATH, CALENDAR_ID
from core.utils import _parse_date

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
            except Exception:
                raise ValueError("Google Calendar credentials expired and refresh failed. Please authenticate again.")
        else:
            raise ValueError("Google Calendar not authenticated. Please authenticate.")
    return build("calendar", "v3", credentials=creds)

def push_to_google_calendar(ticket: dict):
    """Create a new calendar event for a ticket."""
    try:
        due_date = _parse_date(ticket.get("due"))
        if not due_date:
            return None
        
        service = get_calendar_service()
        summary = f"[{ticket['id']}] {ticket.get('repair', 'Repair')} — {ticket.get('name', 'Unknown')}"
        description = (
            f" IT SERVICE TICKET\n{'─'*36}\n"
            f"Ticket #  : {ticket['id']}\nPriority  : {ticket.get('priority', 'Standard')}\n\n"
            f" CUSTOMER\nName : {ticket.get('name')}\nPhone: {ticket.get('phone')}\n"
            f"Email: {ticket.get('email') or '—'}\n\n"
            f" DEVICE\n{ticket.get('device') or '—'}\n\n"
            f" REPAIR\nType : {ticket.get('repair')}\nQuote: {ticket.get('price')}\n\n"
            f" ISSUE\n{ticket.get('issue') or '—'}\n"
        )
        if ticket.get("notes"):
            description += f"\n TECH NOTES\n{ticket['notes']}\n"
            
        event = {
            "summary": summary, "description": description,
            "start": {"date": due_date.isoformat()},
            "end":   {"date": due_date.isoformat()},
            "colorId": "11" if ticket.get("priority")=="Critical" else
                       "5"  if ticket.get("priority")=="Rush" else "1",
            "reminders": {"useDefault": False, "overrides": [
                {"method": "email",  "minutes": 24*60},
                {"method": "popup",  "minutes": 24*60},
                {"method": "popup",  "minutes": 2*60},
            ]},
        }
        
        if ticket.get("cal_event_id"):
            try:
                created = service.events().update(calendarId=CALENDAR_ID, eventId=ticket["cal_event_id"], body=event).execute()
            except Exception as e:
                print(f"Failed to update calendar event, falling back to insert: {e}")
                created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        else:
            created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            
        return {
            "event_id": created.get("id"),
            "html_link": created.get("htmlLink")
        }
    except ValueError as ve:
        raise ve
    except Exception as e:
        print(f"Calendar error: {e}")
        return None
