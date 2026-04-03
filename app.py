"""
GEOSCOPE — Geopolitical News Aggregator
Main Flask application
"""

import os, json, time, hashlib, threading, logging
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
import feedparser
import anthropic

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Anthropic client (lazy — only if key present) ────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ── In-memory article store ──────────────────────────────
# { article_id: { ...article data... } }
ARTICLES: dict = {}
LAST_FETCH: float = 0
FETCH_INTERVAL = 1800  # 30 minutes
fetch_lock = threading.Lock()

# ── RSS Feed Sources ──────────────────────────────────────
RSS_FEEDS = [
    # USA
    {"country": "usa", "flag": "🇺🇸", "source": "Foreign Policy",     "lang": "en", "url": "https://foreignpolicy.com/feed/"},
    {"country": "usa", "flag": "🇺🇸", "source": "Council on Foreign Relations", "lang": "en", "url": "https://www.cfr.org/rss/all"},
    # UK
    {"country": "uk",  "flag": "🇬🇧", "source": "The Guardian World", "lang": "en", "url": "https://www.theguardian.com/world/rss"},
    {"country": "uk",  "flag": "🇬🇧", "source": "BBC World",          "lang": "en", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    # France
    {"country": "fr",  "flag": "🇫🇷", "source": "Le Monde",           "lang": "fr", "url": "https://www.lemonde.fr/rss/une.xml"},
    {"country": "fr",  "flag": "🇫🇷", "source": "France 24",          "lang": "fr", "url": "https://www.france24.com/fr/rss"},
    # Germany
    {"country": "de",  "flag": "🇩🇪", "source": "Deutsche Welle",     "lang": "de", "url": "https://rss.dw.com/rdf/rss-de-all"},
    {"country": "de",  "flag": "🇩🇪", "source": "Spiegel International","lang":"de", "url": "https://www.spiegel.de/international/index.rss"},
    # Spain
    {"country": "es",  "flag": "🇪🇸", "source": "El País",            "lang": "es", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"},
    {"country": "es",  "flag": "🇪🇸", "source": "El Mundo",           "lang": "es", "url": "https://www.elmundo.es/rss/portada.xml"},
    # China (English editions for accessibility)
    {"country": "cn",  "flag": "🇨🇳", "source": "Xinhua English",     "lang": "zh", "url": "https://www.xinhuanet.com/english/rss/worldrss.xml"},
    {"country": "cn",  "flag": "🇨🇳", "source": "SCMP World",         "lang": "zh", "url": "https://www.scmp.com/rss/91/feed"},
]

# Geopolitics keywords for filtering
GEO_KEYWORDS = [
    "war", "conflict", "sanctions", "diplomacy", "NATO", "UN", "treaty",
    "military", "trade", "tariff", "nuclear", "election", "summit", "crisis",
    "geopolit", "ukraine", "russia", "china", "israel", "iran", "taiwan",
    "guerre", "krieg", "guerra", "conflit", "sanction", "traité",
    "diplomatique", "militaire", "élection", "crise", "外交", "战争", "制裁",
    "security", "alliance", "missile", "ceasefire", "occupation", "invasion",
    "refugee", "border", "sovereignty", "coalition", "parliament", "minister",
]

TOPIC_KEYWORDS = {
    "trade":    ["trade", "tariff", "sanction", "export", "import", "wto", "commerce", "économie", "handel", "商业", "关税"],
    "ukraine":  ["ukraine", "russia", "kyiv", "moscow", "zelensky", "putin", "nato", "donetsk", "ceasefire"],
    "mideast":  ["israel", "gaza", "hamas", "lebanon", "iran", "syria", "iraq", "saudi", "yemen", "middle east", "moyen-orient"],
    "climate":  ["climate", "cop", "emissions", "carbon", "renewable", "fossil", "green deal", "climat", "klima"],
    "tech":     ["semiconductor", "chip", "ai", "artificial intelligence", "tech", "huawei", "nvidia", "taiwan", "cyber"],
}

SENTIMENT_RULES = {
    "critical": ["attack", "condemn", "reject", "fail", "crisis", "threat", "danger", "condemns", "slams", "批评", "critica", "critique"],
    "alarm":    ["warn", "warning", "risk", "escalat", "concern", "alarm", "alert", "danger", "risque", "warnung"],
    "positive": ["agree", "deal", "peace", "progress", "success", "cooperation", "hope", "accord", "Einigung"],
    "neutral":  [],
}

# ── Helpers ───────────────────────────────────────────────

def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def detect_sentiment(text: str) -> tuple[str, str]:
    t = text.lower()
    for sent, words in SENTIMENT_RULES.items():
        if any(w in t for w in words):
            labels = {"critical": "CRITICAL", "alarm": "ALERT", "positive": "POSITIVE", "neutral": "ANALYSIS"}
            return sent, labels[sent]
    return "neutral", "ANALYSIS"

def detect_topic(text: str) -> str:
    t = text.lower()
    scores = {topic: sum(1 for kw in kws if kw in t) for topic, kws in TOPIC_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "trade"

def is_geopolitical(text: str) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in GEO_KEYWORDS)

def time_ago(published) -> str:
    try:
        if hasattr(published, 'tm_hour'):
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
        else:
            pub_dt = datetime.now(timezone.utc)
        delta = datetime.now(timezone.utc) - pub_dt
        h = int(delta.total_seconds() // 3600)
        if h < 1:   return "just now"
        if h == 1:  return "1h ago"
        if h < 24:  return f"{h}h ago"
        return f"{h // 24}d ago"
    except Exception:
        return "recently"

# ── AI Translation ────────────────────────────────────────

LANG_NAMES = {"en": "English", "it": "Italian", "fr": "French", "de": "German", "es": "Spanish", "zh": "Chinese"}
TARGET_LANGS = ["en", "it", "fr", "de", "es", "zh"]

def translate_article(text: str, source_lang: str) -> dict:
    """Translate text to all 6 languages. Returns dict {lang: translated_text}"""
    if not ai_client:
        return {lang: text for lang in TARGET_LANGS}

    targets = [l for l in TARGET_LANGS if l != source_lang]
    target_str = ", ".join(f"{LANG_NAMES[l]} ({l})" for l in targets)

    prompt = f"""Translate the following news excerpt into these languages: {target_str}.
Return ONLY a valid JSON object with language codes as keys and translations as values.
No preamble, no markdown, no explanation.

Text to translate:
{text[:400]}"""

    try:
        resp = ai_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        result[source_lang] = text
        return result
    except Exception as e:
        log.warning(f"Translation failed: {e}")
        return {lang: text for lang in TARGET_LANGS}

# ── RSS Fetching ──────────────────────────────────────────

def fetch_feed(feed_cfg: dict) -> list[dict]:
    """Fetch and parse a single RSS feed, return list of article dicts."""
    articles = []
    try:
        parsed = feedparser.parse(feed_cfg["url"])
        for entry in parsed.entries[:6]:  # max 6 per feed
            title   = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link    = entry.get("link", "")
            pub     = entry.get("published_parsed", None)

            # Basic geopolitics filter
            combined = f"{title} {summary}"
            if not is_geopolitical(combined):
                continue

            aid = article_id(link)
            sentiment, sent_label = detect_sentiment(combined)
            topic = detect_topic(combined)

            # Clean summary (strip HTML tags simply)
            import re
            clean_summary = re.sub(r'<[^>]+>', '', summary)[:300]

            articles.append({
                "id":         aid,
                "country":    feed_cfg["country"],
                "flag":       feed_cfg["flag"],
                "source":     feed_cfg["source"],
                "lang":       feed_cfg["lang"],
                "title":      title,
                "summary":    clean_summary,
                "link":       link,
                "published":  time_ago(pub),
                "sentiment":  sentiment,
                "sentLabel":  sent_label,
                "topic":      topic,
                "translated": {},
            })
    except Exception as e:
        log.warning(f"Feed error {feed_cfg['source']}: {e}")
    return articles

def group_stories(articles: list[dict]) -> list[dict]:
    """Group articles by topic into comparative stories."""
    from collections import defaultdict
    by_topic = defaultdict(list)
    for a in articles:
        by_topic[a["topic"]].append(a)

    TOPIC_META = {
        "trade":   {"icon": "⚖️",  "category": {"en":"TRADE WAR","it":"GUERRA COMMERCIALE","fr":"GUERRE COMMERCIALE","de":"HANDELSKRIEG","es":"GUERRA COMERCIAL","zh":"贸易战"}},
        "ukraine": {"icon": "🕊️", "category": {"en":"UKRAINE WAR","it":"GUERRA IN UCRAINA","fr":"GUERRE EN UKRAINE","de":"UKRAINE-KRIEG","es":"GUERRA EN UCRANIA","zh":"乌克兰战争"}},
        "mideast": {"icon": "🌍",  "category": {"en":"MIDDLE EAST","it":"MEDIO ORIENTE","fr":"MOYEN-ORIENT","de":"NAHER OSTEN","es":"ORIENTE MEDIO","zh":"中东"}},
        "climate": {"icon": "🌱",  "category": {"en":"CLIMATE","it":"CLIMA","fr":"CLIMAT","de":"KLIMA","es":"CLIMA","zh":"气候"}},
        "tech":    {"icon": "💻",  "category": {"en":"TECH RIVALRY","it":"RIVALITÀ TECH","fr":"RIVALITÉ TECH","de":"TECH-RIVALITÄT","es":"RIVALIDAD TECH","zh":"科技竞争"}},
    }

    stories = []
    for topic, cards in by_topic.items():
        if not cards:
            continue
        meta = TOPIC_META.get(topic, {"icon":"📰","category":{"en":topic.upper()}})
        # Use the most recent/prominent article for headline
        lead = cards[0]
        stories.append({
            "id":       f"story-{topic}-{int(time.time())}",
            "topic":    topic,
            "icon":     meta["icon"],
            "category": meta["category"],
            "headline": {"en": lead["title"]},
            "summary":  {"en": lead["summary"]},
            "cards":    [{
                "country":    c["country"],
                "flag":       c["flag"],
                "source":     c["source"],
                "sentiment":  c["sentiment"],
                "sentLabel":  c["sentLabel"],
                "headline":   c["title"],
                "excerpt":    c["summary"],
                "time":       c["published"],
                "original":   c["lang"].upper(),
                "link":       c["link"],
                "translated": c.get("translated", {}),
            } for c in cards[:6]],
        })
    return stories

def fetch_all_news():
    """Main fetch cycle: get all feeds, translate, store."""
    global ARTICLES, LAST_FETCH
    log.info("Starting news fetch cycle…")
    raw_articles = []

    for feed in RSS_FEEDS:
        arts = fetch_feed(feed)
        raw_articles.extend(arts)
        time.sleep(0.5)  # be polite to servers

    log.info(f"Fetched {len(raw_articles)} geopolitical articles")

    # Translate new articles
    new_articles = {}
    for art in raw_articles:
        aid = art["id"]
        if aid in ARTICLES:
            new_articles[aid] = ARTICLES[aid]  # keep cached
            continue
        # Translate
        if ai_client and art["summary"]:
            log.info(f"Translating: {art['title'][:50]}…")
            art["translated"] = translate_article(art["summary"], art["lang"])
        new_articles[aid] = art

    with fetch_lock:
        ARTICLES = new_articles
        LAST_FETCH = time.time()

    log.info(f"Fetch cycle complete. {len(ARTICLES)} articles in store.")

def background_fetcher():
    """Runs in a daemon thread, fetches news periodically."""
    while True:
        try:
            fetch_all_news()
        except Exception as e:
            log.error(f"Fetch cycle error: {e}")
        time.sleep(FETCH_INTERVAL)

# ── API Routes ────────────────────────────────────────────

@app.route("/api/stories")
def api_stories():
    """Return grouped stories for the frontend."""
    with fetch_lock:
        arts = list(ARTICLES.values())
    stories = group_stories(arts)
    return jsonify({
        "stories":    stories,
        "count":      len(arts),
        "last_fetch": datetime.fromtimestamp(LAST_FETCH, tz=timezone.utc).isoformat() if LAST_FETCH else None,
        "next_fetch": datetime.fromtimestamp(LAST_FETCH + FETCH_INTERVAL, tz=timezone.utc).isoformat() if LAST_FETCH else None,
    })

@app.route("/api/ticker")
def api_ticker():
    """Return latest headlines for the ticker."""
    with fetch_lock:
        arts = sorted(ARTICLES.values(), key=lambda a: a.get("published",""), reverse=False)[:20]
    ticker = [{"flag": a["flag"], "source": a["source"], "title": a["title"]} for a in arts]
    return jsonify(ticker)

@app.route("/api/status")
def api_status():
    return jsonify({
        "status":       "ok",
        "articles":     len(ARTICLES),
        "last_fetch":   LAST_FETCH,
        "ai_enabled":   ai_client is not None,
        "feeds":        len(RSS_FEEDS),
    })

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Manual refresh trigger (admin use)."""
    secret = request.headers.get("X-Admin-Secret","")
    if secret != os.environ.get("ADMIN_SECRET","changeme"):
        return jsonify({"error": "unauthorized"}), 401
    threading.Thread(target=fetch_all_news, daemon=True).start()
    return jsonify({"status": "fetch started"})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return "OK", 200

# ── Startup ───────────────────────────────────────────────

if __name__ == "__main__":
    # Initial fetch in background so server starts immediately
    threading.Thread(target=fetch_all_news, daemon=True).start()
    # Start periodic background fetcher
    threading.Thread(target=background_fetcher, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
