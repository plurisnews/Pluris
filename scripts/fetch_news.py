"""
PLURIS NEWS — News Fetcher
Raccoglie feed RSS dai principali giornali geopolitici di 15 paesi,
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
# CONFIGURAZIONE FONTI RSS — 15 paesi, ~120 fonti
# ──────────────────────────────────────────────────────────────
SOURCES = [

    # ── USA ──────────────────────────────────────────────────
    {"country": "usa", "flag": "🇺🇸", "name": "Foreign Policy",
     "url": "https://foreignpolicy.com/feed/", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Council on Foreign Relations",
     "url": "https://www.cfr.org/rss.xml", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "The Atlantic — World",
     "url": "https://www.theatlantic.com/feed/channel/international/", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "New York Times — World",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Washington Post — World",
     "url": "https://feeds.washingtonpost.com/rss/world", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Wall Street Journal — World",
     "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Politico — Foreign Policy",
     "url": "https://www.politico.com/rss/politics08.xml", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "The Hill — International",
     "url": "https://thehill.com/rss/syndicator/19110", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Defense One",
     "url": "https://www.defenseone.com/rss/all/", "lang": "en"},
    {"country": "usa", "flag": "🇺🇸", "name": "Brookings Institution",
     "url": "https://www.brookings.edu/feed/", "lang": "en"},

    # ── UK ───────────────────────────────────────────────────
    {"country": "uk", "flag": "🇬🇧", "name": "The Guardian — World",
     "url": "https://www.theguardian.com/world/rss", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "BBC World",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "The Economist",
     "url": "https://www.economist.com/international/rss.xml", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "Financial Times",
     "url": "https://www.ft.com/world?format=rss", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "The Times — World",
     "url": "https://www.thetimes.co.uk/rss/world", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "The Independent — World",
     "url": "https://www.independent.co.uk/news/world/rss", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "Chatham House",
     "url": "https://www.chathamhouse.org/rss.xml", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "Reuters — World",
     "url": "https://feeds.reuters.com/Reuters/worldNews", "lang": "en"},
    {"country": "uk", "flag": "🇬🇧", "name": "The Telegraph — World",
     "url": "https://www.telegraph.co.uk/rss.xml", "lang": "en"},

    # ── FRANCE ───────────────────────────────────────────────
    {"country": "fr", "flag": "🇫🇷", "name": "Le Monde — International",
     "url": "https://www.lemonde.fr/international/rss_full.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Le Figaro — International",
     "url": "https://www.lefigaro.fr/rss/figaro_international.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "France 24",
     "url": "https://www.france24.com/fr/rss", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "RFI — Monde",
     "url": "https://www.rfi.fr/fr/rss/monde.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Le Point — International",
     "url": "https://www.lepoint.fr/rss.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Libération — Monde",
     "url": "https://www.liberation.fr/arc/outboundfeeds/rss/", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "L'Obs — Monde",
     "url": "https://www.nouvelobs.com/rss.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Courrier International",
     "url": "https://www.courrierinternational.com/feed/all/rss.xml", "lang": "fr"},
    {"country": "fr", "flag": "🇫🇷", "name": "Les Échos — Monde",
     "url": "https://www.lesechos.fr/rss/rss_monde.xml", "lang": "fr"},

    # ── GERMANY ──────────────────────────────────────────────
    {"country": "de", "flag": "🇩🇪", "name": "Der Spiegel — Ausland",
     "url": "https://www.spiegel.de/ausland/index.rss", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Deutsche Welle",
     "url": "https://rss.dw.com/rdf/rss-en-world", "lang": "en"},
    {"country": "de", "flag": "🇩🇪", "name": "Frankfurter Allgemeine",
     "url": "https://www.faz.net/rss/aktuell/politik/ausland/", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Süddeutsche Zeitung",
     "url": "https://rss.sueddeutsche.de/rss/Politik", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Die Zeit — Politik",
     "url": "https://newsfeed.zeit.de/politik/index", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Handelsblatt — Politik",
     "url": "https://www.handelsblatt.com/contentexport/feed/politik", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "Tagesspiegel",
     "url": "https://www.tagesspiegel.de/contentexport/feed/home", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "ARD Tagesschau",
     "url": "https://www.tagesschau.de/xml/rss2/", "lang": "de"},
    {"country": "de", "flag": "🇩🇪", "name": "n-tv Ausland",
     "url": "https://www.n-tv.de/rss", "lang": "de"},

    # ── SPAIN ────────────────────────────────────────────────
    {"country": "es", "flag": "🇪🇸", "name": "El País — Internacional",
     "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "El Mundo — Internacional",
     "url": "https://e00-elmundo.uecdn.es/elmundo/rss/internacional.xml", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "La Vanguardia — Internacional",
     "url": "https://www.lavanguardia.com/internacional/index.xml", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "El Confidencial — Mundo",
     "url": "https://rss.elconfidencial.com/mundo/", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "ABC España — Internacional",
     "url": "https://www.abc.es/rss/feeds/abc_Internacional.xml", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "El Español — Internacional",
     "url": "https://www.elespanol.com/rss/internacional.xml", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "RTVE — Internacional",
     "url": "https://www.rtve.es/api/internacionales.rss", "lang": "es"},
    {"country": "es", "flag": "🇪🇸", "name": "Expansión — Economía",
     "url": "https://e00-expansion.uecdn.es/rss/internacional.xml", "lang": "es"},

    # ── CHINA ────────────────────────────────────────────────
    {"country": "cn", "flag": "🇨🇳", "name": "South China Morning Post",
     "url": "https://www.scmp.com/rss/91/feed", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "Global Times",
     "url": "https://www.globaltimes.cn/rss/outbrain.xml", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "Xinhua — World",
     "url": "http://www.xinhuanet.com/english/rss/worldrss.xml", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "China Daily",
     "url": "http://www.chinadaily.com.cn/rss/world_rss.xml", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "CGTN — World",
     "url": "https://www.cgtn.com/subscribe/rss/section/world.xml", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "Caixin Global",
     "url": "https://www.caixinglobal.com/rss/latest-articles.xml", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "The Diplomat — China",
     "url": "https://thediplomat.com/feed/", "lang": "en"},
    {"country": "cn", "flag": "🇨🇳", "name": "Sixth Tone",
     "url": "https://www.sixthtone.com/rss", "lang": "en"},

    # ── ITALY ────────────────────────────────────────────────
    {"country": "it", "flag": "🇮🇹", "name": "La Repubblica — Esteri",
     "url": "https://www.repubblica.it/rss/esteri/rss2.0.xml", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "Corriere della Sera — Esteri",
     "url": "https://www.corriere.it/rss/esteri.xml", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "La Stampa — Esteri",
     "url": "https://www.lastampa.it/rss/esteri.xml", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "Il Sole 24 Ore — Mondo",
     "url": "https://www.ilsole24ore.com/rss/mondo.xml", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "ANSA — Mondo",
     "url": "https://www.ansa.it/sito/notizie/mondo/mondo_rss.xml", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "Il Fatto Quotidiano — Esteri",
     "url": "https://www.ilfattoquotidiano.it/feed/", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "Limes — Geopolitica",
     "url": "https://www.limesonline.com/feed", "lang": "it"},
    {"country": "it", "flag": "🇮🇹", "name": "Internazionale",
     "url": "https://www.internazionale.it/feed/rss.xml", "lang": "it"},

    # ── RUSSIA ───────────────────────────────────────────────
    {"country": "ru", "flag": "🇷🇺", "name": "RT — World",
     "url": "https://www.rt.com/rss/news/", "lang": "en"},
    {"country": "ru", "flag": "🇷🇺", "name": "TASS — World",
     "url": "https://tass.com/rss/v2.xml", "lang": "en"},
    {"country": "ru", "flag": "🇷🇺", "name": "Interfax — World",
     "url": "https://www.interfax.com/rss.asp", "lang": "en"},
    {"country": "ru", "flag": "🇷🇺", "name": "Moscow Times",
     "url": "https://www.themoscowtimes.com/rss/news", "lang": "en"},
    {"country": "ru", "flag": "🇷🇺", "name": "Meduza",
     "url": "https://meduza.io/rss/all", "lang": "en"},
    {"country": "ru", "flag": "🇷🇺", "name": "Kommersant",
     "url": "https://www.kommersant.ru/RSS/main.xml", "lang": "ru"},
    {"country": "ru", "flag": "🇷🇺", "name": "Novaya Gazeta Europe",
     "url": "https://novayagazeta.eu/rss", "lang": "en"},

    # ── JAPAN ────────────────────────────────────────────────
    {"country": "jp", "flag": "🇯🇵", "name": "Japan Times — World",
     "url": "https://www.japantimes.co.jp/feed/", "lang": "en"},
    {"country": "jp", "flag": "🇯🇵", "name": "NHK World",
     "url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "lang": "en"},
    {"country": "jp", "flag": "🇯🇵", "name": "Nikkei Asia",
     "url": "https://asia.nikkei.com/rss/feed/nar", "lang": "en"},
    {"country": "jp", "flag": "🇯🇵", "name": "Asahi Shimbun — English",
     "url": "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "lang": "ja"},
    {"country": "jp", "flag": "🇯🇵", "name": "Yomiuri Shimbun",
     "url": "https://www.yomiuri.co.jp/feed/", "lang": "ja"},
    {"country": "jp", "flag": "🇯🇵", "name": "The Diplomat — Japan",
     "url": "https://thediplomat.com/feed/", "lang": "en"},
    {"country": "jp", "flag": "🇯🇵", "name": "Mainichi Shimbun",
     "url": "https://mainichi.jp/rss/etc/mainichi-flash.rss", "lang": "ja"},

    # ── INDIA ────────────────────────────────────────────────
    {"country": "in", "flag": "🇮🇳", "name": "The Hindu — International",
     "url": "https://www.thehindu.com/news/international/feeder/default.rss", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "Hindustan Times — World",
     "url": "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "The Wire — World",
     "url": "https://thewire.in/feed", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "Indian Express — World",
     "url": "https://indianexpress.com/section/world/feed/", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "NDTV — World",
     "url": "https://feeds.feedburner.com/ndtvnews-world-news", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "Times of India — World",
     "url": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "The Print — World",
     "url": "https://theprint.in/feed/", "lang": "en"},
    {"country": "in", "flag": "🇮🇳", "name": "Observer Research Foundation",
     "url": "https://www.orfonline.org/feed/", "lang": "en"},

    # ── BRAZIL ───────────────────────────────────────────────
    {"country": "br", "flag": "🇧🇷", "name": "Folha de S.Paulo — Mundo",
     "url": "https://feeds.folha.uol.com.br/mundo/rss091.xml", "lang": "pt"},
    {"country": "br", "flag": "🇧🇷", "name": "O Globo — Mundo",
     "url": "https://oglobo.globo.com/rss.xml?editoria=Mundo", "lang": "pt"},
    {"country": "br", "flag": "🇧🇷", "name": "Estadão — Internacional",
     "url": "https://www.estadao.com.br/rss/internacional.xml", "lang": "pt"},
    {"country": "br", "flag": "🇧🇷", "name": "UOL Notícias — Mundo",
     "url": "https://rss.uol.com.br/feed/noticias.xml", "lang": "pt"},
    {"country": "br", "flag": "🇧🇷", "name": "Agência Brasil",
     "url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "lang": "pt"},
    {"country": "br", "flag": "🇧🇷", "name": "The Brazilian Report",
     "url": "https://brazilian.report/feed/", "lang": "en"},
    {"country": "br", "flag": "🇧🇷", "name": "Correio Braziliense — Mundo",
     "url": "https://www.correiobraziliense.com.br/rss/feed.xml", "lang": "pt"},

    # ── TURKEY ───────────────────────────────────────────────
    {"country": "tr", "flag": "🇹🇷", "name": "Daily Sabah — World",
     "url": "https://www.dailysabah.com/feeds/rss/world", "lang": "en"},
    {"country": "tr", "flag": "🇹🇷", "name": "Hurriyet Daily News",
     "url": "https://www.hurriyetdailynews.com/rss/world", "lang": "en"},
    {"country": "tr", "flag": "🇹🇷", "name": "TRT World",
     "url": "https://www.trtworld.com/rss", "lang": "en"},
    {"country": "tr", "flag": "🇹🇷", "name": "Anadolu Agency",
     "url": "https://www.aa.com.tr/en/rss/default?cat=world", "lang": "en"},
    {"country": "tr", "flag": "🇹🇷", "name": "Cumhuriyet",
     "url": "https://www.cumhuriyet.com.tr/rss/son_dakika.xml", "lang": "tr"},
    {"country": "tr", "flag": "🇹🇷", "name": "Milliyet",
     "url": "https://www.milliyet.com.tr/rss/rssNew/dunyaRss.xml", "lang": "tr"},
    {"country": "tr", "flag": "🇹🇷", "name": "Bianet",
     "url": "https://bianet.org/rss", "lang": "en"},

    # ── SAUDI ARABIA ─────────────────────────────────────────
    {"country": "sa", "flag": "🇸🇦", "name": "Arab News",
     "url": "https://www.arabnews.com/rss.xml", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Saudi Gazette",
     "url": "https://saudigazette.com.sa/feed/", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Al Arabiya — World",
     "url": "https://www.alarabiya.net/tools/rss", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Al Jazeera — World",
     "url": "https://www.aljazeera.com/xml/rss/all.xml", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Middle East Eye",
     "url": "https://www.middleeasteye.net/rss", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Asharq Al-Awsat",
     "url": "https://english.aawsat.com/rss.xml", "lang": "en"},
    {"country": "sa", "flag": "🇸🇦", "name": "Al Monitor — Middle East",
     "url": "https://www.al-monitor.com/rss", "lang": "en"},

    # ── AUSTRALIA ────────────────────────────────────────────
    {"country": "au", "flag": "🇦🇺", "name": "ABC News — World",
     "url": "https://www.abc.net.au/news/feed/51120/rss.xml", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "Sydney Morning Herald — World",
     "url": "https://www.smh.com.au/rss/world.xml", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "The Australian",
     "url": "https://www.theaustralian.com.au/feed", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "The Guardian Australia",
     "url": "https://www.theguardian.com/australia-news/rss", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "ASPI — Strategy",
     "url": "https://www.aspistrategist.org.au/feed/", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "The Interpreter — Lowy",
     "url": "https://www.lowyinstitute.org/the-interpreter/rss.xml", "lang": "en"},
    {"country": "au", "flag": "🇦🇺", "name": "East Asia Forum",
     "url": "https://www.eastasiaforum.org/feed/", "lang": "en"},

    # ── SOUTH KOREA ──────────────────────────────────────────
    {"country": "kr", "flag": "🇰🇷", "name": "Korea Herald — World",
     "url": "http://www.koreaherald.com/rss/020000000000.xml", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "Korea JoongAng Daily",
     "url": "https://koreajoongangdaily.joins.com/rss/news", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "Hankyoreh — English",
     "url": "http://english.hani.co.kr/rss/", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "The Chosun Ilbo",
     "url": "https://english.chosun.com/rss/allpaper.xml", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "Yonhap News",
     "url": "https://en.yna.co.kr/RSS/world.xml", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "Korea Times — World",
     "url": "https://www.koreatimes.co.kr/www/rss/rss.asp?categoryCode=103", "lang": "en"},
    {"country": "kr", "flag": "🇰🇷", "name": "38 North — Korea",
     "url": "https://www.38north.org/feed/", "lang": "en"},
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
                     "protectionism", "embargo", "commerce", "gümrük", "ticaret", "tarifa",
                     "comércio", "貿易", "무역", "관세", "व्यापार", "تجارة", "торговля"],
    },
    "ukraine": {
        "label": {"en": "UKRAINE WAR", "it": "GUERRA IN UCRAINA", "fr": "GUERRE EN UKRAINE",
                  "de": "UKRAINE-KRIEG", "es": "GUERRA EN UCRANIA", "zh": "乌克兰战争"},
        "icon": "🕊️",
        "keywords": ["ukraine", "russia", "zelensky", "putin", "kyiv", "moscow", "nato",
                     "ucraina", "russie", "otan", "krieg", "guerra", "ceasefire", "donbas",
                     "missile", "offensive", "战争", "乌克兰", "ucrânia", "ukrayna", "войска",
                     "ウクライナ", "우크라이나", "यूक्रेन", "أوكرانيا"],
    },
    "mideast": {
        "label": {"en": "MIDDLE EAST", "it": "MEDIO ORIENTE", "fr": "MOYEN-ORIENT",
                  "de": "NAHER OSTEN", "es": "ORIENTE MEDIO", "zh": "中东"},
        "icon": "🌙",
        "keywords": ["israel", "gaza", "hamas", "iran", "saudi", "middle east", "palestine",
                     "lebanon", "syria", "yemen", "medio oriente", "moyen-orient", "proche-orient",
                     "nahost", "oriente medio", "中东", "以色列", "伊朗", "oriente médio",
                     "ortadoğu", "中東", "중동", "मध्य पूर्व", "الشرق الأوسط", "Ближний Восток"],
    },
    "climate": {
        "label": {"en": "CLIMATE", "it": "CLIMA", "fr": "CLIMAT",
                  "de": "KLIMA", "es": "CLIMA", "zh": "气候"},
        "icon": "🌍",
        "keywords": ["climate", "cop", "emissions", "carbon", "fossil fuel", "green deal",
                     "global warming", "climat", "klima", "cambio climático", "energia",
                     "renewables", "气候", "碳", "clima", "iklim", "mudança climática",
                     "気候", "기후", "जलवायु", "المناخ", "климат"],
    },
    "tech": {
        "label": {"en": "TECH RIVALRY", "it": "RIVALITÀ TECH", "fr": "RIVALITÉ TECHNOLOGIQUE",
                  "de": "TECH-RIVALITÄT", "es": "RIVALIDAD TECNOLÓGICA", "zh": "科技竞争"},
        "icon": "💻",
        "keywords": ["semiconductor", "chip", "ai ", "artificial intelligence", "huawei",
                     "taiwan", "tsmc", "silicon", "tech war", "cyber", "5g", "quantum",
                     "半导体", "芯片", "人工智能", "technologie", "yapay zeka", "inteligência",
                     "テクノロジー", "기술", "तकनीक", "تقنية", "технологии"],
    },
    "indo_pacific": {
        "label": {"en": "INDO-PACIFIC", "it": "INDO-PACIFICO", "fr": "INDO-PACIFIQUE",
                  "de": "INDO-PAZIFIK", "es": "INDO-PACÍFICO", "zh": "印太地区"},
        "icon": "🌊",
        "keywords": ["indo-pacific", "south china sea", "taiwan strait", "aukus", "quad",
                     "asean", "pacific", "korea", "japan", "philippines", "indonesia",
                     "indo-pacifico", "インド太平洋", "인도태평양", "남중국해"],
    },
    "energy": {
        "label": {"en": "ENERGY & OIL", "it": "ENERGIA & PETROLIO", "fr": "ÉNERGIE & PÉTROLE",
                  "de": "ENERGIE & ÖL", "es": "ENERGÍA & PETRÓLEO", "zh": "能源与石油"},
        "icon": "⚡",
        "keywords": ["oil", "gas", "opec", "energy", "pipeline", "lng", "petroleum", "nuclear",
                     "petrolio", "énergie", "energie", "energía", "石油", "能源", "petróleo",
                     "enerji", "エネルギー", "에너지", "ऊर्जा", "الطاقة", "энергия"],
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
