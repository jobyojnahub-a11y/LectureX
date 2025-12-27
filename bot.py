import asyncio
import logging
import uuid
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import aiohttp
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PWAutoUploader:
    def __init__(self, session_string, api_id, api_hash, session_dir=None):
        # Store credentials for later client creation
        self.session_string = session_string
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = None
        self.pw_token = ""
        self.stystrk_token = ""
        self.channels = {}
        self.uploader_bot = "@url_uploder_nrbot"
        self.running = False
        self.ist = pytz.timezone('Asia/Kolkata')
        self.loop = None
        
    def update_config(self, config):
        """Update configuration"""
        self.pw_token = config.get('pwToken', '')
        self.stystrk_token = config.get('styStrkToken', '')
        logger.info("✅ Configuration updated")
        
    def update_channels(self, channels):
        """Update channel mappings"""
        self.channels = {
            ch['channelId']: {
                'batchId': ch['batchId'],
                'name': ch['name'],
                'active': ch['active']
            }
            for ch in channels if ch.get('active', False)
        }
        logger.info(f"✅ Loaded {len(self.channels)} active channels")
        
    async def start_client(self):
        """Start Telegram client"""
        # Create client in the async context
        if not self.client:
            self.client = TelegramClient(
                StringSession(self.session_string),
                self.api_id,
                self.api_hash
            )
        
        await self.client.start()
        logger.info("✅ Telegram client started successfully")
        
        @self.client.on(events.NewMessage(pattern='/check'))
        async def handle_check(event):
            await self.process_check_command(event)
            
    async def process_check_command(self, event):
        """Process /check command"""
        try:
            # Get channel ID
            chat = await event.get_chat()
            channel_id = f"@{chat.username}" if chat.username else str(chat.id)
            
            logger.info(f"📩 Received /check from channel: {channel_id}")
            
            # Check if channel is monitored
            if channel_id not in self.channels:
                logger.info(f"⚠️ Channel not monitored: {channel_id}")
                return
                
            channel_info = self.channels[channel_id]
            if not channel_info['active']:
                await event.respond("⚠️ This channel is currently inactive")
                return
                
            batch_id = channel_info['batchId']
            
            await event.respond("🔍 Checking today's schedule...")
            
            # Fetch schedule
            lectures = await self.fetch_todays_schedule(batch_id)
            
            if not lectures:
                await event.respond("❌ No lectures found for today")
                return
                
            # Filter available lectures
            available = self.filter_available_lectures(lectures)
            
            if not available:
                await event.respond("📝 No recorded or completed lectures available yet")
                return
                
            await event.respond(f"✅ Found {len(available)} lecture(s) to process")
            
            # Process each lecture
            for idx, lecture in enumerate(available, 1):
                try:
                    topic = lecture['topic']
                    await event.respond(f"🎬 Processing {idx}/{len(available)}:\n{topic}")
                    
                    success = await self.process_lecture(lecture, batch_id, channel_id, topic)
                    
                    if success:
                        await event.respond(f"✅ Lecture {idx} uploaded successfully!")
                    else:
                        await event.respond(f"❌ Failed to process lecture {idx}")
                    
                    # Cooldown between lectures
                    if idx < len(available):
                        await event.respond("⏳ Waiting 5 minutes before next lecture...")
                        await asyncio.sleep(300)  # 5 minutes
                        
                except Exception as e:
                    logger.error(f"❌ Error processing lecture {idx}: {e}")
                    await event.respond(f"❌ Error processing lecture {idx}: {str(e)}")
                    continue
                    
            await event.respond("🎉 All lectures processed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error in /check command: {e}")
            await event.respond(f"❌ Error: {str(e)}")
            
    async def fetch_todays_schedule(self, batch_id):
        """Fetch today's schedule from PW API"""
        url = f"https://api.penpencil.co/v1/batches/{batch_id}/todays-schedule"
        params = {
            "batchId": batch_id,
            "isNewStudyMaterialFlow": "true"
        }
        
        # Generate random ID for this request
        import uuid
        random_id = str(uuid.uuid4())
        
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"Bearer {self.pw_token}",
            "client-id": "5eb393ee95fab7468a79d189",
            "client-type": "WEB",
            "client-version": "1.0.0",
            "content-type": "application/json",
            "origin": "https://www.pw.live",
            "priority": "u=1, i",
            "randomid": random_id,
            "referer": "https://www.pw.live/",
            "sec-ch-ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Fetched schedule: {len(data.get('data', []))} lectures")
                        return data.get('data', [])
                    elif response.status == 429:
                        logger.error(f"❌ Rate limited! Wait before retrying. Response: {await response.text()}")
                        return []
                    else:
                        logger.error(f"❌ Failed to fetch schedule: {response.status} - {await response.text()}")
                        return []
        except Exception as e:
            logger.error(f"❌ Error fetching schedule: {e}")
            return []
                    
    def filter_available_lectures(self, lectures):
        """Filter lectures that are recorded or have ended"""
        available = []
        now = datetime.now(self.ist)
        
        for lecture in lectures:
            # Check if status is COMPLETED
            if lecture.get('status') == 'COMPLETED':
                available.append(lecture)
                continue
                
            # Check if it's a video lecture
            if lecture.get('isVideoLecture', False):
                available.append(lecture)
                continue
                
            # Check if live lecture has ended
            end_time_str = lecture.get('endTime')
            if end_time_str:
                try:
                    # Parse ISO format time
                    end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    # Convert to IST
                    end_time_ist = end_time.astimezone(self.ist)
                    
                    if now > end_time_ist:
                        available.append(lecture)
                except Exception as e:
                    logger.error(f"❌ Error parsing time: {e}")
                    
        logger.info(f"✅ Found {len(available)} available lectures")
        return available
        
    async def process_lecture(self, lecture, batch_id, channel_id, topic):
        """Process a single lecture"""
        try:
            lecture_id = lecture['_id']
            logger.info(f"🎬 Processing lecture: {lecture_id}")
            
            # Get video URL
            video_url = await self.get_video_url(batch_id, lecture_id)
            if not video_url:
                logger.error("❌ Failed to get video URL")
                return False
                
            logger.info(f"✅ Got video URL: {video_url[:100]}...")
            
            # Check if MPD URL needs conversion
            if 'master.mpd' in video_url:
                logger.info("🔄 Converting MPD to M3U8...")
                m3u8_url = await self.generate_m3u8(video_url)
                if not m3u8_url:
                    logger.error("❌ Failed to generate M3U8")
                    return False
                video_url = m3u8_url
                logger.info(f"✅ M3U8 URL: {video_url[:100]}...")
            
            # Upload via bot
            logger.info("📤 Sending to uploader bot...")
            video_message = await self.upload_via_bot(video_url)
            
            if not video_message:
                logger.error("❌ Failed to get video from uploader bot")
                return False
                
            # Forward to original channel
            logger.info(f"📨 Forwarding to channel: {channel_id}")
            await self.client.send_file(
                channel_id,
                video_message.media,
                caption=f"📚 {topic}"
            )
            
            logger.info("✅ Lecture processed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error processing lecture: {e}")
            return False
            
    async def get_video_url(self, batch_id, lecture_id):
        """Get video URL from API"""
        url = "https://video-url-details-v0.bhanuyadav.workers.dev/video-url-details"
        params = {
            "parentid": batch_id,
            "childid": lecture_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for direct video_url
                        if 'video_url' in data:
                            return data['video_url']
                            
                        # Check for url + signedUrl combination
                        if 'url' in data and 'signedUrl' in data:
                            base_url = data['url']
                            signed_params = data['signedUrl']
                            
                            # Combine URL and parameters
                            if '?' in base_url:
                                return f"{base_url}&{signed_params}"
                            else:
                                return f"{base_url}?{signed_params}"
                                
                    logger.error(f"❌ Failed to get video URL: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error getting video URL: {e}")
            return None
                
    async def generate_m3u8(self, mpd_url):
        """Convert MPD to M3U8 using spider API"""
        url = "https://spider.bhanuyadav.workers.dev/generate"
        
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://play2.bhanuyadav.workers.dev",
            "referer": "https://play2.bhanuyadav.workers.dev/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        payload = {
            "url": mpd_url
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        m3u8_url = await response.text()
                        return m3u8_url.strip()
                    else:
                        logger.error(f"❌ Failed to generate M3U8: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"❌ Error generating M3U8: {e}")
            return None
            
    async def upload_via_bot(self, video_url):
        """Send URL to uploader bot and wait for video"""
        try:
            # Send URL to uploader bot
            await self.client.send_message(self.uploader_bot, video_url)
            logger.info(f"✅ Sent URL to {self.uploader_bot}")
            
            # Wait for video response with timeout
            video_message = None
            timeout = 3600  # 1 hour
            start_time = datetime.now()
            check_count = 0
            
            while not video_message:
                check_count += 1
                # Check for new messages from bot
                async for message in self.client.iter_messages(self.uploader_bot, limit=5):
                    if message.video or message.document:
                        # Check if message is recent
                        if message.date > start_time:
                            video_message = message
                            logger.info("✅ Received video from uploader bot")
                            break
                
                # Check timeout
                elapsed = (datetime.now() - start_time).seconds
                if elapsed > timeout:
                    logger.error("❌ Timeout waiting for video from uploader bot")
                    return None
                
                # Log progress every 10 checks (~ 1.6 minutes)
                if check_count % 10 == 0:
                    logger.info(f"⏳ Still waiting for video... ({elapsed // 60} minutes elapsed)")
                    
                # Wait before checking again
                await asyncio.sleep(10)
                
            return video_message
            
        except Exception as e:
            logger.error(f"❌ Error uploading via bot: {e}")
            return None
    
    async def _run_async(self):
        """Async run method"""
        try:
            await self.start_client()
            logger.info("🤖 Bot is running and listening for /check commands...")
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ Error in async run: {e}")
        finally:
            self.running = False
            
    def run(self):
        """Run the bot - creates new event loop in thread"""
        self.running = True
        
        # Create new event loop for this thread
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Run the async method
            self.loop.run_until_complete(self._run_async())
            
        except Exception as e:
            logger.error(f"❌ Error running bot: {e}")
            self.running = False
        finally:
            if self.loop:
                self.loop.close()
            
    def stop(self):
        """Stop the bot"""
        self.running = False
        try:
            if self.client and self.client.is_connected():
                # Schedule disconnect in the bot's event loop
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
            logger.info("🛑 Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
