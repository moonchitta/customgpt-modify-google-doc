# Custom Google Docs API with CustomGPT Integration

This project provides an API to integrate Google Docs functionality with **CustomGPT** or similar platforms. It supports authentication, listing Google Docs-compatible files, reading content, and updating existing documents.

---

## **Features**
- **Authentication**: Allows users to authenticate with their Google account via OAuth 2.0.
- **Google Docs Operations**:
  - List Google Docs-compatible files.
  - Read content from a Google Docs file.
  - Update existing Google Docs with new content.
- **Privacy Policy**: Provides a publicly accessible privacy policy endpoint for transparency.

---

## **Endpoints**
1. **`GET /startAuth`**
   - Initiates the Google OAuth flow by returning an authentication URL.
   - **Response**: JSON with the `auth_url` key.

2. **`GET /handleAuth`**
   - Handles the Google OAuth callback, exchanges the authorization code for tokens, and saves them locally.

3. **`GET /listFiles`**
   - Lists files in Google Drive that are compatible with Google Docs.
   - **Response**: JSON containing an array of file details.
     ```json
     {
       "files": [
         {
           "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
           "name": "Sample Document",
           "mimeType": "application/vnd.google-apps.document"
         }
       ]
     }
     ```

4. **`GET /readDoc`**
   - Reads the content of a Google Docs file.
   - **Query Parameter**:
     - `document_id`: The ID of the document to read.
   - **Response**: JSON containing the document's content.
     ```json
     {
       "content": "This is the content of the document."
     }
     ```

5. **`POST /updateDoc`**
   - Updates a Google Docs file by adding new content at a specified location.
   - **Request Body**:
     ```json
     {
       "document_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
       "content": "This is the new content.",
       "location_index": 1
     }
     ```
   - **Response**:
     ```json
     {
       "message": "Content updated successfully in document: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
     }
     ```

6. **`GET /privacy`**
   - Displays the privacy policy as an HTML page in the browser.

---

## **Setup Instructions**

### **Prerequisites**
1. Install Python (3.7 or above).
2. Install the required libraries:
   ```bash
   pip install flask google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```
3. Download your Google OAuth credentials (`client_secret.json`) from the [Google Cloud Console](https://console.cloud.google.com/).

### **Google Cloud Configuration**
1. Go to **APIs & Services > Credentials**.
2. Enable the following APIs:
   - Google Docs API
   - Google Drive API
3. Create an **OAuth 2.0 Client ID**:
   - Application type: **Web Application**.
   - Add the following as **Authorized Redirect URIs**:
     - For local development: `http://127.0.0.1:5000/handleAuth`
     - For production (via ngrok or server): `https://YOUR_NGROK_URL/handleAuth`
4. Download the `client_secret.json` file and place it in the root directory of this project.

---

### **How to Run**
1. Clone this repository:
   ```bash
   git clone https://github.com/moonchitta/customgpt-modify-google-doc.git
   cd docGPT
   ```

2. Place the `client_secret.json` file in the root directory.

3. Run the Flask application:
   ```bash
   python app.py
   ```

4. Expose your app to the internet using ngrok:
   ```bash
   ngrok http 5000
   ```
   Note the HTTPS URL (e.g., `https://YOUR_NGROK_URL`) provided by ngrok.

---

### **Usage**

1. **Authenticate with Google**:
   - Access the `/startAuth` endpoint:
     ```bash
     GET https://YOUR_NGROK_URL/startAuth
     ```
   - Open the returned `auth_url` in a browser to log in and grant permissions.
   - Google redirects to `/handleAuth`, where credentials are saved.

2. **List Google Docs-Compatible Files**:
   - Call the `/listFiles` endpoint:
     ```bash
     GET https://YOUR_NGROK_URL/listFiles
     ```

3. **Read a Google Docs File**:
   - Call the `/readDoc` endpoint with a document ID:
     ```bash
     GET https://YOUR_NGROK_URL/readDoc?document_id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
     ```

4. **Update a Google Docs File**:
   - Call the `/updateDoc` endpoint:
     ```bash
     POST https://YOUR_NGROK_URL/updateDoc
     Content-Type: application/json
     Body:
     {
       "document_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
       "content": "This is the new content.",
       "location_index": 1
     }
     ```

5. **View Privacy Policy**:
   - Visit the `/privacy` endpoint:
     ```bash
     GET https://YOUR_NGROK_URL/privacy
     ```

---

## **Project Structure**

```plaintext
google-docs-api/
├── app.py                # Main Flask application
├── client_secret.json    # Google OAuth credentials (not included, must be added)
├── requirements.txt      # Python dependencies
└── README.md             # Project documentation
```

---

## **Important Notes**
- **Authentication Tokens**: OAuth tokens are stored locally in `token.json`. Keep this file secure.
- **Redirect URIs**: Ensure that your redirect URIs in the Google Cloud Console match the ones used in your app (local and ngrok URLs).
- **Privacy Policy**: Update the `/privacy` endpoint text if necessary to reflect your actual data usage practices.

---

## **Contributing**
Contributions are welcome! Feel free to submit a pull request or open an issue to improve the project.

---

## **License**
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
