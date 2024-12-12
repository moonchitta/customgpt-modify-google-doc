import googleapiclient
from flask import Flask, request, jsonify
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json
from flask import Flask, request, jsonify, send_from_directory
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import os

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
SCOPES = [ 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive.readonly']

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Default voice ID

# Elevenlabs base url
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/"

# Folder to save generated audio files
OUTPUT_FOLDER = "audio_outputs"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)  # Ensure folder exists

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
    flow.redirect_uri = 'https://f859-2407-d000-1a-4cf4-f9cf-5b9d-8f18-22f0.ngrok-free.app/handleAuth'
    auth_url, _ = flow.authorization_url(prompt='consent')
    return jsonify({'auth_url': auth_url}), 200

@app.route('/handleAuth', methods=['GET'])
def handle_auth():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'https://f859-2407-d000-1a-4cf4-f9cf-5b9d-8f18-22f0.ngrok-free.app/handleAuth'
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
    return send_from_directory(OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)
