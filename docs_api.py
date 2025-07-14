from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Tuple
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import json
import tempfile
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# Create APIRouter instance
router = APIRouter()

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class DocsRequest(BaseModel):
    response_values: Dict[str, str]  # JSON of "title": "content"
    document_title: str
    step_id: str
    folder_name: str

def get_google_creds():
    try:
        required_env_vars = [
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET"
        ]
        
        # Check if all required environment variables are present
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")        # Check if we're running on Railway
        is_railway = bool(os.getenv('RAILWAY_PROD'))
        
        # Try to create credentials from refresh token if available
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
                
                # Force a token refresh to validate the credentials
                request = Request()
                creds.refresh(request)
                return creds
            except Exception as e:
                print(f"Error refreshing token: {str(e)}")
                if is_railway:
                    raise  # On Railway, we can't do interactive OAuth
                # In development, continue to new OAuth flow
        
        if is_railway:
            raise ValueError("No valid refresh token found and interactive OAuth not possible on Railway")
            
        # If we get here, we need to get new credentials via OAuth flow
        # Create a temporary credentials file for OAuth flow
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
            flow = InstalledAppFlow.from_client_secrets_file(temp_path, SCOPES)
            creds = flow.run_local_server(port=0)
            print("\nNew credentials generated. Update your .env and Railway variables with:")
            print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
            return creds
        finally:
            os.unlink(temp_path)  # Clean up the temporary file
            
    except Exception as e:
        raise Exception(f"Failed to obtain valid credentials: {str(e)}")
        
    return creds

def convert_markdown_to_docs_requests(text: str, start_index: int) -> Tuple[List[dict], int]:
    requests = []
    current_index = start_index
    print("\n=== Starting Markdown Conversion ===")
    print(f"Initial text length: {len(text)}")
    print(f"Start index: {start_index}")
    
    # First collect ALL formatting locations
    formats = []
    
    # Find headers (store full line ranges)
    for match in re.finditer(r'^(#{1,6})\s+(.+?)(?:\s*#*\s*)?$', text, re.MULTILINE):
        formats.append({
            'type': 'header',
            'start': match.start(),
            'end': match.end(),
            'level': len(match.group(1)),
            'text': match.group(2).strip()
        })
        print(f"Found header: '{match.group(2).strip()}' at {match.start()}-{match.end()}")
    
    # Find bold text
    for match in re.finditer(r'\*\*(.*?)\*\*', text):
        formats.append({
            'type': 'bold',
            'start': match.start(),
            'end': match.end(),
            'text': match.group(1)
        })
        print(f"Found bold: '{match.group(1)}' at {match.start()}-{match.end()}")
    
    # Find links
    for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        formats.append({
            'type': 'link',
            'start': match.start(),
            'end': match.end(),
            'text': match.group(1),
            'url': match.group(2)
        })
        print(f"Found link: '{match.group(1)}' -> '{match.group(2)}' at {match.start()}-{match.end()}")
    
    # Sort formats from last to first
    formats.sort(key=lambda x: x['start'], reverse=True)
    print(f"\nFound {len(formats)} format regions")
    
    # Build a list of text segments and their formatting
    segments = []
    last_pos = len(text)
    
    print("\n=== Processing Text ===")
    # Work backwards through the text
    for fmt in formats:
        # Add the text between this format and the last one
        if fmt['end'] < last_pos:
            segments.insert(0, {
                'text': text[fmt['end']:last_pos],
                'format': None
            })
        
        # Add this formatted segment
        segments.insert(0, {
            'text': fmt['text'],
            'format': fmt
        })
        last_pos = fmt['start']
    
    # Add any remaining text at the start
    if last_pos > 0:
        segments.insert(0, {
            'text': text[0:last_pos],
            'format': None
        })
    
    # Now build the document requests
    clean_text = ''
    format_ranges = []
    current_pos = current_index
    
    print("\n=== Building Document ===")
    for segment in segments:
        # Add this segment's text
        text_start = len(clean_text)
        clean_text += segment['text']
        text_end = len(clean_text)
        
        # Record formatting if any
        if segment['format']:
            fmt = segment['format']
            doc_start = current_index + text_start
            doc_end = current_index + text_end
            
            print(f"Text: '{segment['text']}'")
            print(f"Format: {fmt['type']} at {doc_start}-{doc_end}")
            
            format_ranges.append({
                'type': fmt['type'],
                'start': doc_start,
                'end': doc_end,
                'level': fmt.get('level'),
                'url': fmt.get('url')
            })
    
    # Insert the clean text
    print(f"\n=== Inserting Clean Text ===")
    print(f"Final text length: {len(clean_text)}")
    requests.append({
        'insertText': {
            'location': {'index': current_index},
            'text': clean_text
        }
    })
    
    # Apply all formatting
    print("\n=== Applying Formatting ===")
    for fmt in format_ranges:
        try:
            print(f"Applying {fmt['type']} at {fmt['start']}-{fmt['end']}")
            
            if fmt['type'] == 'header':
                style_type = f'HEADING_{fmt["level"]}'
                requests.append({
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': fmt['start'],
                            'endIndex': fmt['end']
                        },
                        'paragraphStyle': {
                            'namedStyleType': style_type
                        },
                        'fields': 'namedStyleType'
                    }
                })
            elif fmt['type'] == 'bold':
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': fmt['start'],
                            'endIndex': fmt['end']
                        },
                        'textStyle': {
                            'bold': True
                        },
                        'fields': 'bold'
                    }
                })
            elif fmt['type'] == 'link':
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': fmt['start'],
                            'endIndex': fmt['end']
                        },
                        'textStyle': {
                            'link': {
                                'url': fmt['url']
                            }
                        },
                        'fields': 'link'
                    }
                })
        except Exception as e:
            print(f"ERROR processing {fmt['type']}: {str(e)}")
            continue
    
    final_index = current_index + len(clean_text)
    print(f"\n=== Conversion Complete ===")
    print(f"Start index: {current_index}, Final index: {final_index}")
    print("==========================\n")
    return requests, final_index

# Add formatting requests based on stored ranges
def apply_formatting_requests(requests: List[dict], text: str, style_ranges: List[dict], current_index: int) -> None:
    for style_range in style_ranges:
        # Validate heading
        if style_range['type'].startswith('HEADING_'):
            # Ensure header range is at paragraph start
            if not style_range.get('is_paragraph_start', False):
                continue
                
            # Validate header text
            header_text = text[style_range['start']:style_range['end']].strip()
            if header_text != style_range['text']:
                continue
                
            # Apply paragraph style
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': style_range['start'] + current_index,
                        'endIndex': style_range['end'] + current_index
                    },
                    'paragraphStyle': {
                        'namedStyleType': style_range['type']
                    },
                    'fields': 'namedStyleType'
                }
            })

    # ...existing code for other formatting...

from fastapi import Request as FastAPIRequest

async def generate_docs(request_data: DocsRequest, http_request: FastAPIRequest) -> dict:

    try:
        creds = get_google_creds()
        # Create Drive API service
        drive_service = build('drive', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)

        # Check if folder exists anywhere in Drive, if not create it
        folder_query = f"name = '{request_data.folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        folder_results = drive_service.files().list(
            q=folder_query,
            spaces='drive',
            fields='files(id, name, parents)'
        ).execute()
        folder_items = folder_results.get('files', [])

        if not folder_items:
            # Check if 'Synsona Export' folder exists in root
            export_query = "name = 'Synsona Export' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            export_results = drive_service.files().list(
                q=export_query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            export_items = export_results.get('files', [])

            if not export_items:
                # Create 'Synsona Export' folder in root
                export_metadata = {
                    'name': 'Synsona Export',
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                export_folder = drive_service.files().create(body=export_metadata).execute()
                export_folder_id = export_folder.get('id')
            else:
                export_folder_id = export_items[0].get('id')

            # Create new folder inside Synsona Export folder
            folder_metadata = {
                'name': request_data.folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [export_folder_id]
            }
            folder = drive_service.files().create(body=folder_metadata).execute()
            folder_id = folder.get('id')
        else:
            folder_id = folder_items[0].get('id')

        # Create a new Google Doc in the folder
        doc_metadata = {
            'name': request_data.document_title,
            'mimeType': 'application/vnd.google-apps.document',
            'parents': [folder_id]
        }
        doc = drive_service.files().create(body=doc_metadata).execute()

        # Get the document ID
        document_id = doc.get('id')
        # Build requests for document content
        requests = []
        current_index = 1

        for title, content in request_data.response_values.items():
            # Insert title with proper spacing
            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': f"{title}\n"  # Single newline for less spacing
                }
            })

            # Apply TITLE style (instead of HEADING_1)
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': current_index,
                        'endIndex': current_index + len(title)
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'TITLE'
                    },
                    'fields': 'namedStyleType'
                }
            })

            current_index += len(title) + 1  # +1 for the single newline
            # Add a paragraph break before content to avoid section break issues
            if current_index > 1:  # Skip for first section
                requests.append({
                    'insertText': {
                        'location': {'index': current_index},
                        'text': '\n'
                    }
                })
                current_index += 1

            # Convert markdown content and get its requests
            content_requests, new_index = convert_markdown_to_docs_requests(content, current_index)
            requests.extend(content_requests)

            # Add newlines after content
            requests.append({
                'insertText': {
                    'location': {'index': new_index},
                    'text': "\n\n"
                }
            })

            current_index = new_index + 2

        # Update the document content
        docs_service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()

        # Get the web view link for the document
        web_view_link = f"https://docs.google.com/document/d/{document_id}/edit"

        # Update sharing permissions to anyone with the link can view
        drive_service.permissions().create(
            fileId=document_id,
            body={
                'type': 'anyone',
                'role': 'reader'
            }
        ).execute()

        return {
            "status": "success",
            "document_title": request_data.document_title,
            "document_id": document_id,
            "document_url": web_view_link,
            "step_id": request_data.step_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating document: {str(e)}")


# Register endpoint with APIRouter
from fastapi import Request as FastAPIRequest
@router.post("/generate-docs")
async def generate_docs_endpoint(request_data: DocsRequest, http_request: FastAPIRequest):
    return await generate_docs(request_data, http_request)
