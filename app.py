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

# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def search_viral():
    import math
    data      = request.json
    keyword   = data.get('keyword', '').strip()
    max_hours = int(data.get('max_hours', 0))   # 0 = all time
    if not keyword:
        return jsonify({"error": "Keyword is required"}), 400
    try:
        gen = scrapetube.get_search(keyword, limit=200)
        results = []
        for v in gen:
            try:
                title         = v.get('title', {}).get('runs', [{}])[0].get('text', '')
                video_id      = v.get('videoId', '')
                published_str = v.get('publishedTimeText', {}).get('simpleText', '')
                views_str     = v.get('viewCountText', {}).get('simpleText', '')
                owner         = v.get('ownerText', {}).get('runs', [{}])[0].get('text', '')
                thumbnail     = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                views = parse_views(views_str)
                hours = parse_hours(published_str)

                # Period filter: skip videos older than chosen window
                if max_hours > 0 and hours > max_hours:
                    continue

                if views >= 10_000:
                    # VPH — raw, can inflate very new videos
                    vph = round(views / hours, 1) if hours > 0 else views

                    # Outlier Score (vidIQ-style):
                    # views / sqrt(hours) gives a balanced signal:
                    # a 1-week-old video with 100k views scores higher than
                    # a 5-year-old video with 500k views, but a 1-hour-old
                    # video with 200 views doesn't dominate.
                    outlier = round(views / math.sqrt(max(hours, 1)), 1)

                    results.append({
                        "id": video_id, "title": title, "channel": owner,
                        "views": views, "views_str": views_str,
                        "published": published_str, "hours": hours,
                        "vph": vph, "outlier": outlier,
                        "thumbnail": thumbnail,
                        "url": f"https://www.youtube.com/watch?v={video_id}"
                    })
            except Exception:
                continue

        # Rank by Outlier Score
        results.sort(key=lambda x: x['outlier'], reverse=True)
        return jsonify({"results": results[:50], "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Subscriber scraper ────────────────────────────────────────────────────────
import requests as _req
import threading

_sub_cache = {}   # {"/@ChannelHandle": 12300}
_cache_lock = threading.Lock()

def parse_subscribers(sub_str):
    """Convert '1.23M subscribers' → 1230000"""
    if not sub_str:
        return 0
    s = sub_str.lower().replace('subscribers', '').replace('subscriber', '').strip()
    s = s.replace(',', '.')
    try:
        if 'b' in s: return int(float(s.replace('b','').strip()) * 1_000_000_000)
        if 'm' in s: return int(float(s.replace('m','').strip()) * 1_000_000)
        if 'k' in s: return int(float(s.replace('k','').strip()) * 1_000)
        return int(float(''.join(c for c in s if c.isdigit() or c == '.')))
    except:
        return 0

def fetch_subscribers(channel_url):
    """Fetch subscriber count for a YouTube channel URL (e.g. '/@Handle')."""
    with _cache_lock:
        if channel_url in _sub_cache:
            return _sub_cache[channel_url]

    try:
        full_url = f"https://www.youtube.com{channel_url}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        r = _req.get(full_url, headers=headers, timeout=8)
        # YouTube embeds subscriber count in the page JSON
        match = re.search(r'"subscriberCountText":\{"simpleText":"([^"]+)"', r.text)
        if not match:
            match = re.search(r'"subscriberCountText":\{"accessibility":\{"accessibilityData":\{"label":"([^"]+)"', r.text)
        subs = parse_subscribers(match.group(1)) if match else 0
        with _cache_lock:
            _sub_cache[channel_url] = subs
        return subs
    except:
        return 0


@app.route('/api/channel-outliers', methods=['POST'])
def channel_outliers():
    """Search videos then enrich each with channel subscriber count.
    Ranks by Views/Subscribers ratio to surface small channels with huge reach.
    Multiple videos from the same channel are kept — they validate the THEME."""
    import math
    from concurrent.futures import ThreadPoolExecutor

    data      = request.json
    keyword   = data.get('keyword', '').strip()
    max_hours = int(data.get('max_hours', 0))
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
                # Extract canonical channel URL (e.g. /@Handle or /channel/ID)
                channel_url   = (v.get('shortBylineText', {})
                                  .get('runs', [{}])[0]
                                  .get('navigationEndpoint', {})
                                  .get('browseEndpoint', {})
                                  .get('canonicalBaseUrl', ''))
                thumbnail     = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                views = parse_views(views_str)
                hours = parse_hours(published_str)

                if max_hours > 0 and hours > max_hours:
                    continue
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
            fetch_subscribers(ch_url)   # result goes into _sub_cache

        with ThreadPoolExecutor(max_workers=8) as ex:
            ex.map(fetch_one, unique_channels)

        # Enrich results with subscriber data + ratio
        enriched = []
        for r in raw_results:
            subs = _sub_cache.get(r['channel_url'], 0)
            if subs > 0:
                ratio = round(r['views'] / subs, 2)
            else:
                ratio = 0

            # Tier label
            if ratio >= 20:   tier = "🔥🔥🔥"
            elif ratio >= 10: tier = "🔥🔥"
            elif ratio >= 3:  tier = "🔥"
            else:             tier = ""

            subs_str = (f"{subs/1_000_000:.1f}M" if subs >= 1_000_000
                        else f"{subs/1_000:.1f}K" if subs >= 1_000
                        else str(subs)) if subs else "N/A"

            r.update({"subscribers": subs, "subs_str": subs_str,
                       "ratio": ratio, "tier": tier})
            enriched.append(r)

        # Rank by ratio descending (best outliers first)
        enriched.sort(key=lambda x: x['ratio'], reverse=True)
        return jsonify({"results": enriched[:50], "total": len(enriched)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/analyze', methods=['POST'])
def analyze_script():
    """Single-shot Gemini call: script → viral title structures (all in English)."""
    data = request.json
    script = data.get('script', '').strip()
    niche  = data.get('niche', 'English learning for Brazilian Portuguese speakers').strip()
    if not script:
        return jsonify({"error": "Script is required"}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    # Build the single prompt (everything in English)
    prompt = f"""You are an elite YouTube viral title strategist with deep expertise in the "{niche}" niche.

TASK: Analyze the video script below and generate 7 viral title structures optimized for maximum click-through rate on YouTube.

SCRIPT:
\"\"\"
{script}
\"\"\"

RULES:
- Every title MUST be in English.
- Each title must use a distinct psychological formula (curiosity gap, fear, aspiration, social proof, controversy, how-to, listicle, etc.).
- Titles should be concise (ideally under 65 characters) but impactful.
- Avoid clickbait with no substance; each title must be honest to the script.

RESPONSE FORMAT (valid JSON only, no extra text):
{{
  "core_topic": "<one-sentence summary of what the script is really about>",
  "avatar_pain": "<the single biggest pain/desire this script addresses>",
  "titles": [
    {{
      "title": "<the viral title>",
      "formula": "<formula name, e.g. 'Curiosity Gap + Number'>",
      "emotional_trigger": "<e.g. fear / curiosity / aspiration / relief / social proof>",
      "hook_score": <integer 1-10>,
      "why_it_works": "<one sentence explanation>",
      "thumb_text": "<1 to 5 bold words to overlay on the thumbnail that COMPLEMENT (not repeat) the title — should create curiosity or reinforce the emotional hook visually>"
    }}
  ]
}}"""

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
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
