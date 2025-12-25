import os
import json
import asyncio
import threading
import logging
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
import hashlib

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret-key-in-production')
CORS(app)

# Data file path - will persist on Render's disk
DATA_DIR = '/opt/render/project/src/data'
DATA_FILE = 'pw_uploader_data.json'

# Create data directory if not exists
os.makedirs(DATA_DIR, exist_ok=True)
DATA_PATH = os.path.join(DATA_DIR, DATA_FILE)

# Global bot instance
bot_instance = None
bot_thread = None

def load_data():
    """Load data from JSON file"""
    try:
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, 'r') as f:
                data = json.load(f)
                logger.info(f"Data loaded from {DATA_PATH}")
                return data
    except Exception as e:
        logger.error(f"Error loading data: {e}")
    
    # Return default data
    return {
        'auth': None,
        'config': {
            'telegramSession': '',
            'pwToken': '',
            'styStrkToken': ''
        },
        'channels': [],
        'session_active': False
    }

def save_data(data):
    """Save data to JSON file"""
    try:
        with open(DATA_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Data saved to {DATA_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        return False

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

# HTML Template
ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PW Auto Uploader - Admin Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    </style>
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
                console.error('Error loading data:', err);
                alert('Failed to load data. Please refresh the page.');
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
                    alert(data.error || 'Login failed');
                }
            } catch (err) {
                console.error('Login error:', err);
                alert('Login failed. Please try again.');
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
                    alert('Password setup successful!');
                    loadData();
                } else {
                    alert(data.error || 'Setup failed');
                }
            } catch (err) {
                console.error('Setup error:', err);
                alert('Setup failed. Please try again.');
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
                    alert('Configuration saved!');
                    configData = config;
                } else {
                    alert(data.error || 'Save failed');
                }
            } catch (err) {
                console.error('Save config error:', err);
                alert('Failed to save configuration.');
            }
        }

        async function toggleSession() {
            const action = sessionActive ? 'deactivate' : 'activate';
            
            if (!sessionActive && !configData.telegramSession) {
                alert('Please configure Telegram session string first!');
                return;
            }
            
            try {
                const res = await fetch('/api/session/' + action, { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();
                if (data.success) {
                    sessionActive = !sessionActive;
                    alert(data.message || 'Session toggled successfully');
                    render();
                } else {
                    alert(data.error || 'Failed to toggle session');
                }
            } catch (err) {
                console.error('Toggle session error:', err);
                alert('Error: ' + (err.message || 'Failed to toggle session'));
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
                alert('Please fill all fields!');
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
                    render();
                } else {
                    alert(data.error || 'Failed to add channel');
                }
            } catch (err) {
                console.error('Add channel error:', err);
                alert('Failed to add channel.');
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
                } else {
                    alert(data.error || 'Failed to delete channel');
                }
            } catch (err) {
                console.error('Delete channel error:', err);
                alert('Failed to delete channel.');
            }
        }

        async function toggleChannel(id) {
            try {
                const res = await fetch('/api/channels/' + id + '/toggle', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    channelsData = data.channels;
                    render();
                } else {
                    alert(data.error || 'Failed to toggle channel');
                }
            } catch (err) {
                console.error('Toggle channel error:', err);
                alert('Failed to toggle channel.');
            }
        }

        function render() {
            const app = document.getElementById('app');
            
            if (!authData) {
                app.innerHTML = renderSetup();
                return;
            }
            
            if (!isAuthenticated()) {
                app.innerHTML = renderLogin();
                return;
            }

            app.innerHTML = renderAdminPanel();
        }

        function renderSetup() {
            return `
                <div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
                    <div class="bg-white rounded-lg shadow-xl p-8 max-w-md w-full fade-in">
                        <div class="text-center mb-6">
                            <div class="w-16 h-16 bg-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                                </svg>
                            </div>
                            <h1 class="text-2xl font-bold text-gray-800">First Time Setup</h1>
                            <p class="text-gray-600 mt-2">Create your admin password</p>
                        </div>
                        <div class="space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">Password (min 6 chars)</label>
                                <input type="password" id="setupPassword" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">Confirm Password</label>
                                <input type="password" id="confirmPassword" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                            </div>
                            <button onclick="setupPassword()" class="w-full bg-indigo-600 text-white py-3 rounded-lg hover:bg-indigo-700 font-medium transition-colors">
                                Setup Admin Panel
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        function renderLogin() {
            return `
                <div class="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
                    <div class="bg-white rounded-lg shadow-xl p-8 max-w-md w-full fade-in">
                        <div class="text-center mb-6">
                            <div class="w-16 h-16 bg-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                                <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                                </svg>
                            </div>
                            <h1 class="text-2xl font-bold text-gray-800">PW Auto Uploader</h1>
                            <p class="text-gray-600 mt-2">Enter your admin password</p>
                        </div>
                        <div class="space-y-4">
                            <input type="password" id="password" placeholder="Enter password" 
                                   class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                   onkeypress="if(event.key==='Enter') login()">
                            <button onclick="login()" class="w-full bg-indigo-600 text-white py-3 rounded-lg hover:bg-indigo-700 font-medium transition-colors">
                                Login to Admin Panel
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }

        function renderAdminPanel() {
            const activeChannels = channelsData.filter(ch => ch.active).length;
            
            return `
                <div class="min-h-screen bg-gray-50">
                    <div class="bg-white shadow">
                        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
                            <h1 class="text-2xl font-bold text-gray-800">PW Auto Uploader - Admin Panel</h1>
                            <button onclick="logout()" class="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">
                                <span>Logout</span>
                            </button>
                        </div>
                    </div>

                    <div class="${sessionActive ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'} border-b px-4 py-3">
                        <div class="max-w-7xl mx-auto flex items-center justify-between">
                            <div class="flex items-center space-x-2">
                                <div class="w-3 h-3 rounded-full ${sessionActive ? 'bg-green-500' : 'bg-yellow-500'}"></div>
                                <span class="font-medium text-gray-800">
                                    ${sessionActive ? 'Telegram Session Active ✅' : 'Telegram Session Inactive ⚠️'}
                                </span>
                            </div>
                            <button onclick="toggleSession()" 
                                    class="px-4 py-2 rounded-lg font-medium transition-colors ${sessionActive ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'} text-white">
                                ${sessionActive ? 'Deactivate' : 'Activate Session'}
                            </button>
                        </div>
                    </div>

                    <div class="max-w-7xl mx-auto px-4 py-6">
                        <div class="bg-white rounded-lg shadow mb-6">
                            <div class="border-b flex">
                                <button onclick="showTab('channels')" id="tab-channels" class="px-6 py-4 border-b-2 border-indigo-600 text-indigo-600 font-medium">
                                    Channels
                                </button>
                                <button onclick="showTab('config')" id="tab-config" class="px-6 py-4 border-b-2 border-transparent text-gray-500 hover:text-gray-700 font-medium">
                                    Configuration
                                </button>
                            </div>

                            <div class="p-6">
                                <div id="content-channels">
                                    <div class="bg-gray-50 p-6 rounded-lg mb-6">
                                        <h3 class="text-lg font-semibold text-gray-800 mb-4">Add New Channel</h3>
                                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                                            <input type="text" id="channelName" placeholder="Channel Name" 
                                                   class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                            <input type="text" id="channelId" placeholder="Channel ID (@channel or -100xxx)" 
                                                   class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                            <input type="text" id="batchId" placeholder="Batch ID" 
                                                   class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none">
                                        </div>
                                        <button onclick="addChannel()" class="mt-4 px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
                                            Add Channel
                                        </button>
                                    </div>

                                    <div>
                                        <h3 class="text-lg font-semibold text-gray-800 mb-4">Active Channels (${activeChannels})</h3>
                                        ${channelsData.length === 0 ? 
                                            '<div class="text-center py-12 text-gray-500">No channels added yet</div>' :
                                            channelsData.map(ch => `
                                                <div class="p-4 border-2 ${ch.active ? 'border-green-200 bg-green-50' : 'border-gray-200 bg-gray-50'} rounded-lg mb-3">
                                                    <div class="flex items-center justify-between">
                                                        <div class="flex-1">
                                                            <div class="flex items-center space-x-3">
                                                                <h4 class="font-semibold text-gray-800">${ch.name}</h4>
                                                                <span class="px-2 py-1 text-xs rounded-full ${ch.active ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-600'}">
                                                                    ${ch.active ? 'Active' : 'Inactive'}
                                                                </span>
                                                            </div>
                                                            <div class="mt-2 text-sm text-gray-600">
                                                                <span class="font-medium">Channel:</span> ${ch.channelId} | 
                                                                <span class="font-medium">Batch:</span> ${ch.batchId}
                                                            </div>
                                                        </div>
                                                        <div class="flex items-center space-x-2">
                                                            <button onclick="toggleChannel('${ch.id}')" 
                                                                    class="px-4 py-2 rounded-lg font-medium transition-colors ${ch.active ? 'bg-yellow-600 hover:bg-yellow-700' : 'bg-green-600 hover:bg-green-700'} text-white">
                                                                ${ch.active ? 'Disable' : 'Enable'}
                                                            </button>
                                                            <button onclick="deleteChannel('${ch.id}')" 
                                                                    class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">
                                                                Delete
                                                            </button>
                                                        </div>
                                                    </div>
                                                </div>
                                            `).join('')
                                        }
                                    </div>
                                </div>

                                <div id="content-config" style="display: none;">
                                    <div class="space-y-6">
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">Telegram Session String</label>
                                            <textarea id="telegramSession" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 h-32 focus:outline-none" 
                                                      placeholder="Enter your Telegram session string...">${configData.telegramSession || ''}</textarea>
                                            <p class="mt-2 text-sm text-gray-500">Required for bot to work as your Telegram account</p>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">PW Token</label>
                                            <input type="text" id="pwToken" value="${configData.pwToken || ''}" 
                                                   class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none" 
                                                   placeholder="Enter PW API Token">
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium text-gray-700 mb-2">STYSTRK Token</label>
                                            <input type="text" id="styStrkToken" value="${configData.styStrkToken || ''}" 
                                                   class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none" 
                                                   placeholder="Enter STYSTRK Token">
                                        </div>
                                        <button onclick="saveConfig()" class="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
                                            Save Configuration
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="bg-blue-50 border border-blue-200 rounded-lg p-6">
                            <h3 class="font-semibold text-blue-900 mb-3">How it works:</h3>
                            <ol class="list-decimal list-inside space-y-2 text-blue-800">
                                <li>Configure your Telegram session string and tokens in Configuration tab</li>
                                <li>Activate your Telegram session (green banner at top)</li>
                                <li>Add channels and map them to batch IDs</li>
                                <li>Send /check in any monitored channel</li>
                                <li>Bot will automatically process and upload lectures</li>
                                <li>5-minute cooldown between lectures</li>
                            </ol>
                        </div>
                    </div>
                </div>
            `;
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
    """Serve admin panel"""
    return render_template_string(ADMIN_PANEL_HTML)

@app.route('/api/data')
def get_data():
    """Get all data"""
    try:
        data = load_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in /api/data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/setup', methods=['POST'])
def setup():
    """Setup admin password"""
    try:
        data = load_data()
        if data['auth']:
            return jsonify({'success': False, 'error': 'Already setup'})
        
        password = request.json.get('password')
        data['auth'] = {'passwordHash': hash_password(password)}
        
        if save_data(data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save data'})
    except Exception as e:
        logger.error(f"Error in /api/setup: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Login to admin panel"""
    try:
        data = load_data()
        password = request.json.get('password')
        
        if not data['auth']:
            return jsonify({'success': False, 'error': 'Not setup'})
        
        if hash_password(password) == data['auth']['passwordHash']:
            session['authenticated'] = True
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Incorrect password'})
    except Exception as e:
        logger.error(f"Error in /api/login: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration"""
    try:
        data = load_data()
        config = request.json
        data['config'] = config
        
        if save_data(data):
            # Reload bot config if running
            global bot_instance
            if bot_instance:
                bot_instance.update_config(config)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save data'})
    except Exception as e:
        logger.error(f"Error in /api/config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/session/<action>', methods=['POST'])
def toggle_session(action):
    """Activate/deactivate Telegram session"""
    try:
        data = load_data()
        
        if action == 'activate':
            if not data['config']['telegramSession']:
                return jsonify({'success': False, 'error': 'Session string not configured'})
            
            # Import bot here to avoid issues
            try:
                from bot import PWAutoUploader
            except Exception as e:
                logger.error(f"Failed to import bot: {e}")
                return jsonify({'success': False, 'error': f'Bot import failed: {str(e)}'})
            
            # Start bot
            global bot_instance, bot_thread
            try:
                if not bot_instance:
                    api_id = os.getenv('API_ID')
                    api_hash = os.getenv('API_HASH')
                    
                    if not api_id or not api_hash:
                        return jsonify({'success': False, 'error': 'API_ID or API_HASH not configured in environment'})
                    
                    bot_instance = PWAutoUploader(
                        data['config']['telegramSession'],
                        int(api_id),
                        api_hash
                    )
                    bot_instance.update_config(data['config'])
                    bot_instance.update_channels(data['channels'])
                    
                    bot_thread = threading.Thread(target=bot_instance.run)
                    bot_thread.daemon = True
                    bot_thread.start()
                    
                    logger.info("Bot started successfully")
                
                data['session_active'] = True
                save_data(data)
                return jsonify({'success': True, 'message': 'Session activated successfully'})
                
            except Exception as e:
                logger.error(f"Failed to start bot: {e}")
                return jsonify({'success': False, 'error': f'Failed to start bot: {str(e)}'})
        
        elif action == 'deactivate':
            data['session_active'] = False
            save_data(data)
            
            # Stop bot
            if bot_instance:
                try:
                    bot_instance.stop()
                except:
                    pass
            
            return jsonify({'success': True, 'message': 'Session deactivated'})
        
        return jsonify({'success': False, 'error': 'Invalid action'})
        
    except Exception as e:
        logger.error(f"Error in /api/session: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channels', methods=['POST'])
def add_channel():
    """Add new channel"""
    try:
        data = load_data()
        channel = request.json
        data['channels'].append(channel)
        
        if save_data(data):
            # Update bot channels if running
            global bot_instance
            if bot_instance:
                bot_instance.update_channels(data['channels'])
            return jsonify({'success': True, 'channels': data['channels']})
        else:
            return jsonify({'success': False, 'error': 'Failed to save data'})
    except Exception as e:
        logger.error(f"Error in /api/channels POST: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
def delete_channel(channel_id):
    """Delete channel"""
    try:
        data = load_data()
        data['channels'] = [ch for ch in data['channels'] if ch['id'] != channel_id]
    if save_data(data):
        # Update bot channels if running
        global bot_instance
        if bot_instance:
            bot_instance.update_channels(data['channels'])
        return jsonify({'success': True, 'channels': data['channels']})
    else:
        return jsonify({'success': False, 'error': 'Failed to save data'})
except Exception as e:
    logger.error(f"Error in /api/channels DELETE: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/channels/<channel_id>/toggle', methods=['POST'])
def toggle_channel(channel_id):
"""Toggle channel status"""
try:
data = load_data()
for ch in data['channels']:
if ch['id'] == channel_id:
ch['active'] = not ch['active']
break
    if save_data(data):
        # Update bot channels if running
        global bot_instance
        if bot_instance:
            bot_instance.update_channels(data['channels'])
        return jsonify({'success': True, 'channels': data['channels']})
    else:
        return jsonify({'success': False, 'error': 'Failed to save data'})
except Exception as e:
    logger.error(f"Error in /api/channels toggle: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500
if name == 'main':
port = int(os.getenv('PORT', 5000))
app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
