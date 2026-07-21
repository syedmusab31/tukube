import os, glob, sqlite3, ffmpeg
from yt_dlp import YoutubeDL
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL") # E.g., https://www.tiktok.com/@username

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
        # If no music found, strip audio entirely
        ffmpeg.output(video.video, 'final_short.mp4', an=None).run(overwrite_output=True)

# 3. GENERATE SEO METADATA
def generate_metadata(caption):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"Create catchy YouTube Shorts metadata for this video caption: '{caption}'. Output format:\nTITLE: <max 90 chars title>\nDESCRIPTION: <short description with #Shorts>"
    response = model.generate_content(prompt).text
    
    title = response.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
    description = response.split("DESCRIPTION:")[1].strip()
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
        upload_to_youtube(title, description)
    else:
        print("No new videos found to process.")