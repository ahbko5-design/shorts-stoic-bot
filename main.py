import os
import re
import json
import time
import random
import asyncio
import textwrap
import requests
from google import genai
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# Восстановление секретов
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON', ''))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN', ''))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

STOIC_TOPICS = [
    "control what you can, ignore the rest", 
    "embracing hardship and pain", 
    "the shortness of life (memento mori)", 
    "staying calm under pressure", 
    "mastering your emotions", 
    "disregarding the opinions of others", 
    "finding peace in solitude", 
    "daily discipline over motivation"
]

# Резервные цитаты на случай исчерпания квоты Gemini (429)
FALLBACK_SCRIPTS = [
    {
        "text": "You have power over your mind, not outside events. Realize this, and you will find strength. Subscribe to Daily Stoic Mindset for your daily dose of wisdom.",
        "image_query": "greek statue dark fog",
        "title": "Master Your Mind 🏛️ #shorts #stoicism #wisdom #philosophy",
        "tags": ["Stoicism", "Philosophy", "Wisdom", "Mindset", "Shorts"]
    },
    {
        "text": "We suffer more often in imagination than in reality. Stay grounded in the present. Subscribe to Daily Stoic Mindset for your daily dose of wisdom.",
        "image_query": "dark mountain solitude landscape",
        "title": "Overthinking Kills Peace 🏛️ #shorts #stoicism #mindset",
        "tags": ["Stoicism", "Philosophy", "Wisdom", "Mindset", "Shorts"]
    },
    {
        "text": "Waste no more time arguing about what a good man should be. Be one. Subscribe to Daily Stoic Mindset for your daily dose of wisdom.",
        "image_query": "marcus aurelius statue rain",
        "title": "Stop Talking, Start Being 🏛️ #shorts #stoicism #discipline",
        "tags": ["Stoicism", "Philosophy", "Wisdom", "Mindset", "Shorts"]
    }
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(STOIC_TOPICS)
    
    prompt = f"""
    Write a UNIQUE, powerful 20-second Stoic lesson.
    TOPIC: {selected_topic}.
    Random seed number: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Deep, impactful, philosophical text.
    - END WITH: "Subscribe to Daily Stoic Mindset for your daily dose of wisdom."
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_query": "single search keyword for stock photo like statue, dark nature, mountain, fog, rain, forest",
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
            raw = response.text
            start = raw.find('{')
            end = raw.rfind('}') + 1
            return json.loads(raw[start:end])
        except Exception as e:
            err_msg = str(e)
            match = re.search(r"retryDelay': '(\d+)s'", err_msg)
            wait_time = int(match.group(1)) + 2 if match else 35
            print(f"⚠️ Ошибка Gemini (429/Квота). Попытка {attempt + 1}/5. Ждём {wait_time} сек...")
            time.sleep(wait_time)
            
    print("⚠️ Квота Gemini исчерпана. Используем резервную стоическую мудрость...")
    return random.choice(FALLBACK_SCRIPTS)

async def create_audio(text):
    # Глубокий мужской баритон для философичности
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("audio.mp3")

def download_pexels_image(query):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    photos = res.get("photos", [])
    if not photos:
        res = requests.get("https://api.pexels.com/v1/search?query=statue&per_page=10&orientation=portrait", headers=headers).json()
        photos = res.get("photos", [])

    selected = random.choice(photos)
    image_url = selected["src"]["large2x"]
    
    with open("stoic_bg.jpg", "wb") as f:
        f.write(requests.get(image_url).content)
    print("📸 Атмосферный фон стоицизма скачан!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    target_w, target_h = 1080, 1920

    # 1. Пропорциональный Crop-to-Fill в PIL (без растяжения пропорций)
    img = Image.open("stoic_bg.jpg").convert("RGB")
    orig_w, orig_h = img.size

    scale = max(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    bg_canvas = img_resized.crop((left, top, left + target_w, top + target_h))

    # 2. Отрисовка текста белым с черной обводкой по центру
    draw = ImageDraw.Draw(bg_canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    except:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(script_text, width=22)
    line_height = 75
    y_text = int(target_h * 0.32)

    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) / 2

        # Черный контрастный контур
        for adj in [(-3,0), (3,0), (0,-3), (0,3), (-3,-3), (3,3), (-3,3), (3,-3)]:
            draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

        # Белый философский текст
        draw.text((x, y_text), line, font=font, fill="white")
        y_text += line_height

    bg_canvas.save("final_frame.jpg")

    # 3. Анимация плавного Zoom-In и сведение
    img_clip = ImageClip("final_frame.jpg").set_duration(duration)
    img_animated = img_clip.resize(lambda t: 1 + 0.04 * t).set_position(('center', 'center'))

    final_clip = CompositeVideoClip([img_animated], size=(target_w, target_h))
    final_clip = final_clip.set_audio(audio)
    
    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    audio.close()

def upload_to_youtube(metadata):
    from google.oauth2.credentials import Credentials
    
    creds = Credentials.from_authorized_user_file('token.json', ["https://www.googleapis.com/auth/youtube.upload"])
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    description_text = (
        f"{metadata['text']}\n\n"
        f"🏛️ Daily Stoic wisdom to keep you disciplined.\n"
        f"🔔 Subscribe to Daily Stoic Mindset for more daily philosophy!\n\n"
        f"#shorts #stoicism #philosophy #mindset #wisdom"
    )

    body = {
        'snippet': {
            'title': metadata['title'],
            'description': description_text,
            'tags': metadata['tags'],
            'categoryId': '27'
        },
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }

    media = MediaFileUpload("final_short.mp4", mimetype="video/mp4", resumable=False)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print(f"✅ СТОИЧЕСКИЙ РОЛИК ОПУБЛИКОВАН! ID: {response.get('id')}")

if __name__ == "__main__":
    print("1. Генерируем стоический сценарий...")
    data = get_script()
    print("2. Озвучиваем глубоким голосом...")
    asyncio.run(create_audio(data['text']))
    print("3. Ищем атмосферную картинку...")
    download_pexels_image(data['image_query'])
    print("4. Собираем 9:16 видео с текстом и Zoom-эффектом...")
    build_video(data['text'])
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
