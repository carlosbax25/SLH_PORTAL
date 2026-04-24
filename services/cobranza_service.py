"""Servicio de tracking para notificaciones de cobranza PRE JURIDICA."""
import json
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from services.sheets_tracking import _api_request

COL_TZ = timezone(timedelta(hours=-5))
COBRANZA_SHEET = "COBRANZA_TRACKING"

# Cache
_cobranza_cache = {"data": None, "time": 0}
_COBRANZA_CACHE_TTL = 120  # 2 minutes

_cobranza_cache = {"data": None, "time": 0}
CACHE_TTL = 120  # 2 minutes


def _ensure_cobranza_sheet():
    result = _api_request("GET", "?fields=sheets.properties.title")
    if not result:
        return
    sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
    if COBRANZA_SHEET in sheets:
        return
    _api_request("POST", ":batchUpdate", {
        "requests": [{"addSheet": {"properties": {"title": COBRANZA_SHEET}}}]
    })
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A1:G1")
    _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {
        "values": [["ROW_ID", "PROPIETARIO", "CONJUNTO", "NOTIF1_DATE",
                     "NOTIF1_EMAIL", "NOTIF2_DATE", "NOTIF2_EMAIL"]]
    })


def load_cobranza_tracking() -> dict:
    now = time.time()
    if _cobranza_cache["data"] is not None and (now - _cobranza_cache["time"]) < _COBRANZA_CACHE_TTL:
        return _cobranza_cache["data"]
    _ensure_cobranza_sheet()
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A2:G5000")
    result = _api_request("GET", f"values/{rng}")
    if not result:
        return {}
    tracking = {}
    for row in result.get("values", []):
        if row:
            row_id = row[0]
            tracking[row_id] = {
                "propietario": row[1] if len(row) > 1 else "",
                "conjunto": row[2] if len(row) > 2 else "",
                "notif1_date": row[3] if len(row) > 3 else "",
                "notif1_email": row[4] if len(row) > 4 else "",
                "notif2_date": row[5] if len(row) > 5 else "",
                "notif2_email": row[6] if len(row) > 6 else "",
            }
    _cobranza_cache["data"] = tracking
    _cobranza_cache["time"] = now
    return tracking


def save_notification(row_id: str, notif_num: int, data: dict):
    """Guarda una notificación enviada (1 o 2)."""
    _cobranza_cache["data"] = None  # Invalidate cache
    _ensure_cobranza_sheet()
    now = datetime.now(COL_TZ).isoformat()

    # Check if exists
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A2:A5000")
    result = _api_request("GET", f"values/{rng}")
    rows = result.get("values", []) if result else []
    row_idx = None
    for i, r in enumerate(rows):
        if r and r[0] == row_id:
            row_idx = i + 2
            break

    if row_idx:
        # Update existing row
        existing = _api_request("GET",
            f"values/{urllib.parse.quote(f'{COBRANZA_SHEET}!A{row_idx}:G{row_idx}')}")
        vals = existing.get("values", [[]])[0] if existing else []
        while len(vals) < 7:
            vals.append("")
        if notif_num == 1:
            vals[3] = now
            vals[4] = data.get("email", "")
        else:
            vals[5] = now
            vals[6] = data.get("email", "")
        rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A{row_idx}:G{row_idx}")
        _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {"values": [vals]})
    else:
        new_row = [
            row_id, data.get("propietario", ""), data.get("conjunto", ""),
            now if notif_num == 1 else "",
            data.get("email", "") if notif_num == 1 else "",
            now if notif_num == 2 else "",
            data.get("email", "") if notif_num == 2 else "",
        ]
        rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A:G")
        _api_request("POST",
            f"values/{rng}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            {"values": [new_row]})


def get_notification_status(row_id: str) -> dict:
    """Retorna el estado de notificaciones para un propietario."""
    tracking = load_cobranza_tracking()
    return tracking.get(row_id, {})


def can_send_notif2(row_id: str) -> bool:
    """Verifica si han pasado 15 días desde la notificación 1."""
    info = get_notification_status(row_id)
    notif1 = info.get("notif1_date", "")
    if not notif1:
        return False
    try:
        d1 = datetime.fromisoformat(notif1)
        now = datetime.now(COL_TZ)
        return (now - d1).days >= 10
    except Exception:
        return False


def days_until_notif2(row_id: str) -> int:
    """Retorna días restantes para poder enviar notificación 2. 0 = ya se puede."""
    info = get_notification_status(row_id)
    notif1 = info.get("notif1_date", "")
    if not notif1:
        return -1
    try:
        d1 = datetime.fromisoformat(notif1)
        now = datetime.now(COL_TZ)
        elapsed = (now - d1).days
        remaining = 10 - elapsed
        return max(0, remaining)
    except Exception:
        return -1
