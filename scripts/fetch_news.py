"""
PLURIS — News Fetcher
Raccoglie feed RSS dai principali giornali geopolitici di 6 paesi,
raggruppa per tema, traduce con Claude API, salva in data/news.json
"""

import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

# ── Anthropic client (opzionale — se non hai la chiave, traduce con flag skip)
try:
    import anthropic
    ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    AI_TRANSLATION = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    ANTHROPIC_CLIENT = None
    AI_TRANSLATION = False

# ──────────────────────────────────────────────────────────────
# CONFIGURAZIONE FONTI RSS
# ──────────────────────────────────────────────────────────────
SOURCES = [
    # USA
    {"country": "usa", "flag": "🇺🇸", "name": "Foreign Policy",
     "url": "https://foreignpolicy.com/feed/", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Council on Foreign Relations",
     "url": "https://www.cfr.org/rss.xml", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "The Atlantic — World",
     "url": "https://www.theatlantic.com/feed/channel/international/", "lang": "en"},

    # UK
    {"country": "uk", "flag": "🇬🇧", "name": "The Guardian — World",
     "url": "https://www.theguardian.com/world/rss", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "BBC World",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "The Economist",
     "url": "https://www.economist.com/international/rss.xml", "lang": "en"},

    # France
    {"country": "fr", "flag": "🇫🇷", "name": "Le Monde — International",
     "url": "https://www.lemonde.fr/international/rss_full.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Le Figaro — International",
     "url": "https://www.lefigaro.fr/rss/figaro_international.xml", "lang": "fr"},

    # Germany
    {"country": "de", "flag": "🇩🇪", "name": "Der Spiegel — Ausland",
     "url": "https://www.spiegel.de/ausland/index.rss", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Deutsche Welle",
     "url": "https://rss.dw.com/rdf/rss-en-world", "lang": "en"},

    # Spain
    {"country": "es", "flag": "🇪🇸", "name": "El País — Internacional",
     "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "El Mundo — Internacional",
     "url": "https://e00-elmundo.uecdn.es/elmundo/rss/internacional.xml", "lang": "es"},

    # China
    {"country": "cn", "flag": "🇨🇳", "name": "South China Morning Post",
     "url": "https://www.scmp.com/rss/91/feed", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "Global Times",
     "url": "https://www.globaltimes.cn/rss/outbrain.xml", "lang": "en"},
]

# ──────────────────────────────────────────────────────────────
# TEMI GEOPOLITICI — parole chiave per raggruppamento
# ──────────────────────────────────────────────────────────────
TOPICS = {
    "trade": {
        "label": {"en": "TRADE WAR", "it": "GUERRA COMMERCIALE", "fr": "GUERRE COMMERCIALE",
                  "de": "HANDELSKRIEG", "es": "GUERRA COMERCIAL", "zh": "贸易战"},
        "icon": "⚖️",
        "keywords": ["tariff", "trade war", "sanction", "export control", "import", "dazio",
                     "commercio", "zoll", "arancel", "关税", "贸易", "wto", "supply chain",
                     "protectionism", "embargo", "commerce"],
    },
    "ukraine": {
        "label": {"en": "UKRAINE WAR", "it": "GUERRA IN UCRAINA", "fr": "GUERRE EN UKRAINE",
                  "de": "UKRAINE-KRIEG", "es": "GUERRA EN UCRANIA", "zh": "乌克兰战争"},
        "icon": "🕊️",
        "keywords": ["ukraine", "russia", "zelensky", "putin", "kyiv", "moscow", "nato",
                     "ucraina", "russie", "otan", "krieg", "guerra", "ceasefire", "donbas",
                     "missile", "offensive", "战争", "乌克兰"],
    },
    "mideast": {
        "label": {"en": "MIDDLE EAST", "it": "MEDIO ORIENTE", "fr": "MOYEN-ORIENT",
                  "de": "NAHER OSTEN", "es": "ORIENTE MEDIO", "zh": "中东"},
        "icon": "🌙",
        "keywords": ["israel", "gaza", "hamas", "iran", "saudi", "middle east", "palestine",
                     "lebanon", "syria", "yemen", "medio oriente", "moyen-orient", "proche-orient",
                     "nahost", "oriente medio", "中东", "以色列", "伊朗"],
    },
    "climate": {
        "label": {"en": "CLIMATE", "it": "CLIMA", "fr": "CLIMAT",
                  "de": "KLIMA", "es": "CLIMA", "zh": "气候"},
        "icon": "🌍",
        "keywords": ["climate", "cop", "emissions", "carbon", "fossil fuel", "green deal",
                     "global warming", "climat", "klima", "cambio climático", "energia",
                     "renewables", "气候", "碳"],
    },
    "tech": {
        "label": {"en": "TECH RIVALRY", "it": "RIVALITÀ TECH", "fr": "RIVALITÉ TECHNOLOGIQUE",
                  "de": "TECH-RIVALITÄT", "es": "RIVALIDAD TECNOLÓGICA", "zh": "科技竞争"},
        "icon": "💻",
        "keywords": ["semiconductor", "chip", "ai ", "artificial intelligence", "huawei",
                     "taiwan", "tsmc", "silicon", "tech war", "cyber", "5g", "quantum",
                     "半导体", "芯片", "人工智能", "technologie"],
    },
}

FALLBACK_TOPIC = "trade"  # topic di default se nessuna keyword matcha

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
def fetch_rss(url: str, timeout: int = 10) -> list[dict]:
    """Scarica e parsa un feed RSS, restituisce lista di articoli."""
    headers = {"User-Agent": "PLURIS-Bot/1.0 (geopolitics aggregator)"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except (URLError, ET.ParseError) as e:
        print(f"  ⚠️  {url} — {e}")
        return []

    items = []
    # Supporta sia RSS 2.0 che Atom
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "dc": "http://purl.org/dc/elements/1.1/",
          "media": "http://search.yahoo.com/mrss/"}

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        desc  = (item.findtext("description") or item.findtext("dc:description", namespaces=ns) or "").strip()
        # rimuovi HTML tags dalla descrizione
        desc  = re.sub(r"<[^>]+>", "", desc)[:400]
        pub   = (item.findtext("pubDate") or item.findtext("dc:date", namespaces=ns) or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "excerpt": desc, "pubDate": pub})

    # Atom fallback
    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = (link_el.get("href", "") if link_el is not None else "").strip()
            desc = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
            desc = re.sub(r"<[^>]+>", "", desc)[:400]
            if title and link:
                items.append({"title": title, "link": link, "excerpt": desc, "pubDate": ""})

    return items[:15]  # max 15 per fonte


def classify_topic(title: str, excerpt: str) -> str:
    """Classifica un articolo in un topic geopolitico."""
    text = (title + " " + excerpt).lower()
    scores = {topic: 0 for topic in TOPICS}
    for topic, conf in TOPICS.items():
        for kw in conf["keywords"]:
            if kw.lower() in text:
                scores[topic] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else FALLBACK_TOPIC


def make_id(title: str, country: str) -> str:
    return hashlib.md5((title + country).encode()).hexdigest()[:10]


def translate_with_claude(text: str, target_langs: list[str], source_lang: str) -> dict:
    """Traduce un testo nelle lingue target usando Claude API."""
    if not AI_TRANSLATION or not ANTHROPIC_CLIENT or len(text) < 10:
        return {}

    langs_to_translate = [l for l in target_langs if l != source_lang]
    if not langs_to_translate:
        return {}

    lang_names = {"en": "English", "it": "Italian", "fr": "French",
                  "de": "German", "es": "Spanish", "zh": "Chinese (Simplified)"}
    target_list = ", ".join(f"{lang_names.get(l, l)} ({l})" for l in langs_to_translate)

    prompt = f"""Translate the following news excerpt into these languages: {target_list}.
Return ONLY a JSON object with language codes as keys. No markdown, no explanation.
Example: {{"en": "...", "it": "...", "fr": "..."}}

Text to translate:
{text[:300]}"""

    try:
        msg = ANTHROPIC_CLIENT.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        # pulizia JSON
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  ⚠️  Translation error: {e}")
        return {}


def sentiment_from_text(title: str, country: str) -> tuple[str, str]:
    """Stima il sentiment da parole chiave semplici."""
    title_l = title.lower()
    if any(w in title_l for w in ["war", "attack", "crisis", "collapse", "threat", "conflict",
                                   "guerra", "crisi", "krieg", "crise", "critica"]):
        return "alarm", "ALERT"
    if any(w in title_l for w in ["sanction", "condemn", "reject", "refuse", "warns",
                                   "avverte", "condanna", "warnt", "condena"]):
        return "critical", "CRITICAL"
    if any(w in title_l for w in ["deal", "agreement", "peace", "cooperation", "accord",
                                   "accordo", "pace", "einigung", "acuerdo", "合作"]):
        return "positive", "POSITIVE"
    return "neutral", "ANALYSIS"


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"PLURIS Fetcher — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"AI Translation: {'✅ ON' if AI_TRANSLATION else '⏭️  OFF (no API key)'}")
    print(f"{'='*50}\n")

    # Carica news precedenti per evitare duplicati
    output_path = os.path.join(os.path.dirname(__file__), "../data/news.json")
    existing_ids = set()
    if os.path.exists(output_path):
        try:
            with open(output_path) as f:
                old = json.load(f)
            for story in old.get("stories", {}).values():
                for card in story.get("cards", []):
                    existing_ids.add(card.get("id", ""))
        except Exception:
            pass

    # Raggruppa articoli per topic
    topic_cards: dict[str, list] = {t: [] for t in TOPICS}
    all_langs = ["en", "it", "fr", "de", "es", "zh"]

    for source in SOURCES:
        print(f"📡 {source['flag']} {source['name']}...")
        articles = fetch_rss(source["url"])
        print(f"   → {len(articles)} articoli trovati")

        for art in articles:
            article_id = make_id(art["title"], source["country"])
            if article_id in existing_ids:
                continue

            topic = classify_topic(art["title"], art["excerpt"])
            sentiment, sent_label = sentiment_from_text(art["title"], source["country"])

            # Traduzione AI (solo se chiave disponibile)
            translated = {}
            if AI_TRANSLATION and art["excerpt"]:
                translated = translate_with_claude(
                    art["title"] + ". " + art["excerpt"],
                    all_langs,
                    source["lang"]
                )
                time.sleep(0.3)  # rate limit gentile

            card = {
                "id": article_id,
                "country": source["country"],
                "flag": source["flag"],
                "source": source["name"],
                "headline": art["title"],
                "excerpt": art["excerpt"] or "Read the full article at source.",
                "link": art["link"],
                "time": art["pubDate"] or "recently",
                "original": source["lang"].upper(),
                "sentiment": sentiment,
                "sentLabel": sent_label,
                "translated": translated,
            }
            topic_cards[topic].append(card)

        time.sleep(0.5)  # pausa tra fonti

    # ── Costruisci struttura stories ──
    stories = {}
    for topic_key, conf in TOPICS.items():
        cards = topic_cards[topic_key]
        if not cards:
            continue

        # Max 6 card per story (una per paese idealmente)
        # Priorità: un paese diverso per ogni slot
        seen_countries = set()
        selected = []
        for card in sorted(cards, key=lambda c: c["time"], reverse=False):
            if card["country"] not in seen_countries:
                selected.append(card)
                seen_countries.add(card["country"])
            if len(selected) >= 6:
                break
        # Se non arriva a 6, aggiungi altri
        for card in cards:
            if card not in selected and len(selected) < 6:
                selected.append(card)

        stories[topic_key] = {
            "id": topic_key,
            "topic": topic_key,
            "icon": conf["icon"],
            "category": conf["label"],
            "headline": {
                "en": f"Global perspectives on: {topic_key.replace('_', ' ').title()}",
                "it": f"Prospettive globali su: {topic_key}",
                "fr": f"Perspectives mondiales sur: {topic_key}",
                "de": f"Weltweite Perspektiven zu: {topic_key}",
                "es": f"Perspectivas globales sobre: {topic_key}",
                "zh": f"全球视角：{topic_key}",
            },
            "summary": {
                "en": f"{len(selected)} perspectives from {len(seen_countries)} countries.",
                "it": f"{len(selected)} prospettive da {len(seen_countries)} paesi.",
                "fr": f"{len(selected)} perspectives de {len(seen_countries)} pays.",
                "de": f"{len(selected)} Perspektiven aus {len(seen_countries)} Ländern.",
                "es": f"{len(selected)} perspectivas de {len(seen_countries)} países.",
                "zh": f"来自{len(seen_countries)}个国家的{len(selected)}种视角。",
            },
            "cards": selected,
        }

    # ── Salva output ──
    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "total_articles": sum(len(v) for v in topic_cards.values()),
        "stories": stories,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Salvato: {output_path}")
    print(f"   Topics: {', '.join(f'{k}({len(v)} cards)' for k,v in topic_cards.items())}")
    print(f"   Totale articoli: {output['total_articles']}")


if __name__ == "__main__":
    main()
