from flask import Flask, request, jsonify
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)

# File paths and scopes
CLIENT_SECRET_FILE = 'client_secret.json'  # Path to your client_secret.json file
TOKEN_FILE = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive.readonly']

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

# Authentication flow (unchanged)
@app.route('/startAuth', methods=['GET'])
def start_auth():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'https://df92-2407-d000-1a-e3-d573-b85e-9f94-f098.ngrok-free.app/handleAuth'
    auth_url, _ = flow.authorization_url(prompt='consent')
    return jsonify({'auth_url': auth_url}), 200

@app.route('/handleAuth', methods=['GET'])
def handle_auth():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = 'https://df92-2407-d000-1a-e3-d573-b85e-9f94-f098.ngrok-free.app/handleAuth'
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

if __name__ == '__main__':
    app.run(debug=True)
