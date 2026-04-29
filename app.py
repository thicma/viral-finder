from flask import Flask, render_template, request, jsonify
import scrapetube
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_views(view_str):
    if not view_str:
        return 0
    view_str = view_str.lower().split(" view")[0].split(" visualiza")[0].strip()
    if 'k' in view_str or 'mil' in view_str:
        val = view_str.replace('k', '').replace('mil', '').strip().replace(',', '.')
        try: return int(float(val) * 1000)
        except: return 0
    elif 'm' in view_str or 'mi' in view_str:
        val = view_str.replace('m', '').replace('mi', '').strip().replace(',', '.')
        try: return int(float(val) * 1_000_000)
        except: return 0
    else:
        val = "".join(c for c in view_str if c.isdigit())
        try: return int(val) if val else 0
        except: return 0

def parse_hours(time_str):
    if not time_str:
        return 999_999
    s = time_str.lower()
    m = re.search(r'\d+', s)
    num = int(m.group()) if m else 1
    if "second" in s or "segundo" in s: return max(num / 3600, 0.01)
    if "minute" in s or "minuto" in s: return max(num / 60, 0.01)
    if "hour" in s or "hora" in s: return num
    if "day" in s or "dia" in s: return num * 24
    if "week" in s or "semana" in s: return num * 168
    if "month" in s or "mês" in s or "mes" in s: return num * 720
    if "year" in s or "ano" in s: return num * 8_760
    return 999_999

# ── Subscriber scraper ────────────────────────────────────────────────────────
import requests as _req
import threading

_sub_cache = {}   # {"/@ChannelHandle": 12300}
_cache_lock = threading.Lock()

def parse_subscribers(sub_str):
    """Convert '2.67M subscribers' or '413K subscribers' to int.
    Expects standard en-US format (commas = thousands, dots = decimal).
    """
    if not sub_str:
        return 0
    s = sub_str.lower().replace('subscribers', '').replace('subscriber', '').strip()
    s = s.replace(',', '')

    m = re.search(r'([\d\.]+)\s*([kmb])?', s)
    if not m:
        return 0
    try:
        num = float(m.group(1))
        unit = m.group(2)
        if unit == 'b': return int(num * 1_000_000_000)
        if unit == 'm': return int(num * 1_000_000)
        if unit == 'k': return int(num * 1_000)
        return int(num)
    except:
        return 0

def fetch_subscribers(channel_url):
    """Fetch subscriber count from a YouTube channel's /about page.
    Parses ytInitialData JSON → pageHeaderRenderer → metadataRows.
    """
    with _cache_lock:
        if channel_url in _sub_cache:
            return _sub_cache[channel_url]

    try:
        full_url = f"https://www.youtube.com{channel_url}/about"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        r = _req.get(full_url, headers=headers, timeout=10)

        subs = 0
        yt_match = re.search(r'var ytInitialData = (\{.+?\});', r.text)
        if yt_match:
            import json as _json
            data = _json.loads(yt_match.group(1))
            header = data.get('header', {}).get('pageHeaderRenderer', {})
            if header:
                content = header.get('content', {}).get('pageHeaderViewModel', {})
                metadata = content.get('metadata', {}).get('contentMetadataViewModel', {})
                rows = metadata.get('metadataRows', [])
                for row in rows:
                    for part in row.get('metadataParts', []):
                        text = part.get('text', {}).get('content', '')
                        if 'subscriber' in text.lower():
                            subs = parse_subscribers(text)
                            break
                    if subs > 0:
                        break

            # Fallback: old c4TabbedHeaderRenderer
            if subs == 0:
                c4 = data.get('header', {}).get('c4TabbedHeaderRenderer', {})
                sub_text = c4.get('subscriberCountText', {}).get('simpleText', '')
                if sub_text:
                    subs = parse_subscribers(sub_text)

        with _cache_lock:
            _sub_cache[channel_url] = subs
        return subs
    except:
        return 0

# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def search_viral():
    """Unified search: scrape videos → fetch subscriber counts in parallel → return
    each result with Outlier Score AND Views/Subs ratio in a single response."""
    import math
    from concurrent.futures import ThreadPoolExecutor

    data    = request.json
    keyword = data.get('keyword', '').strip()
    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400

    try:
        gen = scrapetube.get_search(keyword, limit=200)
        raw_results = []

        for v in gen:
            try:
                title         = v.get('title', {}).get('runs', [{}])[0].get('text', '')
                video_id      = v.get('videoId', '')
                published_str = v.get('publishedTimeText', {}).get('simpleText', '')
                views_str     = v.get('viewCountText', {}).get('simpleText', '')
                owner         = v.get('ownerText', {}).get('runs', [{}])[0].get('text', '')
                channel_url   = (v.get('shortBylineText', {})
                                  .get('runs', [{}])[0]
                                  .get('navigationEndpoint', {})
                                  .get('browseEndpoint', {})
                                  .get('canonicalBaseUrl', ''))
                thumbnail     = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                views = parse_views(views_str)
                hours = parse_hours(published_str)

                if views < 10_000:
                    continue

                vph     = round(views / hours, 1) if hours > 0 else views
                outlier = round(views / math.sqrt(max(hours, 1)), 1)

                raw_results.append({
                    "id": video_id, "title": title, "channel": owner,
                    "channel_url": channel_url,
                    "views": views, "views_str": views_str,
                    "published": published_str, "hours": hours,
                    "vph": vph, "outlier": outlier,
                    "thumbnail": thumbnail,
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                })
            except Exception:
                continue

        # Fetch subscriber counts in parallel (one request per unique channel)
        unique_channels = list({r['channel_url'] for r in raw_results if r['channel_url']})

        def fetch_one(ch_url):
            fetch_subscribers(ch_url)

        with ThreadPoolExecutor(max_workers=8) as ex:
            ex.map(fetch_one, unique_channels)

        # Enrich every result with subscriber data + ratio
        for r in raw_results:
            subs = _sub_cache.get(r['channel_url'], 0)
            ratio = round(r['views'] / subs, 2) if subs > 0 else 0

            if ratio >= 20:   tier = "ultra"
            elif ratio >= 10: tier = "high"
            elif ratio >= 3:  tier = "medium"
            else:             tier = ""

            subs_str = (f"{subs/1_000_000:.1f}M" if subs >= 1_000_000
                        else f"{subs/1_000:.1f}K" if subs >= 1_000
                        else str(subs)) if subs else "N/A"

            r.update({"subscribers": subs, "subs_str": subs_str,
                       "ratio": ratio, "tier": tier})

        # Default sort by Outlier Score
        raw_results.sort(key=lambda x: x['outlier'], reverse=True)
        return jsonify({"results": raw_results[:50], "total": len(raw_results)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/analyze', methods=['POST'])
def analyze_script():
    """Single-shot Gemini call: script + reference images → viral title structures + visual strategy."""
    data = request.json
    script = data.get('script', '').strip()
    niche  = data.get('niche', 'English learning for Brazilian Portuguese speakers').strip()
    references = data.get('references', [])

    if not script:
        return jsonify({"error": "Script is required"}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    # Build the base prompt
    prompt = f"""You are an elite YouTube viral title strategist and visual director with deep expertise in the "{niche}" niche.

TASK: Analyze the video script below. If reference images and titles are provided, analyze their visual patterns, hook structures, and psychological triggers. Generate 7 viral title structures and 1 comprehensive visual strategy for the thumbnail that mimics the successful elements of the references.

SCRIPT:
\"\"\"
{script}
\"\"\"

RULES:
- Every title MUST be in English.
- Each title must use a distinct psychological formula (curiosity gap, fear, aspiration, social proof, controversy, how-to, listicle, etc.).
- Titles should be concise (ideally under 65 characters) but impactful.
- Avoid clickbait with no substance; each title must be honest to the script.
- If references are provided, your titles MUST mimic their structural formatting (e.g., ALL CAPS usage, punctuation, curiosity gaps).
- The visual_strategy must describe exactly how to compose a thumbnail (colors, expressions, layout, text) that fits the reference aesthetic.

RESPONSE FORMAT (valid JSON only, no extra text):
{{
  "core_topic": "<one-sentence summary of what the script is really about>",
  "avatar_pain": "<the single biggest pain/desire this script addresses>",
  "visual_strategy": "<Detailed prompt for a designer (or Midjourney) to generate a thumbnail mimicking the exact visual style, colors, composition, and psychological triggers seen in the provided reference thumbnails (or best practices if none provided).>",
  "titles": [
    {{
      "title": "<the viral title>",
      "formula": "<formula name, e.g. 'Curiosity Gap + Number'>",
      "emotional_trigger": "<e.g. fear / curiosity / aspiration / relief / social proof>",
      "hook_score": <integer 1-10>,
      "why_it_works": "<one sentence explanation>",
      "thumb_text": "<1 to 5 bold words to overlay on the thumbnail that COMPLEMENT (not repeat) the title>"
    }}
  ]
}}"""

    # Prepare multimodal contents
    contents = [prompt]
    
    if references:
        import io
        import PIL.Image
        import requests as _req
        
        contents.append("\n\n--- REFERENCE VIRAL VIDEOS ---\nStudy these successful titles and thumbnails carefully:")
        for ref in references:
            title = ref.get('title', 'Unknown Title')
            thumb_url = ref.get('thumbnail', '')
            contents.append(f"Reference Title: {title}")
            
            if thumb_url:
                try:
                    # Download thumbnail high-res if possible
                    url = thumb_url.replace('mqdefault', 'maxresdefault')
                    r = _req.get(url, timeout=5)
                    if r.status_code == 404 or len(r.content) < 5000:
                        r = _req.get(thumb_url, timeout=5) # fallback to mqdefault
                    if r.status_code == 200:
                        img = PIL.Image.open(io.BytesIO(r.content))
                        contents.append(img)
                except Exception as e:
                    print(f"Failed to load image {thumb_url}: {e}")

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(contents)
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw)
        return jsonify(result)
    except json.JSONDecodeError as je:
        return jsonify({"error": f"Failed to parse Gemini response as JSON: {str(je)}", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
