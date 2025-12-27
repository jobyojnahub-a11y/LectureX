import os
import json
import threading
import logging
from flask import Flask, render_template_string, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# Use current directory for data storage
DATA_DIR = os.path.join(os.getcwd(), 'data')
DATA_FILE = 'pw_uploader_data.json'
os.makedirs(DATA_DIR, exist_ok=True)
DATA_PATH = os.path.join(DATA_DIR, DATA_FILE)

# Session storage directory for Telethon
SESSION_DIR = os.path.join(os.getcwd(), 'sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

bot_instance = None
bot_thread = None

def load_data():
    try:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, 'r') as f:
                data = json.load(f)
                logger.info(f"✅ Data loaded from {DATA_PATH}")
                return data
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}")
    
    logger.info("Creating new default data")
    return {
        'auth': None,
        'config': {'telegramSession': '', 'pwToken': '', 'styStrkToken': ''},
        'channels': [],
        'session_active': False
    }

def save_data(data):
    try:
        with open(DATA_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"✅ Data saved to {DATA_PATH}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving data: {e}")
        return False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PW Auto Uploader</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
    <div id="app"></div>
    <script>
        let authData = null;
        let configData = null;
        let channelsData = [];
        let sessionActive = false;

        async function loadData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                authData = data.auth;
                configData = data.config;
                channelsData = data.channels;
                sessionActive = data.session_active;
                render();
            } catch (err) {
                console.error('Load error:', err);
                alert('Failed to load data');
            }
        }

        function isAuthenticated() {
            return sessionStorage.getItem('authenticated') === 'true';
        }

        async function login() {
            const password = document.getElementById('password').value;
            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await res.json();
                if (data.success) {
                    sessionStorage.setItem('authenticated', 'true');
                    render();
                } else {
                    alert(data.error);
                }
            } catch (err) {
                alert('Login failed');
            }
        }

        async function setupPassword() {
            const password = document.getElementById('setupPassword').value;
            const confirm = document.getElementById('confirmPassword').value;
            
            if (password !== confirm) {
                alert('Passwords do not match!');
                return;
            }
            if (password.length < 6) {
                alert('Password must be at least 6 characters!');
                return;
            }

            try {
                const res = await fetch('/api/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ Setup successful!');
                    loadData();
                } else {
                    alert('❌ ' + data.error);
                }
            } catch (err) {
                alert('Setup failed');
            }
        }

        function logout() {
            sessionStorage.removeItem('authenticated');
            render();
        }

        async function saveConfig() {
            const config = {
                telegramSession: document.getElementById('telegramSession').value,
                pwToken: document.getElementById('pwToken').value,
                styStrkToken: document.getElementById('styStrkToken').value
            };

            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ Configuration saved!');
                    configData = config;
                } else {
                    alert('❌ ' + data.error);
                }
            } catch (err) {
                alert('Failed to save');
            }
        }

        async function toggleSession() {
            const action = sessionActive ? 'deactivate' : 'activate';
            
            if (!sessionActive && !configData.telegramSession) {
                alert('⚠️ Configure session string first!');
                return;
            }
            
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = 'Processing...';
            
            try {
                const res = await fetch('/api/session/' + action, { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();
                if (data.success) {
                    sessionActive = !sessionActive;
                    alert('✅ ' + data.message);
                    render();
                } else {
                    alert('❌ ' + data.error);
                    btn.disabled = false;
                }
            } catch (err) {
                alert('❌ Error: ' + err.message);
                btn.disabled = false;
            }
        }

        async function addChannel() {
            const channel = {
                name: document.getElementById('channelName').value,
                channelId: document.getElementById('channelId').value,
                batchId: document.getElementById('batchId').value,
                active: true,
                id: Date.now().toString()
            };

            if (!channel.name || !channel.channelId || !channel.batchId) {
                alert('Fill all fields!');
                return;
            }

            try {
                const res = await fetch('/api/channels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(channel)
                });
                const data = await res.json();
                if (data.success) {
                    channelsData = data.channels;
                    document.getElementById('channelName').value = '';
                    document.getElementById('channelId').value = '';
                    document.getElementById('batchId').value = '';
                    alert('✅ Channel added!');
                    render();
                }
            } catch (err) {
                alert('Failed to add channel');
            }
        }

        async function deleteChannel(id) {
            if (!confirm('Delete this channel?')) return;
            try {
                const res = await fetch('/api/channels/' + id, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    channelsData = data.channels;
                    render();
                }
            } catch (err) {
                alert('Failed to delete');
            }
        }

        async function toggleChannel(id) {
            try {
                const res = await fetch('/api/channels/' + id + '/toggle', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    channelsData = data.channels;
                    render();
                }
            } catch (err) {
                alert('Failed to toggle');
            }
        }

        function render() {
            const app = document.getElementById('app');
            if (!authData) {
                app.innerHTML = renderSetup();
            } else if (!isAuthenticated()) {
                app.innerHTML = renderLogin();
            } else {
                app.innerHTML = renderAdminPanel();
            }
        }

        function renderSetup() {
            return `<div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
                <div class="bg-white rounded-lg shadow-xl p-8 max-w-md w-full">
                    <div class="text-center mb-6">
                        <div class="w-16 h-16 bg-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                            </svg>
                        </div>
                        <h1 class="text-2xl font-bold text-gray-800">First Time Setup</h1>
                        <p class="text-gray-600 mt-2">Create admin password</p>
                    </div>
                    <div class="space-y-4">
                        <input type="password" id="setupPassword" placeholder="Password (min 6 chars)" class="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                        <input type="password" id="confirmPassword" placeholder="Confirm Password" class="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                        <button onclick="setupPassword()" class="w-full bg-indigo-600 text-white py-3 rounded-lg hover:bg-indigo-700 font-medium">Setup Admin Panel</button>
                    </div>
                </div>
            </div>`;
        }

        function renderLogin() {
            return `<div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
                <div class="bg-white rounded-lg shadow-xl p-8 max-w-md w-full">
                    <div class="text-center mb-6">
                        <div class="w-16 h-16 bg-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                            </svg>
                        </div>
                        <h1 class="text-2xl font-bold text-gray-800">PW Auto Uploader</h1>
                        <p class="text-gray-600 mt-2">Admin Login</p>
                    </div>
                    <div class="space-y-4">
                        <input type="password" id="password" placeholder="Enter password" class="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none" onkeypress="if(event.key==='Enter') login()">
                        <button onclick="login()" class="w-full bg-indigo-600 text-white py-3 rounded-lg hover:bg-indigo-700 font-medium">Login</button>
                    </div>
                </div>
            </div>`;
        }

        function renderAdminPanel() {
            const activeChannels = channelsData.filter(ch => ch.active).length;
            return `<div class="min-h-screen bg-gray-50">
                <div class="bg-white shadow">
                    <div class="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
                        <h1 class="text-2xl font-bold text-gray-800">PW Auto Uploader</h1>
                        <button onclick="logout()" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">Logout</button>
                    </div>
                </div>
                <div class="${sessionActive ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'} border-b px-4 py-3">
                    <div class="max-w-7xl mx-auto flex justify-between items-center">
                        <div class="flex items-center space-x-2">
                            <div class="w-3 h-3 rounded-full ${sessionActive ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}"></div>
                            <span class="font-medium">${sessionActive ? '✅ Telegram Session Active' : '⚠️ Session Inactive'}</span>
                        </div>
                        <button onclick="toggleSession()" class="px-4 py-2 ${sessionActive ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'} text-white rounded-lg font-medium">${sessionActive ? 'Deactivate' : 'Activate Session'}</button>
                    </div>
                </div>
                <div class="max-w-7xl mx-auto px-4 py-6">
                    <div class="bg-white rounded-lg shadow mb-6">
                        <div class="border-b flex">
                            <button onclick="showTab('channels')" id="tab-channels" class="px-6 py-4 border-b-2 border-indigo-600 text-indigo-600 font-medium">Channels</button>
                            <button onclick="showTab('config')" id="tab-config" class="px-6 py-4 border-b-2 border-transparent text-gray-500 hover:text-gray-700 font-medium">Configuration</button>
                        </div>
                        <div class="p-6">
                            <div id="content-channels">
                                <div class="bg-gray-50 p-6 rounded-lg mb-6">
                                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Add New Channel</h3>
                                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <input type="text" id="channelName" placeholder="Channel Name" class="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                        <input type="text" id="channelId" placeholder="Channel ID (@channel or -100xxx)" class="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                        <input type="text" id="batchId" placeholder="Batch ID" class="px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                    </div>
                                    <button onclick="addChannel()" class="mt-4 px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Add Channel</button>
                                </div>
                                <h3 class="text-lg font-semibold text-gray-800 mb-4">Active Channels (${activeChannels})</h3>
                                ${channelsData.length === 0 ? '<div class="text-center py-12 text-gray-500">No channels added yet. Add your first channel above.</div>' : channelsData.map(ch => `
                                    <div class="p-4 border-2 ${ch.active ? 'border-green-200 bg-green-50' : 'border-gray-200 bg-gray-50'} rounded-lg mb-3">
                                        <div class="flex justify-between items-center">
                                            <div class="flex-1">
                                                <div class="flex items-center space-x-3">
                                                    <h4 class="font-semibold text-gray-800">${ch.name}</h4>
                                                    <span class="px-2 py-1 text-xs rounded-full ${ch.active ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-600'}">${ch.active ? 'Active' : 'Inactive'}</span>
                                                </div>
                                                <p class="text-sm text-gray-600 mt-1"><span class="font-medium">Channel:</span> ${ch.channelId} | <span class="font-medium">Batch:</span> ${ch.batchId}</p>
                                            </div>
                                            <div class="flex space-x-2">
                                                <button onclick="toggleChannel('${ch.id}')" class="px-4 py-2 ${ch.active ? 'bg-yellow-600 hover:bg-yellow-700' : 'bg-green-600 hover:bg-green-700'} text-white rounded-lg text-sm">${ch.active ? 'Disable' : 'Enable'}</button>
                                                <button onclick="deleteChannel('${ch.id}')" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm">Delete</button>
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                            <div id="content-config" style="display:none;">
                                <div class="space-y-6">
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">Telegram Session String</label>
                                        <textarea id="telegramSession" class="w-full px-4 py-2 border rounded-lg h-32 focus:ring-2 focus:ring-indigo-500 focus:outline-none font-mono text-sm" placeholder="Paste your session string here...">${configData.telegramSession || ''}</textarea>
                                        <p class="text-sm text-gray-500 mt-2">Required for bot to work. Generate using session_generator.py</p>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">PW Token</label>
                                        <input type="text" id="pwToken" value="${configData.pwToken || ''}" class="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none" placeholder="Enter PW API Token">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-2">STYSTRK Token (Optional)</label>
                                        <input type="text" id="styStrkToken" value="${configData.styStrkToken || ''}" class="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none" placeholder="Enter STYSTRK Token">
                                    </div>
                                    <button onclick="saveConfig()" class="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium">Save Configuration</button>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-6">
                        <h3 class="font-semibold text-blue-900 mb-3">📖 How it works:</h3>
                        <ol class="list-decimal list-inside space-y-2 text-blue-800 text-sm">
                            <li>Configure your Telegram session string and tokens in Configuration tab</li>
                            <li>Click "Activate Session" to start the bot</li>
                            <li>Add channels with their corresponding batch IDs</li>
                            <li>Send <code class="bg-blue-100 px-2 py-1 rounded">/check</code> command in any monitored channel</li>
                            <li>Bot will automatically process and upload lectures with 5-minute cooldown</li>
                        </ol>
                    </div>
                </div>
            </div>`;
        }

        function showTab(tab) {
            document.getElementById('tab-channels').className = 'px-6 py-4 border-b-2 border-transparent text-gray-500 hover:text-gray-700 font-medium';
            document.getElementById('tab-config').className = 'px-6 py-4 border-b-2 border-transparent text-gray-500 hover:text-gray-700 font-medium';
            document.getElementById('content-channels').style.display = 'none';
            document.getElementById('content-config').style.display = 'none';
            document.getElementById('tab-' + tab).className = 'px-6 py-4 border-b-2 border-indigo-600 text-indigo-600 font-medium';
            document.getElementById('content-' + tab).style.display = 'block';
        }

        loadData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(ADMIN_PANEL_HTML)

@app.route('/api/data')
def get_data():
    try:
        data = load_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in /api/data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/setup', methods=['POST'])
def setup():
    try:
        data = load_data()
        if data['auth']:
            return jsonify({'success': False, 'error': 'Already setup'})
        password = request.json.get('password')
        data['auth'] = {'passwordHash': hash_password(password)}
        if save_data(data):
            logger.info("✅ Admin password setup complete")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Failed to save'})
    except Exception as e:
        logger.error(f"Error in setup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login_route():
    try:
        data = load_data()
        password = request.json.get('password')
        if not data['auth']:
            return jsonify({'success': False, 'error': 'Not setup'})
        if hash_password(password) == data['auth']['passwordHash']:
            session['authenticated'] = True
            logger.info("✅ Admin logged in")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Incorrect password'})
    except Exception as e:
        logger.error(f"Error in login: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config_route():
    try:
        data = load_data()
        config = request.json
        data['config'] = config
        if save_data(data):
            global bot_instance
            if bot_instance:
                bot_instance.update_config(config)
            logger.info("✅ Configuration saved")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Failed to save'})
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/<action>', methods=['POST'])
def toggle_session_route(action):
    try:
        data = load_data()
        if action == 'activate':
            if not data['config']['telegramSession']:
                return jsonify({'success': False, 'error': 'Session string not configured'})
            
            try:
                from bot import PWAutoUploader
            except Exception as e:
                logger.error(f"Failed to import bot: {e}")
                return jsonify({'success': False, 'error': f'Bot import failed: {str(e)}'})
            
            global bot_instance, bot_thread
            try:
                if not bot_instance:
                    api_id = os.getenv('API_ID')
                    api_hash = os.getenv('API_HASH')
                    
                    if not api_id or not api_hash:
                        return jsonify({'success': False, 'error': 'API_ID or API_HASH not set in environment variables'})
                    
                    logger.info(f"Starting bot with session directory: {SESSION_DIR}")
                    
                    bot_instance = PWAutoUploader(
                        data['config']['telegramSession'], 
                        int(api_id), 
                        api_hash,
                        session_dir=SESSION_DIR
                    )
                    bot_instance.update_config(data['config'])
                    bot_instance.update_channels(data['channels'])
                    
                    bot_thread = threading.Thread(target=bot_instance.run)
                    bot_thread.daemon = True
                    bot_thread.start()
                    
                    logger.info("✅ Bot started successfully")
                
                data['session_active'] = True
                save_data(data)
                return jsonify({'success': True, 'message': 'Bot activated successfully! 🚀'})
                
            except Exception as e:
                logger.error(f"Failed to start bot: {e}")
                return jsonify({'success': False, 'error': f'Failed to start: {str(e)}'})
                
        elif action == 'deactivate':
            data['session_active'] = False
            save_data(data)
            
            if bot_instance:
                try:
                    bot_instance.stop()
                    logger.info("✅ Bot stopped")
                except Exception as e:
                    logger.error(f"Error stopping bot: {e}")
            
            return jsonify({'success': True, 'message': 'Session deactivated'})
            
        return jsonify({'success': False, 'error': 'Invalid action'})
        
    except Exception as e:
        logger.error(f"Error in toggle session: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channels', methods=['POST'])
def add_channel_route():
    try:
        data = load_data()
        channel = request.json
        data['channels'].append(channel)
        if save_data(data):
            global bot_instance
            if bot_instance:
                bot_instance.update_channels(data['channels'])
            logger.info(f"✅ Channel added: {channel['name']}")
            return jsonify({'success': True, 'channels': data['channels']})
        return jsonify({'success': False, 'error': 'Failed to save'})
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
def delete_channel_route(channel_id):
    try:
        data = load_data()
        data['channels'] = [ch for ch in data['channels'] if ch['id'] != channel_id]
        if save_data(data):
            global bot_instance
            if bot_instance:
                bot_instance.update_channels(data['channels'])
            logger.info(f"✅ Channel deleted: {channel_id}")
            return jsonify({'success': True, 'channels': data['channels']})
        return jsonify({'success': False, 'error': 'Failed to save'})
    except Exception as e:
        logger.error(f"Error deleting channel: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channels/<channel_id>/toggle', methods=['POST'])
def toggle_channel_route(channel_id):
    try:
        data = load_data()
        for ch in data['channels']:
            if ch['id'] == channel_id:
                ch['active'] = not ch['active']
                break
        if save_data(data):
            global bot_instance
            if bot_instance:
                bot_instance.update_channels(data['channels'])
            logger.info(f"✅ Channel toggled: {channel_id}")
            return jsonify({'success': True, 'channels': data['channels']})
        return jsonify({'success': False, 'error': 'Failed to save'})
    except Exception as e:
        logger.error(f"Error toggling channel: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"🚀 Starting PW Auto Uploader on port {port}")
    logger.info(f"📁 Data directory: {DATA_DIR}")
    logger.info(f"📁 Session directory: {SESSION_DIR}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
