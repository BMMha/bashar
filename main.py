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

# متغير عام لحفظ آخر توكن (يمكن استخدامه لاحقاً أو للتعبئة التلقائية)
LATEST_REFRESH_TOKEN = None

# بيانات الاعتماد
CLIENT_ID = '1096352235538-pkdcd73qn9miojk1cflr52fuminb4j4c.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'https://bashar-7fw9.onrender.com/callback'

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
    global LATEST_REFRESH_TOKEN
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    try:
        refresh_token = credentials.refresh_token
        if refresh_token:
            LATEST_REFRESH_TOKEN = refresh_token
    except Exception as e:
        print(f"An error occurred during callback: {e}")
        
    return redirect(url_for('show_report'))


# ✅ تم تعديل هذه الدالة بالكامل
@app.route('/report', methods=['GET', 'POST'])
def show_report():
    # ✅ هذا الكود سيعمل بعد أن يقوم المستخدم بلصق التوكن والضغط على الزر
    if request.method == 'POST':
        # ✅ جلب التوكن من حقل الإدخال الذي اسمه 'token_input'
        refresh_token = request.form.get('token_input')

        if not refresh_token:
            return "<h2>الرجاء إدخال Refresh Token.</h2>", 400

        try:
            credentials = Credentials(
                token=None, refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                scopes=['https://www.googleapis.com/auth/gmail.readonly']
            )
            
            service = build('gmail', 'v1', credentials=credentials)
            result = service.users().messages().list(userId='me', maxResults=20, q="is:inbox").execute()
            messages = result.get('messages', [])
            
            # ... (كود عرض التقرير يبقى كما هو)
            if not messages: return "<h2>لم يتم العثور على رسائل في البريد الوارد.</h2>"
            emails_data = []
            def batch_callback(request_id, response, exception):
                if exception is None: emails_data.append(response)
                else: print(f"Batch request error: {exception}")
            batch = service.new_batch_http_request(callback=batch_callback)
            for msg in messages:
                batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
            batch.execute()
            
            # كود توليد وعرض الرسائل (يبقى كما هو)
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

        except Exception as e:
            # عرض الخطأ في صفحة الإدخال نفسها
            error_message = f"حدث خطأ: {e}"
            # (سنعود لاحقًا إلى صفحة الإدخال مع رسالة الخطأ)

    # ✅ هذا الكود سيعمل عند زيارة الصفحة لأول مرة (GET request)
    # سيقوم بعرض صفحة HTML تحتوي على حقل الإدخال
    token_value = LATEST_REFRESH_TOKEN if LATEST_REFRESH_TOKEN else ""
    form_html = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>إدخال التوكن</title>
        <style>
            body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }}
            .container {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; width: 600px; }}
            h1 {{ color: #333; }}
            textarea {{ width: 100%; min-height: 100px; margin-bottom: 20px; border-radius: 8px; border: 1px solid #ccc; padding: 10px; font-family: monospace; }}
            button {{ padding: 12px 24px; border-radius: 8px; border: none; background-color: #007bff; color: white; font-size: 16px; cursor: pointer; }}
            .error {{ color: red; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>عرض رسائل البريد</h1>
            <p>الرجاء لصق الـ Refresh Token في الحقل أدناه لعرض الرسائل.</p>
            <form method="post">
                <textarea name="token_input" placeholder="1//0...">{token_value}</textarea>
                <button type="submit">عرض الرسائل</button>
            </form>
            {f'<p class="error">{error_message}</p>' if 'error_message' in locals() else ''}
        </div>
    </body>
    </html>
    """
    return Response(form_html, mimetype='text/html; charset=utf-8')