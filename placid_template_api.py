from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel
import os
import httpx
from dotenv import load_dotenv
from drive_utils import build_strict_folder_path
from file_template_api import get_google_creds, get_or_create_nested_folder, get_mime_type
import tempfile
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load environment variables
load_dotenv()

PLACID_API_URL = "https://api.placid.app/api/rest/images"

router = APIRouter()

class PlacidTemplateRequest(BaseModel):
    file_title: str
    step_id: str
    folder_name: str
    customer_id: str
    campaign_id: str
    wf_id: str
    wf_group_id: str
    placid_template_id: str
    placid_layers_json: dict

async def placid_auth_headers():
    placid_api_token = os.getenv("PLACID_API_TOKEN")
    if not placid_api_token:
        raise HTTPException(status_code=500, detail="Placid API token not configured.")
    return {"Authorization": f"Bearer {placid_api_token}", "Content-Type": "application/json"}

@router.post("/generate-image-from-template")
async def generate_image_from_template(request_data: PlacidTemplateRequest, http_request: FastAPIRequest):
    import asyncio
    try:
        placid_callback_url = os.getenv("SYNSONA_PLACID_CALLBACK")
        payload = {
            "template_uuid": request_data.placid_template_id,
            "create_now": True,
            "passthrough": f"step_id={request_data.step_id}",
            "layers": request_data.placid_layers_json,
            "webhook_success": placid_callback_url
        }
        headers = await placid_auth_headers()
        print("[Placid Debug] Payload to Placid API:", payload)
        print("[Placid Debug] Headers to Placid API:", headers)
        max_retries = 20
        retry_count = 0
        timeout = httpx.Timeout(60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while retry_count < max_retries:
                print(f"[Placid Debug] POSTing to {PLACID_API_URL} (attempt {retry_count+1})")
                response = await client.post(PLACID_API_URL, json=payload, headers=headers)
                print("[Placid Debug] Response status:", response.status_code)
                print("[Placid Debug] Response text:", response.text)
                if response.status_code == 429:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise HTTPException(status_code=429, detail="Placid API rate limit reached after 20 retries.")
                    await asyncio.sleep(30)
                    continue
                elif response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=f"Placid API error: {response.text}")
                placid_json = response.json()
                placid_url = placid_json.get("url") or placid_json.get("image_url")
                if not placid_url:
                    raise HTTPException(status_code=500, detail="No image URL returned from Placid API.")

                # Download image to temp file
                img_response = requests.get(placid_url)
                if img_response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to download image from Placid.")
                tmp_file_path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_file.write(img_response.content)
                    tmp_file_path = tmp_file.name
                # At this point, the file is closed and can be safely uploaded and deleted

                # Upload to Google Drive
                creds = get_google_creds()
                drive_service = build('drive', 'v3', credentials=creds)
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

                folder_path = build_strict_folder_path(request_data)
                folder_id = get_or_create_nested_folder(drive_service, export_folder_id, folder_path)

                file_name = f"{request_data.file_title}.png"
                mime_type = get_mime_type("png")
                file_metadata = {
                    'name': file_name,
                    'parents': [folder_id]
                }
                media = MediaFileUpload(tmp_file_path, mimetype=mime_type, resumable=False)
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

                # Clean up temp file
                import time
                time.sleep(0.1)
                os.unlink(tmp_file_path)

                return {
                    "status": "success",
                    "file_title": file_name,
                    "file_id": file_id,
                    "file_url": web_view_link,
                    "step_id": request_data.step_id
                }
    except Exception as e:
        import traceback
        print("[Placid Debug] Exception in generate_image_from_template:", str(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")
