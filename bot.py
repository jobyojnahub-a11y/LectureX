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
        self.uploader_bot = "@Torrent_Leech_Pro_Bot"
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
            
            # Send initial message and store it
            status_msg = await event.respond("🔍 **Checking Today's Schedule...**")
            temp_messages = [status_msg]
            
            # Fetch schedule
            lectures = await self.fetch_todays_schedule(batch_id)
            
            if not lectures:
                await status_msg.edit("❌ **No lectures found for today**")
                await asyncio.sleep(3)
                await status_msg.delete()
                return
                
            # Filter available lectures
            available = self.filter_available_lectures(lectures)
            
            if not available:
                await status_msg.edit("📝 **No recorded or completed lectures available yet**")
                await asyncio.sleep(3)
                await status_msg.delete()
                return
            
            # Update status
            await status_msg.edit(f"✅ **Found {len(available)} Lecture(s)**\n\n⏳ Starting processing...")
            
            # Process each lecture
            for idx, lecture in enumerate(available, 1):
                try:
                    # Get lecture details
                    topic = lecture.get('topic', 'Untitled Lecture')
                    subject = lecture.get('subjectId', {}).get('name', 'General')
                    
                    # Update status for this lecture
                    processing_msg = await event.respond(
                        f"🎬 **Processing Lecture {idx}/{len(available)}**\n\n"
                        f"📚 **Subject:** `{subject}`\n"
                        f"📖 **Topic:** `{topic}`\n\n"
                        f"⏳ Please wait..."
                    )
                    temp_messages.append(processing_msg)
                    
                    success = await self.process_lecture(lecture, batch_id, channel_id, topic, subject)
                    
                    if success:
                        await processing_msg.edit(
                            f"✅ **Lecture {idx} Uploaded Successfully!**\n\n"
                            f"📚 **Subject:** `{subject}`\n"
                            f"📖 **Topic:** `{topic}`"
                        )
                        # Delete after 5 seconds
                        await asyncio.sleep(5)
                        await processing_msg.delete()
                        temp_messages.remove(processing_msg)
                    else:
                        await processing_msg.edit(
                            f"❌ **Failed to process Lecture {idx}**\n\n"
                            f"📚 **Subject:** `{subject}`\n"
                            f"📖 **Topic:** `{topic}`"
                        )
                        # Delete after 5 seconds
                        await asyncio.sleep(5)
                        await processing_msg.delete()
                        temp_messages.remove(processing_msg)
                    
                    # Cooldown between lectures
                    if idx < len(available):
                        cooldown_msg = await event.respond(
                            f"⏸️ **Cooldown Period**\n\n"
                            f"⏳ Waiting 5 minutes before next lecture...\n"
                            f"📊 Progress: **{idx}/{len(available)}** completed"
                        )
                        temp_messages.append(cooldown_msg)
                        await asyncio.sleep(300)  # 5 minutes
                        await cooldown_msg.delete()
                        temp_messages.remove(cooldown_msg)
                        
                except Exception as e:
                    logger.error(f"❌ Error processing lecture {idx}: {e}")
                    error_msg = await event.respond(
                        f"❌ **Error Processing Lecture {idx}**\n\n"
                        f"⚠️ `{str(e)}`"
                    )
                    temp_messages.append(error_msg)
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    temp_messages.remove(error_msg)
                    continue
            
            # Final success message
            final_msg = await event.respond(
                f"🎉 **All Lectures Processed!**\n\n"
                f"✅ Successfully uploaded **{len(available)}** lecture(s)\n"
                f"📚 Check above for the videos"
            )
            
            # Delete all temporary messages
            for msg in temp_messages:
                try:
                    await msg.delete()
                except:
                    pass
            
            # Delete final message after 10 seconds
            await asyncio.sleep(10)
            try:
                await final_msg.delete()
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Error in /check command: {e}")
            await event.respond(f"❌ **Error:** `{str(e)}`")
            
    async def fetch_todays_schedule(self, batch_id):
        """Fetch today's schedule from StudyMaxer API"""
        url = f"https://studymaxer.bhanuyadav.workers.dev/todays-schedule"
        params = {
            "batchId": batch_id
        }
        
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://studymaxer.bhanuyadav.workers.dev",
            "referer": "https://studymaxer.bhanuyadav.workers.dev/",
            "sec-ch-ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        lectures = data.get('data', [])
                        logger.info(f"✅ Fetched schedule: {len(lectures)} lectures")
                        return lectures
                    elif response.status == 429:
                        logger.error(f"❌ Rate limited! Wait before retrying.")
                        return []
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to fetch schedule: {response.status} - {error_text}")
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
        
    async def process_lecture(self, lecture, batch_id, channel_id, topic, subject):
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
            
            # Clean topic for filename (remove special characters)
            clean_topic = topic.replace('/', '-').replace('\\', '-').replace(':', '-').replace('|', '-')
            
            # Upload via bot with title
            logger.info("📤 Sending to uploader bot...")
            video_message = await self.upload_via_bot(video_url, clean_topic)
            
            if not video_message:
                logger.error("❌ Failed to get video from uploader bot")
                return False
            
            # Create beautiful caption
            caption = (
                f"📚 **{subject}**\n\n"
                f"📖 **{topic}**\n\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Quality: Best Available\n"
                f"📥 Ready to Watch"
            )
            
            # Forward to original channel WITHOUT sender name
            logger.info(f"📨 Forwarding to channel: {channel_id}")
            
            # Send as new message with caption (removes sender info)
            await self.client.send_file(
                channel_id,
                video_message.media,
                caption=caption
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
        
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://video-url-details-v0.bhanuyadav.workers.dev",
            "referer": "https://video-url-details-v0.bhanuyadav.workers.dev/",
            "sec-ch-ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Check if response has success field
                        if result.get('success'):
                            data = result.get('data', {})
                        else:
                            data = result
                        
                        # Check for direct video_url
                        if 'video_url' in data:
                            logger.info(f"✅ Got direct video_url")
                            return data['video_url']
                            
                        # Check for url + signedUrl combination
                        if 'url' in data and 'signedUrl' in data:
                            base_url = data['url']
                            signed_params = data['signedUrl']
                            
                            # Remove leading ? if present in signedUrl
                            if signed_params.startswith('?'):
                                signed_params = signed_params[1:]
                            
                            # Combine URL and parameters
                            if '?' in base_url:
                                final_url = f"{base_url}&{signed_params}"
                            else:
                                final_url = f"{base_url}?{signed_params}"
                            
                            logger.info(f"✅ Combined URL with signed parameters")
                            return final_url
                        
                        logger.error(f"❌ Unexpected response format: {result}")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to get video URL: {response.status} - {error_text}")
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
            
    async def upload_via_bot(self, video_url, lecture_title):
        """Send URL to Torrent Leech Pro Bot and wait for video"""
        try:
            # Format command: /yl URL -n Title
            command = f"/yl {video_url} -n {lecture_title}"
            
            logger.info(f"📤 Sending to {self.uploader_bot}")
            await self.client.send_message(self.uploader_bot, command)
            
            # Wait for quality selection buttons
            await asyncio.sleep(8)
            logger.info("⏳ Waiting for quality selection...")
            
            # Get the latest message with buttons
            button_message = None
            async for message in self.client.iter_messages(self.uploader_bot, limit=10):
                if message.reply_markup and "Choose Video Quality" in (message.text or ""):
                    button_message = message
                    logger.info(f"✅ Found quality selection message")
                    break
            
            if not button_message:
                logger.error("❌ No quality buttons found")
                # Try to find any message with buttons
                async for message in self.client.iter_messages(self.uploader_bot, limit=10):
                    if message.reply_markup:
                        button_message = message
                        logger.info(f"✅ Found message with buttons: {message.text[:50] if message.text else 'No text'}")
                        break
            
            if not button_message or not button_message.reply_markup:
                logger.error("❌ Still no buttons found")
                return None
            
            # Get all buttons from reply_markup
            try:
                from telethon.tl.types import KeyboardButtonCallback
                
                buttons = button_message.reply_markup.rows
                logger.info(f"📋 Found {len(buttons)} button rows")
                
                # Search for "Best Video" button
                best_video_found = False
                for row_idx, row in enumerate(buttons):
                    for button in row.buttons:
                        button_text = button.text if hasattr(button, 'text') else str(button)
                        logger.info(f"🔘 Button found: {button_text}")
                        
                        if 'Best Video' in button_text or 'best video' in button_text.lower():
                            logger.info(f"✅ Found 'Best Video' button, clicking...")
                            
                            # Click using callback_query
                            await button_message.click(data=button.data)
                            best_video_found = True
                            break
                    
                    if best_video_found:
                        break
                
                if not best_video_found:
                    logger.error("❌ Could not find 'Best Video' button")
                    logger.info("📋 Available buttons:")
                    for row in buttons:
                        for button in row.buttons:
                            logger.info(f"   - {button.text if hasattr(button, 'text') else str(button)}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Error clicking button: {e}")
                return None
            
            logger.info("⏳ Download and upload started, tracking progress...")
            
            # Track progress and wait for final video
            video_message = None
            timeout = 10800  # 3 hours for large files
            
            # Make start_time timezone aware (UTC)
            import pytz
            start_time = datetime.now(pytz.UTC)
            
            last_progress = ""
            check_interval = 20
            check_count = 0
            last_check_time = start_time
            
            while not video_message:
                check_count += 1
                current_time = datetime.now(pytz.UTC)
                
                # Check for new messages
                found_progress = False
                async for message in self.client.iter_messages(self.uploader_bot, limit=20):
                    msg_text = message.text or ""
                    
                    # Check if this is a progress message
                    if "┃" in msg_text and ("Download" in msg_text or "Upload" in msg_text or "Processed:" in msg_text):
                        # Extract progress info
                        progress_info = self.extract_progress(msg_text)
                        if progress_info and progress_info != last_progress:
                            logger.info(f"📊 {progress_info}")
                            last_progress = progress_info
                            found_progress = True
                            last_check_time = current_time  # Update last activity time
                    
                    # Check if this is the final video
                    if message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type):
                        # Check if it's after our command
                        if message.date > start_time:
                            # Make sure it's not a thumbnail or small file
                            file_size = message.document.size if message.document else (message.video.size if message.video else 0)
                            if file_size > 5 * 1024 * 1024:  # At least 5MB
                                video_message = message
                                logger.info(f"✅ Received video! Size: {file_size / (1024*1024):.2f}MB")
                                break
                
                if video_message:
                    break
                
                # Check timeout from last activity
                elapsed_total = (current_time - start_time).total_seconds()
                elapsed_since_activity = (current_time - last_check_time).total_seconds()
                
                # If no activity for 30 minutes, timeout
                if elapsed_since_activity > 1800:
                    logger.error(f"❌ No activity for 30 minutes. Last progress: {last_progress}")
                    return None
                
                # Total timeout
                if elapsed_total > timeout:
                    logger.error(f"❌ Total timeout ({timeout//60} minutes). Last progress: {last_progress}")
                    return None
                
                # Log status every 5 checks (~ 1.5 minutes)
                if check_count % 5 == 0:
                    minutes_elapsed = int(elapsed_total // 60)
                    logger.info(f"⏳ Processing... {minutes_elapsed} min elapsed. Last: {last_progress or 'Waiting...'}")
                
                # Wait before checking again
                await asyncio.sleep(check_interval)
            
            return video_message
            
        except Exception as e:
            logger.error(f"❌ Error uploading via bot: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def extract_progress(self, text):
        """Extract progress information from bot message"""
        try:
            lines = text.split('\n')
            progress_bar = ""
            processed = ""
            status = ""
            
            for line in lines:
                if '┃' in line and '[' in line and ']' in line:
                    # Extract progress bar
                    start = line.find('[')
                    end = line.find(']')
                    if start != -1 and end != -1:
                        progress_bar = line[start:end+1]
                        # Also get percentage
                        if '%' in line:
                            pct_start = line.find(']') + 1
                            pct_end = line.find('%', pct_start) + 1
                            progress_bar += " " + line[pct_start:pct_end].strip()
                
                elif '┠ Processed:' in line:
                    processed = line.replace('┠ Processed:', '').strip()
                
                elif '┠ Status:' in line:
                    status = line.replace('┠ Status:', '').strip()
            
            if progress_bar:
                result = progress_bar
                if processed:
                    result += f" | {processed}"
                if status:
                    result += f" | {status}"
                return result
            
            return None
        except:
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
