import os
import json
import time
import requests
import asyncio
from google import genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# 1. Восстановление конфигов из секретов GitHub
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON'))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN'))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# --- СЦЕНАРИЙ (СТОИЦИЗМ) ---
def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(STOIC_TOPICS)
    
    prompt = f"""
    Write a UNIQUE 20-second powerful Stoic lesson.
    TOPIC: {selected_topic}.
    Random seed number: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Deep, impactful, philosophical text.
    - END WITH: "Subscribe to Daily Stoic Mindset for your daily dose of wisdom."
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "query": "single search keyword for stock video like statue, dark nature, mountain, fog, rain",
      "title": "Stoic Rule for Hard Times 🏛️ #shorts #stoicism #wisdom",
      "tags": ["Stoicism", "Philosophy", "Wisdom", "Mindset", "Shorts"]
    }}
    """
    
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} не удалась ({e}). Ждем 15 секунд...")
            time.sleep(15)
            
    raise Exception("❌ Не удалось получить ответ от Gemini.")
