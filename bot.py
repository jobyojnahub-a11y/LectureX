import asyncio
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient, events
import aiohttp
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PWAutoUploader:
    def __init__(self, session_string, api_id, api_hash):
        self.client = TelegramClient(
            session_string,
            api_id,
            api_hash
        )
        self.pw_token = ""
        self.stystrk_token = ""
        self.channels = {}
        self.uploader_bot = "@url_uploder_nrbot"
        self.running = False
        self.ist = pytz.timezone('Asia/Kolkata')
        
    def update_config(self, config):
        """Update configuration"""
        self.pw_token = config.get('pwToken', '')
        self.stystrk_token = config.get('styStrkToken', '')
        logger.info("Configuration updated")
        
    def update_channels(self, channels):
        """Update channel mappings"""
        self.channels = {
            ch['channelId']: {
                'batchId': ch['batchId'],
                'name': ch['name'],
