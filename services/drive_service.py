"""Servicio para subir archivos a Google Drive."""
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER_ID = "1Bt4tE6qttIKuUv-iSwz5RRpNFfhQIiqE"
SCOPES = ["https://www.googleapis.com/auth/drive.file",
          "https://www.googleapis.com/auth/spreadsheets"]


def _get_credentials():
    """Carga credenciales desde archivo o variable de entorno."""
    creds_path = os.path.join(BASE_DIR, "credentials.json")
    if os.path.exists(creds_path):
        return service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
    # For Render: credentials from env var
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    return None


def _get_drive_service():
    creds = _get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


def upload_to_drive(filepath: str, filename: str) -> str | None:
    """
    Sube un archivo a Google Drive.
    Retorna el ID del archivo en Drive, o None si falla.
    """
    service = _get_drive_service()
    if not service:
        return None

    file_metadata = {
        "name": filename,
        "parents": [FOLDER_ID],
    }
    media = MediaFileUpload(
        filepath,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    try:
        file = service.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()
        return file.get("id")
    except Exception as e:
        print(f"Error uploading to Drive: {e}")
        return None


def get_drive_link(file_id: str) -> str:
    """Retorna el link de visualización de un archivo en Drive."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def delete_from_drive(file_id: str) -> bool:
    """Elimina un archivo de Google Drive."""
    service = _get_drive_service()
    if not service:
        return False
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception:
        return False
