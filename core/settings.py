import json
from core.db import get_conn
from core.constants import REPAIR_DAYS, REPAIR_PRICE, DEVICE_TYPES

DEFAULT_SETTINGS = {
    "tax_rate": "0.0",
    "tax_label": "Tax",
    "currency_symbol": "$",
    "shop_name": "OpenBench",
    "shop_tagline": "IT Service Center",
    "shop_phone": "",
    "shop_email": "contact@openbench.com",
    "shop_address": "",
    "ticket_modules": json.dumps([
        {"id": "customer", "name": "Customer", "enabled": True},
        {"id": "device", "name": "Device", "enabled": True},
        {"id": "repair", "name": "Repair", "enabled": True},
        {"id": "ticket_details", "name": "Ticket Details", "enabled": True},
        {"id": "checklist", "name": "Pre-Repair Checklist", "enabled": True},
        {"id": "legal", "name": "Authorizations & Legal", "enabled": True}
    ]),
    "ticket_repair_types": json.dumps([
        {"name": k, "days": REPAIR_DAYS.get(k, 0), "price": REPAIR_PRICE.get(k, 0)}
        for k in REPAIR_DAYS
    ]),
    "ticket_devices": json.dumps(DEVICE_TYPES),
    "ticket_techs": json.dumps([]),
    "ticket_checklist": json.dumps(["Power On", "WiFi", "Bluetooth", "Screen", "Battery", "Keyboard", "Touchpad/Mouse", "Sound", "Camera"]),
    "ticket_legal": json.dumps(["Customer confirmed data is backed up / Factory reset authorized", "Repair authorized (Service waiver signed)"]),
    "invoice_footer": "Thank you for your business!",
    "email_templates": json.dumps([
        {
            "id": "status_update",
            "name": "Status Update",
            "subject": "Repair Update: [TICKET_ID]",
            "body": "Hello [CUSTOMER_NAME],\n\nThis is an update regarding your repair ticket [TICKET_ID] ([DEVICE]).\n\nCurrent Status: [STATUS]\n\nNotes: \n\nPlease let us know if you have any questions.\n\nThank you,\nOpenBench"
        },
        {
            "id": "ready_pickup",
            "name": "Ready for Pickup",
            "subject": "Your Repair is Ready: [TICKET_ID]",
            "body": "Hello [CUSTOMER_NAME],\n\nGreat news! Your repair for [DEVICE] (Ticket [TICKET_ID]) is now complete and ready for pickup.\n\nTotal Due: [PRICE]\n\nPlease let us know when you plan to come by.\n\nThank you,\nOpenBench"
        },
        {
            "id": "invoice",
            "name": "Invoice",
            "subject": "Invoice for Repair: [TICKET_ID]",
            "body": "Hello [CUSTOMER_NAME],\n\nAttached is the invoice for your repair ticket [TICKET_ID].\n\nTotal: [PRICE]\n\nThank you for choosing OpenBench!"
        }
    ]),
    "backup_frequency": "daily",
    "backup_retention_days": "14",
    "backup_directory": "",
    "timezone": "America/Chicago",
    "time_format": "12h",
    "display_density": "comfortable"
}

def _init_settings():
    with get_conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        for k, v in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))

def get_setting(key: str, default=None):
    with get_conn() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

def get_all_settings():
    with get_conn() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

def set_setting(key: str, value: str):
    with get_conn() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def set_settings(settings: dict):
    with get_conn() as con:
        for k, v in settings.items():
            con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
