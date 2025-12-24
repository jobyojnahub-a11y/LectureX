"""
Telegram Session String Generator
Run this once to get your session string
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

print("=" * 50)
print("Telegram Session String Generator")
print("=" * 50)

API_ID = input("Enter your API_ID: ")
API_HASH = input("Enter your API_HASH: ")

print("\nGenerating session string...")
print("You will receive a code on Telegram. Enter it when prompted.\n")

with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
    print("\n" + "=" * 50)
    print("Your Session String:")
    print("=" * 50)
    session_string = client.session.save()
    print(session_string)
    print("=" * 50)
    print("\nSave this string securely!")
    print("You'll need it in the admin panel.")
