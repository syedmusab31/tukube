import os, glob, sqlite3, ffmpeg
from yt_dlp import YoutubeDL
from groq import Groq
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

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
            # Check DB to prevent downloading duplicates
            if not cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,)).fetchone():
                print(f"Downloading new video ID: {vid_id}")
                dl_opts = {'outtmpl': 'input.mp4'}
                YoutubeDL(dl_opts).download([entry['url']])
                
                cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
                conn.commit()
                return entry.get('title', '')
    return None

# 2. TRIM TO 58s & OVERLAY AUDIO
def edit_video():
    probe = ffmpeg.probe('input.mp4')
    duration = float(probe['format']['duration'])
    max_duration = 58.0 if duration > 60 else duration

    music_files = glob.glob('music/*.mp3')
    audio_track = music_files[0] if music_files else None

    video = ffmpeg.input('input.mp4', t=max_duration)
    
    if audio_track:
        audio = ffmpeg.input(audio_track, t=max_duration)
        ffmpeg.output(video.video, audio.audio, 'final_short.mp4').run(overwrite_output=True)
    else:
        # Strip audio if no custom track is provided
        ffmpeg.output(video.video, 'final_short.mp4', an=None).run(overwrite_output=True)

# 3. GENERATE SEO METADATA USING GROQ API
def generate_metadata(caption):
    # Initializes using GROQ_API_KEY environment variable
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    system_prompt = (
        "You are an expert YouTube Shorts algorithm specialist. "
        "Create viral, high-CTR titles and descriptions based on video captions."
    )
    user_prompt = f"""
    Create YouTube Shorts metadata for this TikTok video caption: '{caption}'.
    
    Strict Rules:
    1. Title must be catchy, engaging, under 90 characters, and include 1 emoji.
    2. Description must be concise and end with relevant hashtags including #Shorts.
    
    Your output MUST follow this exact format:
    TITLE: <your title here>
    DESCRIPTION: <your description here>
    """
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    response_text = completion.choices[0].message.content
    
    # Parse title and description
    title = response_text.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
    description = response_text.split("DESCRIPTION:")[1].strip()
    
    return title, description

# 4. UPLOAD TO YOUTUBE
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
        edit_video()
        title, description = generate_metadata(caption)
        print(f"Generated Title: {title}")
        print(f"Generated Description:\n{description}")
        upload_to_youtube(title, description)
    else:
        print("No new videos found to process.")