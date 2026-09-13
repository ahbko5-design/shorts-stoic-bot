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

DARK_STOIC_TOPICS = [
    "memento mori and human insignificance",
    "crying over things you cannot control",
    "overthinking while the universe does not care",
    "seeking approval from idiots",
    "wasting life on social media algorithms",
    "stressing about money on a floating space rock",
    "expecting life to be fair",
    "worrying about opinions of people who will be dead soon"
]

FALLBACK_SCRIPTS = [
    {
        "text": "You are stressing about a text message while standing on a giant rock spinning through a void. Marcus Aurelius is laughing at you. Memento mori, human.",
        "image_query": "marcus aurelius statue dark",
        "title": "Stoic Reality Check 🏛️💀 #shorts #stoicism #darkhumor #philosophy",
        "tags": ["Stoicism", "DarkHumor", "Philosophy", "Wisdom", "Shorts"]
    },
    {
        "text": "Worrying about what people think of you? Good news: they will all be dead soon. Bad news: so will you. Control what you can, ignore the rest.",
        "image_query": "greek statue fog rain",
        "title": "Nobody Cares, Memento Mori 🏛️💀 #shorts #stoicism #mindset",
        "tags": ["Stoicism", "DarkHumor", "Philosophy", "Wisdom", "Shorts"]
    }
]

def get_script():
    client = genai.Client(api_key=GEMINI_API_KEY)
    selected_topic = random.choice(DARK_STOIC_TOPICS)
    
    prompt = f"""
    Write a short, punchy Stoic lesson with heavy DARK HUMOR, cynicism, and brutal honesty (2 sentences max).
    TOPIC: {selected_topic}.
    Random seed number: {random.randint(1000, 9999)}
    
    Voiceover guidelines:
    - Deep, sarcastic, brutally realistic, philosophical.
    - END WITH: "Subscribe for your daily dose of brutal Stoic reality."
    
    Return ONLY a JSON object:
    {{
      "text": "The full spoken text of the video without markdown or emojis",
      "image_query": "statue OR dark mountain OR rain forest OR fog landscape OR skull statue",
      "title": "Dark Stoic Wisdom 🏛️💀 #shorts #stoicism #darkhumor #philosophy",
      "tags": ["Stoicism", "DarkHumor", "Philosophy", "Wisdom", "Shorts"]
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
            
    print("⚠️ Квота Gemini исчерпана. Берем резервный черный стоический мем...")
    return random.choice(FALLBACK_SCRIPTS)

async def create_audio(text):
    # Глубокий саркастичный мужской голос
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="-5%", pitch="-3Hz")
    await communicate.save("audio.mp3")

def download_pexels_image(query):
    headers = {"Authorization": PEXELS_API_KEY}
    random_page = random.randint(1, 10)
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&page={random_page}&orientation=portrait"
    
    try:
        res = requests.get(url, headers=headers).json()
        photos = res.get("photos", [])
    except Exception:
        photos = []

    if not photos:
        backup_queries = ["statue", "dark nature", "mountain fog", "ancient ruins", "rain dark"]
        fallback_q = random.choice(backup_queries)
        random_page = random.randint(1, 8)
        url = f"https://api.pexels.com/v1/search?query={fallback_q}&per_page=15&page={random_page}&orientation=portrait"
        res = requests.get(url, headers=headers).json()
        photos = res.get("photos", [])

    selected = random.choice(photos)
    image_url = selected["src"]["large2x"]
    
    with open("stoic_bg.jpg", "wb") as f:
        f.write(requests.get(image_url).content)
    print("📸 Атмосферный фоновый визуал скачан!")

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    duration = audio.duration
    target_w, target_h = 1080, 1920

    # Пропорциональный Crop-to-Fill в PIL (заполняем 9:16 без растяжения)
    img = Image.open("stoic_bg.jpg").convert("RGB")
    orig_w, orig_h = img.size

    scale = max(target_w / orig_w, target_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    bg_canvas = img_resized.crop((left, top, left + target_w, top + target_h))

    # Наложение текста прямо на картинку через PIL
    draw = ImageDraw.Draw(bg_canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
    except:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(script_text, width=22)
    line_height = 75
    y_text = int(target_h * 0.32)

    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) / 2

        # Чёрная контрастная обводка
        for adj in [(-4,0), (4,0), (0,-4), (0,4), (-4,-4), (4,4), (-4,4), (4,-4)]:
            draw.text((x + adj[0], y_text + adj[1]), line, font=font, fill="black")

        # Белый философский текст
        draw.text((x, y_text), line, font=font, fill="white")
        y_text += line_height

    bg_canvas.save("final_frame.jpg")

    # Анимация Zoom-In и сборка
    img_clip = ImageClip("final_frame.jpg").set_duration(duration)
    img_animated = img_clip.resize(lambda t: 1 + 0.03 * t).set_position(('center', 'center'))

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
        f"🏛️ Brutal Stoic wisdom & dark humor for modern humans.\n"
        f"🔔 Subscribe for your daily dose of Stoic reality!\n\n"
        f"#shorts #stoicism #darkhumor #philosophy #wisdom"
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
    print(f"✅ ЧЕРНЫЙ СТОИЧЕСКИЙ РОЛИК ОПУБЛИКОВАН! ID: {response.get('id')}")

if __name__ == "__main__":
    print("1. Генерируем циничный стоический мем...")
    data = get_script()
    print("2. Озвучиваем глубоким голосом...")
    asyncio.run(create_audio(data['text']))
    print("3. Скачиваем атмосферный случайный визуал с Pexels...")
    download_pexels_image(data['image_query'])
    print("4. Собираем 9:16 видео с субтитрами...")
    build_video(data['text'])
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
