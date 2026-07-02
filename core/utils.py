from datetime import datetime, date, timedelta

def _parse_date(s):
    if not s or s == "—":
        return None
    for fmt in ("%a, %b %d %Y", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            pass
    return None

def fmt_date(d):
    return d.strftime("%a, %b %d %Y") if d else "—"

def add_biz_days(n: int):
    if n is None:
        return None
    d, count = date.today(), 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d

def safe_float(val, default=0.0):
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return default
