from fastapi import APIRouter, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel
import os
import httpx
from dotenv import load_dotenv

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
                return response.json()
    except Exception as e:
        import traceback
        print("[Placid Debug] Exception in generate_image_from_template:", str(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating image: {str(e)}")
