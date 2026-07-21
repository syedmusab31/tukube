# import os, glob, sqlite3, ffmpeg
# from yt_dlp import YoutubeDL
# from groq import Groq
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload

# TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

# # 1. DOWNLOAD TIKTOK & DE-DUPLICATE
# def fetch_video():
#     conn = sqlite3.connect('videos.db')
#     cursor = conn.cursor()
#     cursor.execute("CREATE TABLE IF NOT EXISTS posted (id TEXT PRIMARY KEY)")
    
#     ydl_opts = {'extract_flat': True, 'quiet': True}
#     with YoutubeDL(ydl_opts) as ydl:
#         info = ydl.extract_info(TIKTOK_PROFILE_URL, download=False)
#         for entry in info.get('entries', []):
#             vid_id = entry['id']
#             # Check DB to prevent downloading duplicates
#             if not cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,)).fetchone():
#                 print(f"Downloading new video ID: {vid_id}")
#                 dl_opts = {'outtmpl': 'input.mp4'}
#                 YoutubeDL(dl_opts).download([entry['url']])
                
#                 cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
#                 conn.commit()
#                 return entry.get('title', '')
#     return None

# # 2. TRIM TO 58s & OVERLAY AUDIO
# def edit_video():
#     probe = ffmpeg.probe('input.mp4')
#     duration = float(probe['format']['duration'])
#     max_duration = 58.0 if duration > 60 else duration

#     music_files = glob.glob('music/*.mp3')
#     audio_track = music_files[0] if music_files else None

#     video = ffmpeg.input('input.mp4', t=max_duration)
    
#     if audio_track:
#         audio = ffmpeg.input(audio_track, t=max_duration)
#         ffmpeg.output(video.video, audio.audio, 'final_short.mp4').run(overwrite_output=True)
#     else:
#         # Strip audio if no custom track is provided
#         ffmpeg.output(video.video, 'final_short.mp4', an=None).run(overwrite_output=True)

# # 3. GENERATE SEO METADATA USING GROQ API
# def generate_metadata(caption):
#     # Initializes using GROQ_API_KEY environment variable
#     client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
#     system_prompt = (
#         "You are an expert YouTube Shorts algorithm specialist. "
#         "Create viral, high-CTR titles and descriptions based on video captions."
#     )
#     user_prompt = f"""
#     Create YouTube Shorts metadata for this TikTok video caption: '{caption}'.
    
#     Strict Rules:
#     1. Title must be catchy, engaging, under 90 characters, and include 1 emoji.
#     2. Description must be concise and end with relevant hashtags including #Shorts.
    
#     Your output MUST follow this exact format:
#     TITLE: <your title here>
#     DESCRIPTION: <your description here>
#     """
    
#     completion = client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_prompt}
#         ],
#         temperature=0.7
#     )
    
#     response_text = completion.choices[0].message.content
    
#     # Parse title and description
#     title = response_text.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
#     description = response_text.split("DESCRIPTION:")[1].strip()
    
#     return title, description

# # 4. UPLOAD TO YOUTUBE
# def upload_to_youtube(title, description):
#     creds = Credentials(
#         token=None,
#         refresh_token=os.getenv("YT_REFRESH_TOKEN"),
#         token_uri="https://oauth2.googleapis.com/token",
#         client_id=os.getenv("YT_CLIENT_ID"),
#         client_secret=os.getenv("YT_CLIENT_SECRET")
#     )
#     youtube = build('youtube', 'v3', credentials=creds)
    
#     body = {
#         'snippet': {'title': title, 'description': description, 'categoryId': '22'},
#         'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
#     }
    
#     media = MediaFileUpload('final_short.mp4', chunksize=-1, resumable=True)
#     youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
#     print("Video successfully published to YouTube Shorts!")

# if __name__ == "__main__":
#     caption = fetch_video()
#     if caption is not None:
#         edit_video()
#         title, description = generate_metadata(caption)
#         print(f"Generated Title: {title}")
#         print(f"Generated Description:\n{description}")
#         upload_to_youtube(title, description)
#     else:
#         print("No new videos found to process.")

import os, glob, sqlite3, ffmpeg, asyncio
from yt_dlp import YoutubeDL
from groq import Groq
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

# --- SETTINGS ---
# Choices: 'en-US-ChristopherNeural' (Male), 'en-US-AvaNeural' (Female), 'en-US-EricNeural' (Male)
VOICE_SPEAKER = "en-US-ChristopherNeural"  

# 1. DOWNLOAD TIKTOK & DE-DUPLICATE
def fetch_video():
    conn = sqlite3.connect('videos.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS posted (id TEXT PRIMARY KEY)")
    
    ydl_opts = {'extract_flat': True, 'quiet': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(TIKTOK_PROFILE_URL, download=False)
        for entry in info.get('entries', []):
            vid_id = entry['id']
            if not cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,)).fetchone():
                print(f"Downloading new video ID: {vid_id}")
                dl_opts = {'outtmpl': 'input.mp4'}
                YoutubeDL(dl_opts).download([entry['url']])
                
                cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
                conn.commit()
                return entry.get('title', '')
    return None

# 2. GENERATE SCRIPT ACCORDING TO VIDEO DURATION (GROQ)
def generate_voice_script(caption, target_duration):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    # Estimate words: Average speaking speed is ~2.5 words per second
    target_words = int(target_duration * 2.3)
    
    prompt = f"""
    Create an engaging, storytelling voiceover script based on this TikTok video context: '{caption}'.
    
    STRICT RULES:
    1. The speech MUST take exactly around {target_duration:.0f} seconds to read out loud.
    2. Keep the word count strictly around {target_words} words.
    3. Do NOT include any parenthetical actions or markdown like (Host says:) or **bold**.
    4. Write plain text only.
    """
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return completion.choices[0].message.content.strip()

# 3. GENERATE TTS AUDIO FILE (EDGE-TTS)
async def generate_tts_file(text, output_file="voice.mp3"):
    communicate = edge_tts.Communicate(text, VOICE_SPEAKER)
    await communicate.save(output_file)

# 4. EDIT VIDEO & MIX AUDIO (FFMPEG)
def edit_video(script_text):
    probe = ffmpeg.probe('input.mp4')
    duration = float(probe['format']['duration'])
    max_duration = 58.0 if duration > 60 else duration

    # A. Generate Voiceover File using Async loop
    asyncio.run(generate_tts_file(script_text, "voice.mp3"))

    # B. Visual Transformation Filter Chain
    # - 3% Crop
    # - Scale back to 1080x1920
    # - 1.02x Speed up
    # - Contrast 1.04, Brightness 0.01
    # - Draw Bottom Banner "Follow for daily updates"
    video = (
        ffmpeg
        .input('input.mp4', t=max_duration)
        .crop('iw*0.03', 'ih*0.03', 'iw*0.94', 'ih*0.94')
        .filter('scale', 1080, 1920)
        .filter('setpts', '0.98*PTS') # 1.02x Speed Ramp
        .filter('eq', contrast=1.04, brightness=0.01)
        .drawtext(
            text="Follow for daily updates",
            x='(w-text_w)/2',
            y='h-120',
            fontsize=42,
            fontcolor='white',
            box=1,
            boxcolor='black@0.6',
            boxborderw=15
        )
    )

    # C. Audio Mixing Setup (Voiceover 100% + Background Music 10%)
    music_files = glob.glob('music/*.mp3') + glob.glob('music/*.MP3')
    voice_input = ffmpeg.input('voice.mp3', t=max_duration).filter('volume', 1.0)

    if music_files:
        bg_music = ffmpeg.input(music_files[0], stream_loop=-1, t=max_duration).filter('volume', 0.10)
        # Mix 100% Voiceover + 10% Music together
        audio_mixed = ffmpeg.filter([voice_input, bg_music], 'amix', inputs=2)
    else:
        audio_mixed = voice_input

    # D. Render Final Output
    ffmpeg.output(video, audio_mixed, 'final_short.mp4', acodec='aac', vcodec='libx264').run(overwrite_output=True)

# 5. GENERATE YOUTUBE SEO METADATA (GROQ)
def generate_metadata(caption):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    prompt = f"""
    Create YouTube Shorts metadata for caption: '{caption}'.
    FORMAT:
    TITLE: <catchy title under 90 chars with emoji>
    DESCRIPTION: <short description with #Shorts>
    """
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    
    res = completion.choices[0].message.content
    title = res.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
    description = res.split("DESCRIPTION:")[1].strip()
    
    # Add Disclaimer to Description
    disclaimer = "\n\n---\nDisclaimer: Educational & Entertainment commentary with original AI voiceover and custom editing under Fair Use."
    return title, description + disclaimer

# 6. UPLOAD TO YOUTUBE
def upload_to_youtube(title, description):
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YT_CLIENT_ID"),
        client_secret=os.getenv("YT_CLIENT_SECRET")
    )
    youtube = build('youtube', 'v3', credentials=creds)
    
    body = {
        'snippet': {'title': title, 'description': description, 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    
    media = MediaFileUpload('final_short.mp4', chunksize=-1, resumable=True)
    youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    print("Video successfully published to YouTube Shorts!")

if __name__ == "__main__":
    caption = fetch_video()
    if caption is not None:
        # Get video duration to sync script word count
        probe = ffmpeg.probe('input.mp4')
        duration = float(probe['format']['duration'])
        max_duration = 58.0 if duration > 60 else duration
        
        print("1. Generating Voiceover Script matched to video duration...")
        script = generate_voice_script(caption, max_duration)
        
        print("2. Processing Video Editing & Audio Mixing...")
        edit_video(script)
        
        print("3. Generating YouTube SEO Metadata...")
        title, description = generate_metadata(caption)
        
        print("4. Uploading to YouTube...")
        upload_to_youtube(title, description)
    else:
        print("No new videos found to process.")