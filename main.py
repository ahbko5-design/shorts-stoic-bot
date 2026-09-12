import os
import json
import time
import random
import requests
import asyncio
from google import genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload

# Восстановление секретов
if not os.path.exists('client_secret.json'):
    with open('client_secret.json', 'w') as f:
        f.write(os.getenv('CLIENT_SECRET_JSON'))

if not os.path.exists('token.json'):
    with open('token.json', 'w') as f:
        f.write(os.getenv('YOUTUBE_TOKEN'))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

STOIC_TOPICS = [
    "control what you can, ignore the rest", "embracing hardship and pain", 
    "the shortness of life (memento mori)", "staying calm under pressure", 
    "mastering your emotions", "disregarding the opinions of others", 
    "finding peace in solitude", "daily discipline over motivation"
]

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

async def create_audio(text):
    communicate = edge_tts.Communicate(text, "en-US-EricNeural")
    await communicate.save("audio.mp3")

def download_pexels_video(query):
    headers = {"Authorization": PEXELS_API_KEY}
    random_page = random.randint(1, 5)
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=15&page={random_page}&orientation=portrait"
    res = requests.get(url, headers=headers).json()
    
    videos = res.get("videos", [])
    if not videos:
        res = requests.get("https://api.pexels.com/videos/search?query=statue&per_page=10&orientation=portrait", headers=headers).json()
        videos = res.get("videos", [])

    selected_video = random.choice(videos)
    video_url = selected_video["video_files"][0]["link"]
    
    with open("background.mp4", "wb") as f:
        f.write(requests.get(video_url).content)

def build_video(script_text):
    audio = AudioFileClip("audio.mp3")
    video = VideoFileClip("background.mp4")

    if video.duration < audio.duration:
        video = video.loop(duration=audio.duration)
    else:
        video = video.subclip(0, audio.duration)

    video = video.set_audio(audio)

    # Добавление субтитров по центру
    try:
        txt_clip = (TextClip(
                        txt=script_text, 
                        fontsize=36, 
                        color='white', 
                        font='DejaVu-Sans-Bold',
                        stroke_color='black',
                        stroke_width=2,
                        method='caption',
                        size=(int(video.w * 0.85), None)
                    )
                    .set_position(('center', 'center'))
                    .set_duration(audio.duration))

        final_clip = CompositeVideoClip([video, txt_clip])
    except Exception as e:
        print(f"⚠️ Ошибка субтитров: {e}. Монтируем без текста.")
        final_clip = video

    final_clip.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")
    audio.close()
    video.close()

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
    print(f"✅ ВИДЕО ОПУБЛИКОВАНО! ID: {response.get('id')}")

# 🚀 ТОЧКА ВХОДА — Запуск выполнения всей цепочки
if __name__ == "__main__":
    print("1. Генерируем сценарий...")
    data = get_script()
    print("2. Озвучиваем...")
    asyncio.run(create_audio(data['text']))
    print("3. Скачиваем фон с Pexels...")
    download_pexels_video(data['query'])
    print("4. Собираем видео и накладываем субтитры...")
    build_video(data['text'])
    print("5. Загружаем на YouTube...")
    upload_to_youtube(data)
