import scrapetube
import os
import requests
import re
from concurrent.futures import ThreadPoolExecutor

CHANNEL_URL = "https://www.youtube.com/@SpeakEnglishWithClass/videos"
FOLDER = "SpeakEnglish_Timeline"
HTML_FILE = f"{FOLDER}_Grid.html"

os.makedirs(FOLDER, exist_ok=True)
print(f"Fetching videos from {CHANNEL_URL}...")
videos = list(scrapetube.get_channel(channel_url=CHANNEL_URL))
print(f"Found {len(videos)} videos.")

# Prepare data
video_data = []
for i, v in enumerate(videos):
    title = v.get('title', {}).get('runs', [{}])[0].get('text', 'No Title')
    vid = v.get('videoId', '')
    pub = v.get('publishedTimeText', {}).get('simpleText', '')
    views = v.get('viewCountText', {}).get('simpleText', '')
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    safe_title = safe_title[:80] # Avoid overly long filenames
    filename = f"{i+1:03d} - {safe_title}.jpg"
    filepath = os.path.join(FOLDER, filename)
    
    video_data.append({
        'index': i + 1,
        'title': title,
        'vid': vid,
        'pub': pub,
        'views': views,
        'filepath': filepath
    })

def download_thumb(item):
    vid = item['vid']
    filepath = item['filepath']
    
    # Maxresdefault is 1280x720. If not available, fallback to hqdefault
    urls = [
        f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
    ]
    
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and len(r.content) > 5000: # Exclude broken images
                with open(filepath, "wb") as f:
                    f.write(r.content)
                return True
        except:
            pass
    return False

print(f"Downloading {len(videos)} thumbnails in parallel...")
with ThreadPoolExecutor(max_workers=10) as executor:
    executor.map(download_thumb, video_data)
print("Downloads finished!")

# Generate HTML
html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Timeline: @SpeakEnglishWithClass</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f11; color: white; padding: 40px; margin: 0; }}
        h1 {{ text-align: center; color: #f59e0b; margin-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #a1a1aa; margin-bottom: 40px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 24px; max-width: 1600px; margin: 0 auto; }}
        .card {{ background: #1a1a1f; border-radius: 12px; overflow: hidden; border: 1px solid #333; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-4px); border-color: #f59e0b; }}
        .card img {{ width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; border-bottom: 1px solid #333; }}
        .info {{ padding: 16px; }}
        .title {{ font-size: 15px; font-weight: 600; line-height: 1.4; margin-bottom: 12px; color: #e4e4e7; }}
        .meta {{ font-size: 13px; color: #9ca3af; display: flex; justify-content: space-between; align-items: center; }}
        .views {{ color: #60a5fa; font-weight: 500; background: rgba(96, 165, 250, 0.1); padding: 4px 8px; border-radius: 6px; }}
        .index-badge {{ background: #f59e0b; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 6px; }}
    </style>
</head>
<body>
    <h1>🎬 Timeline History</h1>
    <div class="subtitle">Channel: @SpeakEnglishWithClass (Newest to Oldest)</div>
    <div class="grid">
"""

for item in video_data:
    html_content += f"""
        <div class="card">
            <img src="{item['filepath']}" loading="lazy">
            <div class="info">
                <div class="title"><span class="index-badge">#{item['index']}</span> {item['title']}</div>
                <div class="meta">
                    <span>📅 {item['pub']}</span>
                    <span class="views">👁️ {item['views']}</span>
                </div>
            </div>
        </div>
    """

html_content += """
    </div>
</body>
</html>
"""

with open(HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Generated timeline grid: {HTML_FILE}")
