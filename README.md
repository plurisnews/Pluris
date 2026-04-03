# 🌍 PLURIS — Setup Guide

Segui questi passi nell'ordine. Ogni passo richiede 5-10 minuti.

## STRUTTURA PROGETTO
```
pluris/
├── .github/workflows/fetch_news.yml   ← automazione ogni 30 min
├── data/news.json                     ← notizie generate automaticamente  
├── public/index.html                  ← il sito web
├── scripts/fetch_news.py              ← script che raccoglie le notizie
└── netlify.toml                       ← configurazione hosting
```

## PASSO 1 — GitHub
1. github.com → New repository → nome: pluris → Public
2. Carica tutti questi file con "uploading an existing file"

## PASSO 2 — Netlify (hosting gratis)
1. netlify.com → Sign up con GitHub
2. Add new site → Import from GitHub → seleziona pluris
3. Deploy — in 60 secondi il sito è online

## PASSO 3 — Automazione (già configurata)
GitHub → tab Actions → "PLURIS Fetch News" → Run workflow (primo test)
Poi gira da sola ogni 30 minuti.

## PASSO 4 — Traduzione AI (opzionale, ~€5/mese)
console.anthropic.com → crea chiave API
GitHub repo → Settings → Secrets → New secret
Name: ANTHROPIC_API_KEY  Value: sk-ant-...

## PASSO 5 — AdSense
adsense.google.com → inserisci il tuo URL → aspetta approvazione (3-14gg)

## COSTI
- GitHub + Netlify + Actions: GRATIS
- Dominio .news: ~€10/anno  
- Claude API traduzione: ~€5/mese
