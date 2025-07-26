from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel
from typing import Dict
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import base64
from dotenv import load_dotenv
from drive_utils import build_strict_folder_path

# Load environment variables
load_dotenv()

# Create APIRouter instance
router = APIRouter()

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class FileTemplateRequest(BaseModel):
    file_title: str
    file_extension: str
    step_id: str
    folder_name: str
    text_content: str
    customer_id: str
    campaign_id: str
    wf_id: str
    wf_group_id: str

def get_or_create_nested_folder(drive_service, parent_id, folder_names):
    current_parent = parent_id
    for name in folder_names:
        query = (
            f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{current_parent}' in parents and trashed = false"
        )
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        items = results.get('files', [])
        if items:
            current_parent = items[0]['id']
        else:
            metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [current_parent]
            }
            folder = drive_service.files().create(body=metadata).execute()
            current_parent = folder.get('id')
    return current_parent

def get_google_creds():
    try:
        required_env_vars = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET"
        ]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        is_railway = bool(os.getenv('RAILWAY_PROD'))
        if os.getenv("GOOGLE_REFRESH_TOKEN"):
            try:
                creds_info = {
                    "refresh_token": os.getenv("GOOGLE_REFRESH_TOKEN"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "scopes": SCOPES
                }
                creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
                from google.auth.transport.requests import Request
                request = Request()
                creds.refresh(request)
                return creds
            except Exception as e:
                print(f"Error refreshing token: {str(e)}")
                if is_railway:
                    raise
        if is_railway:
            raise ValueError("No valid refresh token found and interactive OAuth not possible on Railway")
        import tempfile
        import json
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            json.dump({
                "installed": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "redirect_uris": ["http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }, temp_file)
            temp_path = temp_file.name
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(temp_path, SCOPES)
            creds = flow.run_local_server(port=0)
            print("\nNew credentials generated. Update your .env and Railway variables with:")
            print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
            return creds
        finally:
            os.unlink(temp_path)
    except Exception as e:
        raise Exception(f"Failed to obtain valid credentials: {str(e)}")
    return creds

def get_mime_type(file_extension: str) -> str:
    # Basic mapping, can be extended
    mapping = {
        'txt': 'text/plain',
        'md': 'text/markdown',
        'csv': 'text/csv',
        'json': 'application/json',
        'html': 'text/html',
        'xml': 'application/xml',
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    }
    return mapping.get(file_extension.lower(), 'application/octet-stream')

async def generate_file_from_template(request_data: FileTemplateRequest, http_request: FastAPIRequest) -> dict:
    try:
        import urllib.parse
        creds = get_google_creds()
        drive_service = build('drive', 'v3', credentials=creds)

        # Always start from Synsona Export
        export_query = "name = 'Synsona Export' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        export_results = drive_service.files().list(
            q=export_query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        export_items = export_results.get('files', [])
        if not export_items:
            export_metadata = {
                'name': 'Synsona Export',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            export_folder = drive_service.files().create(body=export_metadata).execute()
            export_folder_id = export_folder.get('id')
        else:
            export_folder_id = export_items[0].get('id')

        # Build the strict folder path using shared utility
        folder_path = build_strict_folder_path(request_data)
        folder_id = get_or_create_nested_folder(drive_service, export_folder_id, folder_path)

        file_name = f"{request_data.file_title}.{request_data.file_extension}"
        mime_type = get_mime_type(request_data.file_extension)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }   
        # Decode the URL-encoded text_content before saving (handles both %XX and +)
        decoded_text_content = urllib.parse.unquote_plus(request_data.text_content)
        media = MediaInMemoryUpload(decoded_text_content.encode('utf-8'), mimetype=mime_type, resumable=False)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        file_id = file.get('id')
        web_view_link = file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"
        # Update sharing permissions to anyone with the link can view
        drive_service.permissions().create(
            fileId=file_id,
            body={
                'type': 'anyone',
                'role': 'reader'
            }
        ).execute()
        return {
            "status": "success",
            "file_title": file_name,
            "file_id": file_id,
            "file_url": web_view_link,
            "step_id": request_data.step_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating file: {str(e)}")


# Register endpoint with APIRouter
@router.post("/generate-file-from-template")
async def generate_file_from_template_endpoint(request_data: FileTemplateRequest, http_request: FastAPIRequest):
    return await generate_file_from_template(request_data, http_request)
