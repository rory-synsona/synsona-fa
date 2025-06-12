from fastapi import FastAPI, Request, HTTPException
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
    """
    Converts markdown text to Google Docs API requests and returns the requests along with the new cursor position.
    Supports:
    - Bold (**text**)
    - Links ([text](url))
    - Headers (# h1, ## h2, etc.)
    - Ordered lists (1. item)
    - Unordered lists (- item or * item)
    """
    requests = []
    current_index = start_index
    
    # Split text into paragraphs
    paragraphs = text.split('\n')
    processed_text = ''
    style_ranges = []
    list_items = []
    
    # Debug counters
    text_length = 0
    
    for paragraph in paragraphs:
        paragraph = paragraph.rstrip()
        current_position = len(processed_text)
        
        if not paragraph:
            processed_text += '\n'
            text_length = len(processed_text)
            continue
            
        # Handle headers
        header_match = re.match(r'^(#{1,6})\s+(.+)$', paragraph)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2)
            processed_text += header_text + '\n'
            style_ranges.append((
                current_position + current_index,
                current_position + len(header_text) + current_index,
                f'HEADING_{level}'
            ))
            text_length = len(processed_text)
            continue
            
        # Handle lists
        list_match = re.match(r'^(\s*)([-*]|\d+\.)\s+(.+)$', paragraph)
        if list_match:
            indent = len(list_match.group(1))
            list_type = 'NUMBERED_LIST' if list_match.group(2).endswith('.') else 'BULLET_LIST'
            content = list_match.group(3)
            
            # Calculate positions
            start_pos = len(processed_text) + current_index
            processed_text += content + '\n'
            end_pos = start_pos + len(content)  # Position before newline
              # Store range for formatting
            list_items.append((
                start_pos,
                start_pos + len(content),  # Don't include newline in range
                list_type,
                indent // 2
            ))
            text_length = len(processed_text)
            print(f"List item: content='{content}', range=({start_pos}, {start_pos + len(content)})")
            continue
        
        # Regular paragraph
        processed_text += paragraph + '\n'
        text_length = len(processed_text)
    
    # Process bold text
    final_text = processed_text
    bold_ranges = []
    text_offset = 0
    
    for match in re.finditer(r'\*\*(.*?)\*\*', processed_text):
        start, end = match.span()
        content = match.group(1)
        actual_start = start - text_offset
        bold_ranges.append((
            actual_start + current_index,
            actual_start + len(content) + current_index
        ))
        final_text = final_text[:actual_start] + content + final_text[actual_start + len(content) + 4:]
        text_offset += 4
    
    print(f"Final text length: {len(final_text)}")
    
    # Insert the processed text first
    if final_text:
        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': final_text
            }
        })
        
        # Apply bold formatting
        for start, end in bold_ranges:
            print(f"Bold range: ({start}, {end})")
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': start,
                        'endIndex': end
                    },
                    'textStyle': {
                        'bold': True
                    },
                    'fields': 'bold'
                }
            })
        
        # Apply header styles
        for start, end, style_type in style_ranges:
            print(f"Header range: ({start}, {end}), type={style_type}")
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start,
                        'endIndex': end
                    },
                    'paragraphStyle': {
                        'namedStyleType': style_type
                    },
                    'fields': 'namedStyleType'
                }
            })
            
        # Apply list styles
        for start, end, list_type, depth in list_items:
            print(f"List range: ({start}, {end}), type={list_type}, depth={depth}")
            
            # Find the next newline after the start of content
            next_newline = final_text.find('\n', start - current_index)
            if next_newline == -1:
                next_newline = len(final_text)
                
            # Adjust index to be document-relative
            next_newline += current_index
            
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start,
                        'endIndex': next_newline
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'NORMAL_TEXT',
                        'indentStart': {
                            'magnitude': depth * 36,
                            'unit': 'PT'
                        },
                        'indentFirstLine': {
                            'magnitude': depth * 36,
                            'unit': 'PT'
                        }
                    },
                    'fields': 'namedStyleType,indentStart,indentFirstLine'
                }
            })
            requests.append({
                'createParagraphBullets': {
                    'range': {
                        'startIndex': start,
                        'endIndex': next_newline
                    },
                    'bulletPreset': 'NUMBERED_DECIMAL_NESTED' if list_type == 'NUMBERED_LIST' else 'BULLET_DISC_CIRCLE_SQUARE'
                }
            })
    
    final_index = current_index + len(final_text)
    print(f"Start index: {current_index}, Final index: {final_index}")
    return requests, final_index

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
            # Insert title
            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': f"{title}\n"
                }
            })
            
            # Apply heading 1 style to title
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': current_index,
                        'endIndex': current_index + len(title) + 1
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'TITLE'
                    },
                    'fields': 'namedStyleType'
                }
            })
            
            current_index += len(title) + 1
            
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
