"""Tracking de demandas usando Google Sheets API via HTTP directo (sin google-api-python-client)."""
import os
import json
import urllib.request
import urllib.parse
from google.oauth2 import service_account
import google.auth.transport.requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET_ID = "1nVUwtQeNyNTdXyUuy2qvn_Nlt6UHJda-c2xf__ETqpo"
TRACKING_SHEET = "TRACKING"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_URL = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"


def _get_token():
    """Obtiene un access token usando las credenciales."""
    creds_path = os.path.join(BASE_DIR, "credentials.json")
    creds = None
    if os.path.exists(creds_path):
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES)
    else:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS")
        if creds_json:
            info = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES)
    if not creds:
        return None
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _api_request(method, path, body=None):
    """Hace una request HTTP directa a la Sheets API."""
    token = _get_token()
    if not token:
        return None
    url = f"{BASE_URL}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Sheets API error: {e}")
        return None


def _ensure_tracking_sheet():
    """Crea la hoja TRACKING si no existe."""
    result = _api_request("GET", "?fields=sheets.properties.title")
    if not result:
        return False
    sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
    if TRACKING_SHEET in sheets:
        return True
    _api_request("POST", ":batchUpdate", {
        "requests": [{"addSheet": {"properties": {"title": TRACKING_SHEET}}}]
    })
    rng = urllib.parse.quote(f"{TRACKING_SHEET}!A1:I1")
    _api_request("PUT",
        f"values/{rng}?valueInputOption=RAW",
        {"values": [["CEDULA", "PROPIETARIO", "CONJUNTO", "FILENAME",
                      "GENERATED_AT", "MORA", "DRIVE_ID", "DRIVE_LINK", "DATA_JSON"]]}
    )
    return True


def load_tracking() -> dict:
    """Carga todo el tracking desde Google Sheets."""
    try:
        _ensure_tracking_sheet()
        rng = urllib.parse.quote(f"{TRACKING_SHEET}!A2:I5000")
        result = _api_request("GET", f"values/{rng}")
        if not result:
            return {}
        rows = result.get("values", [])
        tracking = {}
        for row in rows:
            if len(row) >= 6:
                row_id = row[0]
                extra = {}
                if len(row) > 8:
                    try:
                        extra = json.loads(row[8])
                    except Exception:
                        pass
                tracking[row_id] = {
                    "propietario": row[1] if len(row) > 1 else "",
                    "conjunto": row[2] if len(row) > 2 else "",
                    "filename": row[3] if len(row) > 3 else "",
                    "generated_at": row[4] if len(row) > 4 else "",
                    "mora": row[5] if len(row) > 5 else "",
                    "drive_id": row[6] if len(row) > 6 else "",
                    "drive_link": row[7] if len(row) > 7 else "",
                    "hechos": extra.get("hechos", []),
                    "pretensiones": extra.get("pretensiones", []),
                    "medida_cautelar": extra.get("medida_cautelar", ""),
                }
        return tracking
    except Exception as e:
        print(f"Error loading tracking: {e}")
        return {}


def save_tracking_entry(row_id: str, data: dict):
    """Guarda o actualiza una entrada en el tracking."""
    try:
        _ensure_tracking_sheet()
        extra = json.dumps({
            "hechos": data.get("hechos", []),
            "pretensiones": data.get("pretensiones", []),
            "medida_cautelar": data.get("medida_cautelar", ""),
        }, ensure_ascii=False)
        new_row = [
            row_id, data.get("propietario", ""),
            data.get("conjunto", ""), data.get("filename", ""),
            data.get("generated_at", ""), data.get("mora", ""),
            data.get("drive_id", ""), data.get("drive_link", ""), extra,
        ]
        # Check if exists
        rng = urllib.parse.quote(f"{TRACKING_SHEET}!A2:A5000")
        result = _api_request("GET", f"values/{rng}")
        rows = result.get("values", []) if result else []
        row_idx = None
        for i, r in enumerate(rows):
            if r and r[0] == row_id:
                row_idx = i + 2
                break
        if row_idx:
            rng = urllib.parse.quote(f"{TRACKING_SHEET}!A{row_idx}:I{row_idx}")
            _api_request("PUT", f"values/{rng}?valueInputOption=RAW",
                         {"values": [new_row]})
        else:
            rng = urllib.parse.quote(f"{TRACKING_SHEET}!A:I")
            _api_request("POST",
                f"values/{rng}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
                {"values": [new_row]})
    except Exception as e:
        print(f"Error saving tracking: {e}")
