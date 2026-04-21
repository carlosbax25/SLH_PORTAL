"""Tracking de demandas usando Google Sheets como almacenamiento persistente."""
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET_ID = "1nVUwtQeNyNTdXyUuy2qvn_Nlt6UHJda-c2xf__ETqpo"
TRACKING_SHEET = "TRACKING"  # Name of the tracking sheet/tab
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_credentials():
    creds_path = os.path.join(BASE_DIR, "credentials.json")
    if os.path.exists(creds_path):
        return service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    return None


def _get_sheets_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("sheets", "v4", credentials=creds)


def _ensure_tracking_sheet():
    """Crea la hoja TRACKING si no existe."""
    service = _get_sheets_service()
    if not service:
        return False
    try:
        meta = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if TRACKING_SHEET not in sheets:
            service.spreadsheets().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={
                    "requests": [
                        {"addSheet": {"properties": {"title": TRACKING_SHEET}}}
                    ]
                },
            ).execute()
            # Add headers
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"{TRACKING_SHEET}!A1:I1",
                valueInputOption="RAW",
                body={
                    "values": [[
                        "CEDULA", "PROPIETARIO", "CONJUNTO", "FILENAME",
                        "GENERATED_AT", "MORA", "DRIVE_ID", "DRIVE_LINK", "DATA_JSON"
                    ]]
                },
            ).execute()
        return True
    except Exception as e:
        print(f"Error ensuring tracking sheet: {e}")
        return False


def load_tracking() -> dict:
    """Carga todo el tracking desde Google Sheets."""
    service = _get_sheets_service()
    if not service:
        return {}
    try:
        _ensure_tracking_sheet()
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{TRACKING_SHEET}!A2:I5000",
        ).execute()
        rows = result.get("values", [])
        tracking = {}
        for row in rows:
            if len(row) >= 8:
                cedula = row[0]
                data_json = row[8] if len(row) > 8 else "{}"
                extra = {}
                try:
                    extra = json.loads(data_json)
                except Exception:
                    pass
                tracking[cedula] = {
                    "propietario": row[1],
                    "conjunto": row[2],
                    "filename": row[3],
                    "generated_at": row[4],
                    "mora": row[5],
                    "drive_id": row[6],
                    "drive_link": row[7],
                    "hechos": extra.get("hechos", []),
                    "pretensiones": extra.get("pretensiones", []),
                    "medida_cautelar": extra.get("medida_cautelar", ""),
                }
        return tracking
    except Exception as e:
        print(f"Error loading tracking: {e}")
        return {}


def save_tracking_entry(cedula: str, data: dict):
    """Guarda o actualiza una entrada en el tracking de Google Sheets."""
    service = _get_sheets_service()
    if not service:
        return
    try:
        _ensure_tracking_sheet()
        extra = json.dumps({
            "hechos": data.get("hechos", []),
            "pretensiones": data.get("pretensiones", []),
            "medida_cautelar": data.get("medida_cautelar", ""),
        }, ensure_ascii=False)

        new_row = [
            cedula,
            data.get("propietario", ""),
            data.get("conjunto", ""),
            data.get("filename", ""),
            data.get("generated_at", ""),
            data.get("mora", ""),
            data.get("drive_id", ""),
            data.get("drive_link", ""),
            extra,
        ]

        # Check if cedula already exists to update
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"{TRACKING_SHEET}!A2:A5000",
        ).execute()
        rows = result.get("values", [])
        row_idx = None
        for i, row in enumerate(rows):
            if row and row[0] == cedula:
                row_idx = i + 2  # +2 because A2 is row 2
                break

        if row_idx:
            # Update existing row
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"{TRACKING_SHEET}!A{row_idx}:I{row_idx}",
                valueInputOption="RAW",
                body={"values": [new_row]},
            ).execute()
        else:
            # Append new row
            service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range=f"{TRACKING_SHEET}!A:I",
                valueInputOption="RAW",
                body={"values": [new_row]},
            ).execute()
    except Exception as e:
        print(f"Error saving tracking: {e}")
