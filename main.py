import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'أهلاً بك، تطبيقي يعمل على Railway!'

if __name__ == "__main__":
    # احصل على المنفذ من متغيرات البيئة التي توفرها Railway
    port = int(os.environ.get('PORT', 5000))
    # استمع على 0.0.0.0 ليكون الخادم متاحاً خارجياً
    app.run(host='0.0.0.0', port=port)