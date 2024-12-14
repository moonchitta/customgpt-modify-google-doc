import os
import time
import uuid
import threading
import json

import requests
from flask import Flask, request, jsonify, send_from_directory, Response, send_file
from urllib.parse import urlparse

# Google Drive imports
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import googleapiclient.http

# Slack imports
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Slack Bot Token from .env file
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN is not set in the .env file")

client = WebClient(token=SLACK_BOT_TOKEN)

# File paths and scopes
CLIENT_SECRET_FILE = 'client_secret.json'  # Path to your client_secret.json file
TOKEN_FILE = 'token.json'
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/contacts']

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Default voice ID

# Elevenlabs base url
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/"

# Folder to save generated audio files
OUTPUT_FOLDER = "audio_outputs"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)  # Ensure folder exists

# Folder to store temp files
OUTPUT_DIR = "scraped_pages"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global variables for scraping
tasks = {}
driver = None
selenium_initialized = False
selenium_error_message = None

# Google Drive Service
drive_service = None


@app.route('/privacy', methods=['GET'])
def privacy():
    """
    Returns the privacy policy text as an HTML page.
    """
    privacy_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                line-height: 1.6;
            }
            h1 {
                color: #333;
            }
        </style>
    </head>
    <body>
        <h1>Privacy Policy</h1>
        <p>
            This application uses Google APIs to perform its operations. The app accesses user data
            only as necessary to fulfill its functionality, such as creating Google Docs. No user data
            is shared or stored beyond what is required to execute the requested functionality.
        </p>
        <p>
            The app complies with Google's User Data Policy, including the Limited Use requirements.
        </p>
        <p>
            If you have any questions or concerns about your data privacy, please contact us.
        </p>
    </body>
    </html>
    """
    return privacy_html

@app.route('/list_channels', methods=['GET'])
def list_channels():
    """
    List all Slack channels.
    """
    try:
        response = client.conversations_list(types="public_channel,private_channel")
        channels = response.get("channels", [])
        return jsonify({"ok": True, "channels": [{"id": ch["id"], "name": ch["name"]} for ch in channels]})
    except SlackApiError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# Authentication flow (unchanged)
@app.route('/startAuth', methods=['GET'])
def start_auth():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'https://48c3-2407-d000-1a-8ad4-ad85-aa2a-1087-948e.ngrok-free.app/handleAuth'
    auth_url, _ = flow.authorization_url(prompt='consent')
    return jsonify({'auth_url': auth_url}), 200

@app.route('/handleAuth', methods=['GET'])
def handle_auth():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'https://48c3-2407-d000-1a-8ad4-ad85-aa2a-1087-948e.ngrok-free.app/handleAuth'
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)

    creds = flow.credentials
    with open(TOKEN_FILE, 'w') as token_file:
        token_file.write(creds.to_json())

    return jsonify({'message': 'Authentication successful!'}), 200

# List Google Docs-compatible files
@app.route('/listFiles', methods=['GET'])
def list_files():
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

        drive_service = build('drive', 'v3', credentials=creds)
        results = drive_service.files().list(
            pageSize=10,
            fields="files(id, name, mimeType)",
            q="mimeType='application/vnd.google-apps.document'"
        ).execute()
        files = results.get('files', [])

        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Read a Google Docs file
@app.route('/readDoc', methods=['GET'])
def read_doc():
    doc_id = request.args.get('document_id')

    if not doc_id:
        return jsonify({'error': 'Document ID is required'}), 400

    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

        docs_service = build('docs', 'v1', credentials=creds)

        # Retrieve the document content
        document = docs_service.documents().get(documentId=doc_id).execute()
        content = []
        for element in document.get('body', {}).get('content', []):
            if 'paragraph' in element:
                for text_run in element['paragraph'].get('elements', []):
                    if 'textRun' in text_run:
                        content.append(text_run['textRun']['content'])

        return jsonify({'content': ''.join(content)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Update Google Docs file
@app.route('/updateDoc', methods=['POST'])
def update_doc():
    """
    Updates a specific Google Docs file by adding content at a specified location.
    """
    data = request.json
    doc_id = data.get('document_id')
    content = data.get('content')
    location_index = data.get('location_index', 1)  # Default to the beginning of the document

    if not doc_id or not content:
        return jsonify({'error': 'Document ID and content are required'}), 400

    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

        docs_service = build('docs', 'v1', credentials=creds)

        # Request body to update the document
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': location_index,
                    },
                    'text': content,
                }
            }
        ]

        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

        return jsonify({'message': f'Content updated successfully in document: {doc_id}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def initialize_google_drive():
    """Initialize Google Drive API."""
    global drive_service
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            raise Exception("User not authenticated. Please authenticate at /startAuth")

        drive_service = build('drive', 'v3', credentials=creds)
        print("Google Drive service initialized.")
    except Exception as e:
        print(f"Failed to initialize Google Drive: {e}")

def initialize_selenium():
    """Initialize Selenium WebDriver."""
    global driver, selenium_initialized, selenium_error_message
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        print("Initializing Selenium WebDriver...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        selenium_initialized = True
        print("Selenium WebDriver is ready.")
    except Exception as e:
        selenium_initialized = False
        selenium_error_message = str(e)
        print(f"Failed to initialize Selenium: {selenium_error_message}")


def upload_to_google_drive(file_path, folder_id):
    """Upload a file to Google Drive."""
    try:
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = googleapiclient.http.MediaFileUpload(file_path, mimetype='text/html')
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()
        return uploaded_file.get('id'), uploaded_file.get('name')
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None, None


def create_google_drive_folder(folder_name, parent_folder_id=None):
    """Create a folder in Google Drive."""
    try:
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_folder_id:
            folder_metadata['parents'] = [parent_folder_id]

        folder = drive_service.files().create(
            body=folder_metadata,
            fields='id, name'
        ).execute()

        print(f"Folder '{folder_name}' created with ID: {folder.get('id')}")
        return folder.get('id')
    except Exception as e:
        print(f"Error creating folder in Google Drive: {e}")
        return None


def save_page(url, content, parent_folder_id):
    """Save HTML content directly to a sub-folder in Google Drive."""
    parsed_url = urlparse(url)
    filename = parsed_url.path.strip("/").replace("/", "_") or "index"
    filename = f"{filename}.html"

    temp_file_path = os.path.join(OUTPUT_DIR, filename)
    with open(temp_file_path, "wb") as file:
        file.write(content)

    # Upload file to Google Drive
    file_id, file_name = upload_to_google_drive(temp_file_path, parent_folder_id)
    os.remove(temp_file_path)  # Clean up the local temp file

    return file_id, file_name


def scrape_pages_with_selenium(task_id, base_url, max_pages, root_folder_id):
    """Scrape a website and upload pages to a Google Drive sub-folder."""
    global driver
    visited_urls = set()
    urls_to_visit = [base_url]
    pages_scraped = 0
    uploaded_files = []

    # Extract base domain to name the subfolder
    base_domain = urlparse(base_url).netloc.replace("www.", "")
    website_folder_id = create_google_drive_folder(base_domain, root_folder_id)

    if not website_folder_id:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = "Failed to create folder in Google Drive."
        return

    try:
        tasks[task_id]["status"] = "processing"
        while urls_to_visit:
            current_url = urls_to_visit.pop(0)
            if current_url in visited_urls:
                continue

            print(f"Scraping: {current_url}")
            driver.get(current_url)
            time.sleep(2)

            # Save the HTML file to Google Drive
            html_content = driver.page_source
            file_id, file_name = save_page(current_url, html_content.encode("utf-8"), website_folder_id)
            if file_id:
                uploaded_files.append(f"https://drive.google.com/file/d/{file_id}/view")
            visited_urls.add(current_url)
            pages_scraped += 1

            # Stop scraping if max_pages is reached
            if 0 < max_pages <= pages_scraped:
                break

            # Find links to follow
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href")
                if href and href.startswith(base_url) and href not in visited_urls:
                    urls_to_visit.append(href)

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["message"] = f"Scraped {pages_scraped} pages."
        tasks[task_id]["data"] = uploaded_files
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = str(e)
    finally:
        print(f"Task {task_id} completed.")

@app.route('/scrape', methods=['POST'])
def start_scraping():
    """Start scraping task."""
    if not selenium_initialized or not drive_service:
        return jsonify({"status": "error", "message": "Selenium or Google Drive not initialized"}), 500

    data = request.get_json()
    url = data.get("url")
    max_pages = int(data.get("max_pages", -1))
    folder_id = data.get("folder_id")

    if not url or not url.startswith("http") or not folder_id:
        return jsonify({"status": "error", "message": "Invalid input"}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "queued", "message": "Scraping task queued.", "data": None}

    threading.Thread(target=scrape_pages_with_selenium, args=(task_id, url, max_pages, folder_id)).start()

    return jsonify({"status": "success", "message": "Scraping task started.", "data": {"task_id": task_id}})


@app.route('/status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Check scraping task status."""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Invalid task ID"}), 404

    return jsonify({"status": task["status"], "message": task["message"], "data": task["data"]})


@app.route('/shareFileOnSlack', methods=['POST'])
def share_file_on_slack():
    """
    Share a Google Drive document on Slack by changing its permission to public.
    JSON Body: { "channel_id": "C12345678", "document_id": "DRIVE_DOCUMENT_ID", "comment": "Optional comment" }
    """
    data = request.json
    channel_id = data.get("channel_id")
    document_id = data.get("document_id")
    comment = data.get("comment", "")

    if not channel_id or not document_id:
        return jsonify({"ok": False, "error": "channel_id and document_id are required"}), 400

    try:
        # Authenticate and build the Google Drive service
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'ok': False, 'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

        drive_service = build('drive', 'v3', credentials=creds)

        # Change the file permission to public
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        drive_service.permissions().create(
            fileId=document_id,
            body=permission,
            fields='id'
        ).execute()

        # Get the public URL of the document
        public_url = f"https://drive.google.com/file/d/{document_id}/view"

        # Prepare the message for Slack
        message = f"{comment}\n{public_url}" if comment else public_url

        # Post the public URL to the specified Slack channel
        response = client.chat_postMessage(channel=channel_id, text=message)

        return jsonify({
            "ok": True,
            "message_id": response.get("ts"),
            "public_url": public_url,
            "message": "Google Drive file link shared successfully"
        })
    except SlackApiError as slack_error:
        return jsonify({"ok": False, "error": f"Slack error: {str(slack_error)}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": f"Google Drive error: {str(e)}"}), 500

@app.route('/shareFileAsAttachmentOnSlack', methods=['POST'])
def share_file_as_attachment_on_slack():
    """
    Downloads a Google Drive file in its original format and uploads it as an attachment to a Slack channel.
    JSON Body: { "channel_id": "C12345678", "document_id": "DRIVE_DOCUMENT_ID", "comment": "Optional comment" }
    """
    data = request.json
    channel_id = data.get("channel_id")
    document_id = data.get("document_id")
    comment = data.get("comment", "")

    if not channel_id or not document_id:
        return jsonify({"ok": False, "error": "channel_id and document_id are required"}), 400

    try:
        # Authenticate and build the Google Drive service
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'ok': False, 'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

        drive_service = build('drive', 'v3', credentials=creds)

        # Get file metadata (to fetch the file name)
        file_metadata = drive_service.files().get(fileId=document_id, fields="name").execute()
        file_name = file_metadata.get("name")

        # Download the file in its original format
        request_download = drive_service.files().get_media(fileId=document_id)
        file_path = f"/tmp/{file_name}"  # Temporary storage for the file

        with open(file_path, "wb") as file:
            downloader = googleapiclient.http.MediaIoBaseDownload(file, request_download)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        # Upload the file to Slack as an attachment
        with open(file_path, "rb") as file:
            response = client.files_upload(
                channels=channel_id,
                file=file,
                filename=file_name,
                initial_comment=comment
            )

        return jsonify({
            "ok": True,
            "file_id": response.get("file", {}).get("id"),
            "message": "File uploaded to Slack channel successfully."
        })
    except SlackApiError as slack_error:
        return jsonify({"ok": False, "error": f"Slack error: {str(slack_error)}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": f"Google Drive error: {str(e)}"}), 500

@app.route('/generate-audio', methods=['POST'])
def generate_audio():
    try:
        # Get text input from the request
        data = request.json
        text = data.get("text")

        if not text:
            return jsonify({"error": "No text provided"}), 400

        # Call ElevenLabs API
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }

        payload = {
            "text": text,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        response = requests.post(f"{ELEVENLABS_URL}{VOICE_ID}", json=payload, headers=headers)

        if response.status_code != 200:
            return jsonify({"error": "Failed to generate audio", "details": response.text}), response.status_code

        # Save audio content to a local folder
        output_folder = "audio_outputs"
        os.makedirs(output_folder, exist_ok=True)  # Create folder if it doesn't exist

        # Save audio to OUTPUT_FOLDER
        audio_file_path = os.path.join(OUTPUT_FOLDER, "output.mp3")
        with open(audio_file_path, "wb") as audio_file:
            audio_file.write(response.content)

        # Return file URL
        return jsonify({
            "message": "Audio file generated successfully.",
            "file_url": f"{request.host_url}/audio/{os.path.basename(audio_file_path)}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Serve static files from the audio_outputs folder
@app.route('/audio/<filename>')
def serve_audio(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)

    if not os.path.isfile(file_path):
        return "File not found", 404

    # Handle Range requests for streaming
    range_header = request.headers.get('Range', None)
    if not range_header:
        # If no Range header, serve the full file
        return send_file(file_path)

    # Extract byte range
    size = os.path.getsize(file_path)
    byte_range = range_header.split('=')[-1]
    start, end = byte_range.split('-')
    start = int(start) if start else 0
    end = int(end) if end else size - 1

    # Ensure the range is valid
    if start >= size or end >= size:
        return "Range Not Satisfiable", 416

    length = end - start + 1
    headers = {
        'Content-Range': f'bytes {start}-{end}/{size}',
        'Accept-Ranges': 'bytes',
        'Content-Length': str(length),
        'Content-Type': 'audio/mpeg',
    }

    # Open file and read the specified range
    with open(file_path, 'rb') as f:
        f.seek(start)
        data = f.read(length)

    return Response(data, 206, headers=headers)


# POST /createContacts - Create a Contact
@app.route('/createContact', methods=['POST'])
def create_contact():
    data = request.get_json()

    # Validate required fields
    if not data or 'name' not in data or 'email' not in data:
        return jsonify({"error": "Name and Email are required"}), 400

    # Split the name into first and last name
    name_parts = data['name'].strip().split()
    first_name = name_parts[0] if len(name_parts) > 0 else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Load credentials
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401
    except Exception as e:
        return jsonify({'error': 'Failed to load credentials', 'details': str(e)}), 500

    service = build('people', 'v1', credentials=creds)

    try:
        # Build the contact payload with extended fields
        contact_body = {
            "names": [{"givenName": first_name, "familyName": last_name}],
            "emailAddresses": [{"value": data['email']}],
            "phoneNumbers": [
                {"value": data.get('phone'), "type": "mobile"},
                {"value": data.get('workPhone'), "type": "work"} if data.get('workPhone') else None,
                {"value": data.get('officePhone'), "type": "work"} if data.get('officePhone') else None
            ],
            "organizations": [
                {
                    "name": data.get('company'),
                    "title": data.get('position'),
                    "type": "work"
                }
            ]
        }

        # Filter out None values from phoneNumbers and organizations
        contact_body['phoneNumbers'] = [phone for phone in contact_body['phoneNumbers'] if phone]
        contact_body['organizations'] = [org for org in contact_body['organizations'] if org.get('name') or org.get('title')]

        # Call Google People API to create the contact
        created_contact = service.people().createContact(body=contact_body).execute()

        return jsonify({
            "message": "Contact created successfully",
            "ContactId": created_contact.get('resourceName'),
            "name": f"{first_name} {last_name}".strip(),
            "email": data['email'],
            "phone": data.get('phone'),
            "workPhone": data.get('workPhone'),
            "officePhone": data.get('officePhone'),
            "company": data.get('company'),
            "position": data.get('position')
        }), 201

    except Exception as e:
        return jsonify({"error": "Failed to create contact", "details": str(e)}), 500


# POST /getContacts - Retrieve a Contacts
@app.route('/getContacts', methods=['POST'])
def get_contact():
    data = request.get_json()

    # Extract parameters
    contact_id = data.get('ContactId')
    query = data.get('query')  # General query string (name, email, etc.)

    # Validate input
    if not (contact_id or query):
        return jsonify({"error": "At least one of ContactId or query must be provided"}), 400

    # Load credentials
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as token_file:
            creds_json = json.load(token_file)
            creds = Credentials.from_authorized_user_info(creds_json)
    else:
        return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

    service = build('people', 'v1', credentials=creds)

    # Search by ContactId
    if contact_id:
        try:
            person = service.people().get(resourceName=contact_id, personFields="names,emailAddresses,phoneNumbers").execute()
            return jsonify(person), 200
        except Exception as e:
            return jsonify({"error": "Contact not found", "details": str(e)}), 404

    # Search using the query string
    try:
        search_results = service.people().searchContacts(
            query=query,
            readMask="names,emailAddresses,phoneNumbers",
            pageSize=50  # Limit results to 50 for efficiency
        ).execute()

        results = search_results.get('results', [])

        if results:
            return jsonify(results), 200

        return jsonify({"error": "No contacts match the given criteria"}), 404

    except Exception as e:
        return jsonify({"error": "Failed to search contacts", "details": str(e)}), 500

# POST /updateContact - Update a Contact
@app.route('/updateContact', methods=['POST'])
def update_contact():
    data = request.get_json()
    contact_id = data.get('ContactId')

    # Load credentials
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as token_file:
            creds_json = json.load(token_file)
            creds = Credentials.from_authorized_user_info(creds_json)
    else:
        return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401

    service = build('people', 'v1', credentials=creds)

    # Validate ContactId
    if not contact_id:
        return jsonify({"error": "ContactId is required"}), 400

    try:
        # Fetch the existing contact to get its current etag
        contact = service.people().get(
            resourceName=contact_id,
            personFields="names,emailAddresses,phoneNumbers"
        ).execute()

        etag = contact.get('etag')
        if not etag:
            return jsonify({"error": "Failed to retrieve etag for the contact"}), 400

        # Prepare updated fields
        updated_contact_body = {"etag": etag}

        # Update Name if provided
        if 'name' in data:
            name_parts = data['name'].split()
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            updated_contact_body["names"] = contact.get('names', [])
            if updated_contact_body["names"]:
                updated_contact_body["names"][0]["givenName"] = first_name
                updated_contact_body["names"][0]["familyName"] = last_name
            else:
                updated_contact_body["names"] = [{"givenName": first_name, "familyName": last_name}]

        # Update Email if provided
        if 'email' in data:
            updated_contact_body["emailAddresses"] = contact.get('emailAddresses', [])
            if updated_contact_body["emailAddresses"]:
                updated_contact_body["emailAddresses"][0]["value"] = data['email']
            else:
                updated_contact_body["emailAddresses"] = [{"value": data['email']}]

        # Update Phone if provided
        if 'phone' in data:
            updated_contact_body["phoneNumbers"] = contact.get('phoneNumbers', [])
            if updated_contact_body["phoneNumbers"]:
                updated_contact_body["phoneNumbers"][0]["value"] = data['phone']
            else:
                updated_contact_body["phoneNumbers"] = [{"value": data['phone']}]

        # Update Company and Position
        if 'company' in data or 'position' in data:
            updated_contact_body["organizations"] = contact.get('organizations', [])
            if updated_contact_body["organizations"]:
                updated_contact_body["organizations"][0]["name"] = data.get('company', updated_contact_body[
                    "organizations"][0].get("name"))
                updated_contact_body["organizations"][0]["title"] = data.get('position', updated_contact_body[
                    "organizations"][0].get("title"))
            else:
                updated_contact_body["organizations"] = [
                    {"name": data.get('company', ""), "title": data.get('position', ""), "type": "work"}
                ]

        # Update the contact with etag
        updated_contact = service.people().updateContact(
            resourceName=contact_id,
            updatePersonFields="names,emailAddresses,phoneNumbers",
            body=updated_contact_body
        ).execute()

        return jsonify({
            "message": "Contact updated successfully",
            "ContactId": contact_id,
            "updatedFields": updated_contact
        }), 200

    except Exception as e:
        return jsonify({"error": "Failed to update contact", "details": str(e)}), 500

# POST /deleteContact - Delete a Contact
@app.route('/deleteContact', methods=['POST'])
def delete_contact():
    data = request.get_json()
    contact_id = data.get('ContactId')

    # Validate ContactId
    if not contact_id:
        return jsonify({"error": "ContactId is required"}), 400
    if not contact_id.startswith("people/"):
        return jsonify({"error": "Invalid ContactId format. It should start with 'people/'"}), 400

    # Load credentials
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as token_file:
                creds_json = json.load(token_file)
                creds = Credentials.from_authorized_user_info(creds_json)
        else:
            return jsonify({'error': 'User not authenticated. Please authenticate at /startAuth'}), 401
    except Exception as e:
        return jsonify({"error": "Failed to load credentials", "details": str(e)}), 500

    # Build the service
    try:
        service = build('people', 'v1', credentials=creds)
    except Exception as e:
        return jsonify({"error": "Failed to initialize Google People API client", "details": str(e)}), 500

    # Delete the contact
    try:
        service.people().deleteContact(resourceName=contact_id).execute()
        return jsonify({
            "message": "Contact deleted successfully",
            "ContactId": contact_id
        }), 200
    except Exception as e:
        # Handle specific errors based on the exception content
        error_message = str(e)
        if "notFound" in error_message:
            return jsonify({"error": "Contact not found", "ContactId": contact_id}), 404
        elif "permissionDenied" in error_message:
            return jsonify({"error": "Permission denied. Check API permissions."}), 403
        else:
            return jsonify({"error": "Failed to delete contact", "details": error_message}), 500

if __name__ == '__main__':
    initialize_google_drive()
    initialize_selenium()
    app.run(port=8080, debug=True)
