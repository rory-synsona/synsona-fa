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
    requests = []
    current_index = start_index
    
    # Split text into paragraphs
    paragraphs = text.split('\n')
    processed_text = ''
    style_ranges = []
    list_items = []
    link_ranges = []
    bold_ranges = []  # Initialize bold_ranges list
    
    # First process the paragraphs
    for paragraph in paragraphs:
        paragraph = paragraph.rstrip()
        current_position = len(processed_text)
        
        if not paragraph:
            processed_text += '\n'
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
            continue
        
        # Regular paragraph
        processed_text += paragraph + '\n'
    
    # Process links and bold text
    final_text = processed_text
    text_length = len(final_text)
      # Initialize text positions - each position maps to its final position
    text_positions = list(range(text_length))
    print(f"\nStarting text processing with length: {text_length}")
    print(f"Current index: {current_index}")

    def validate_position(pos: int, context: str) -> bool:
        """Validate a text position is within bounds"""
        if pos < 0 or pos >= text_length:
            print(f"Warning: Position {pos} out of bounds [0, {text_length}) in {context}")
            return False
        return True
        
    def update_positions(start: int, text_removed: int, text_added: int, context: str) -> None:
        """Update position tracking after text modification"""
        nonlocal text_length, text_positions, final_text
        
        if not validate_position(start, context):
            return
            
        print(f"\nUpdating positions for {context}:")
        print(f"Start: {start}, Removed: {text_removed}, Added: {text_added}")
          # Update text length before calculating positions
        text_length = len(final_text)
        
        # Calculate net change in length
        delta = text_added - text_removed
        
        # Map each position to its new location
        updated_positions = []
        doc_length = text_length + current_index
        
        for pos in text_positions:
            if pos < start:
                # Keep positions before the edit point unchanged
                updated_positions.append(pos)
            else:
                # For positions after the edit point:
                # 1. Subtract start to make position relative to edit point
                # 2. Add delta to account for length change
                # 3. Add start back to make position absolute
                # 4. Ensure position stays within document bounds
                relative_pos = pos - start
                shifted_pos = relative_pos + delta
                new_pos = start + shifted_pos
                
                # Clamp to valid range
                new_pos = max(start, min(new_pos, doc_length))
                updated_positions.append(new_pos)
        
        # Update the text_positions array in place
        text_positions[:] = updated_positions
        
        print(f"Positions updated: text_length={text_length}, doc_length={doc_length}")
        print(f"Position range: {min(text_positions)} to {max(text_positions)}")

    # Collect all links first
    all_links = []
    for match in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', final_text):
        full_match = match.group(0)
        link_text = match.group(1)
        url = match.group(2)
        start_pos = match.start()
        end_pos = match.end()
        
        # Skip invalid positions
        if not validate_position(start_pos, f"link {link_text} start") or \
           not validate_position(end_pos - 1, f"link {link_text} end"):
            continue
        
        all_links.append((start_pos, end_pos, link_text, url))

    # Sort links in reverse order
    all_links.sort(reverse=True)
    print(f"\nCollected {len(all_links)} valid links")
    
    # Process links
    for start_pos, end_pos, link_text, url in all_links:
        try:
            # Process the link text
            text_before = final_text[:start_pos]
            text_after = final_text[end_pos:]
            final_text = text_before + link_text + text_after
            
            # Update text length after modification
            text_length = len(final_text)
            
            print(f"\nProcessing link: {link_text}")
            print(f"URL: {url}")
            print(f"Original position: {start_pos} to {end_pos}")
            
            # Track position changes just once
            chars_removed = end_pos - start_pos
            chars_added = len(link_text)
            update_positions(start_pos, chars_removed, chars_added, f"link {link_text}")
            
            # Calculate final position using mapped position
            final_start = text_positions[start_pos]
            final_end = final_start + len(link_text)
            
            # Validate final positions are within document bounds
            if final_start >= 0 and final_end <= text_length:
                print(f"Final text position: {final_start} to {final_end}")
                link_ranges.append((final_start, final_end, url))
                print(f"Stored link range: {final_start} to {final_end}")
            else:
                print(f"Warning: Link position out of bounds: {final_start} to {final_end}")
                
        except IndexError as e:
            print(f"Warning: Invalid position while processing link {link_text}: {str(e)}")
            continue
            
    # Process bold text with similar validation
    bold_matches = []
    for match in re.finditer(r'\*\*(.*?)\*\*', final_text):
        start_pos = match.start()
        end_pos = match.end()
        content = match.group(1)
        
        if not validate_position(start_pos, f"bold {content} start") or \
           not validate_position(end_pos - 1, f"bold {content} end"):
            continue
            
        bold_matches.append((start_pos, end_pos, content))

    bold_matches.sort(reverse=True)
    print(f"\nCollected {len(bold_matches)} valid bold matches")    # Process bold text
    for start_pos, end_pos, content in bold_matches:
        try:
            # Update the text first
            text_before = final_text[:start_pos]
            text_after = final_text[end_pos:]
            final_text = text_before + content + text_after
            
            # Update text length after modification
            text_length = len(final_text)
            
            print(f"\nProcessing bold text: {content}")
            
            # Track position changes and update tracking
            chars_removed = end_pos - start_pos
            chars_added = len(content)
            update_positions(start_pos, chars_removed, chars_added, f"bold text {content}")
            
            # Calculate final positions using mapped position
            final_start = text_positions[start_pos]
            final_end = final_start + len(content)
            
            # Validate final positions are within document bounds
            if final_start >= 0 and final_end <= text_length:
                print(f"Final text position: {final_start} to {final_end}")
                bold_ranges.append((final_start, final_end))
                print(f"Stored bold range: {final_start} to {final_end}")
            else:
                print(f"Warning: Bold position out of bounds: {final_start} to {final_end}")
                
        except IndexError as e:
            print(f"Warning: Invalid position while processing bold text {content}: {str(e)}")
            continue
    
    print(f"\nFinal text length: {text_length}")
      # Insert the processed text first
    if final_text:
        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': final_text
            }
        })
        
        # Calculate document positions based on final text length
        final_doc_length = current_index + len(final_text)
        
        # Apply link formatting
        for text_start, text_end, url in link_ranges:
            # Convert and validate text positions to document positions
            doc_start = min(current_index + text_start, final_doc_length)
            doc_end = min(current_index + text_end, final_doc_length)
            
            # Skip invalid ranges
            if doc_start >= doc_end or doc_end > final_doc_length:
                print(f"Skipping invalid link range: {doc_start} to {doc_end}")
                continue
            
            print(f"Applying link at document range: ({doc_start}, {doc_end}), URL={url}")
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': doc_start,
                        'endIndex': doc_end
                    },
                    'textStyle': {
                        'link': {
                            'url': url
                        }
                    },
                    'fields': 'link'
                }
            })
          # Apply bold formatting
        for text_start, text_end in bold_ranges:
            # Convert and validate text positions to document positions
            doc_start = min(current_index + text_start, final_doc_length)
            doc_end = min(current_index + text_end, final_doc_length)
            
            # Skip invalid ranges
            if doc_start >= doc_end or doc_end > final_doc_length:
                print(f"Skipping invalid bold range: {doc_start} to {doc_end}")
                continue
                
            print(f"Applying bold at document range: ({doc_start}, {doc_end})")
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': doc_start,
                        'endIndex': doc_end
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
            # Insert title with proper spacing
            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': f"{title}\n\n"  # Add extra newline for better spacing
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
            
            current_index += len(title) + 2  # +2 for the two newlines
            
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
