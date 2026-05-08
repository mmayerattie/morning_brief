# CLAUDE.md — Briefing Agent

## Visión general del proyecto

Agente de inteligencia diaria personal que recolecta información de múltiples fuentes
(tech news, mercados financieros, GitHub trending, startups), la sintetiza usando
la API de Groq (Llama 3.3 70B), y la entrega todos los días a las 8am vía Telegram.

El usuario es Mayer: data scientist graduándose en pocos meses, emprendedor enfocado
en agentes de IA, con portafolio mixto de acciones tech, ETFs y cripto. Busca trabajo
en Madrid, París, Milán, Londres y Argentina.

---

## Estado actual (2026-05-08)

✅ **Funcionando:**
- Pipeline completo end-to-end
- Todos los collectors (tech news, ArXiv, GitHub trending, markets, startups)
- Entrega por Telegram (2 mensajes — ver issue abajo)
- Logging en Supabase (`sent=True`)
- Scheduler a las 8am Madrid
- Deduplicación de repos de GitHub (no repite repos ya vistos)

⚠️ **Issues conocidos:**
1. **Datos de mercado**: yfinance solo devuelve datos para tickers que no dependen del horario del mercado US. Las acciones (SOFI, DLR, SKM, CLSK, BRK-B) y ETFs (SMH, XLU) aparecen vacíos cuando el mercado está cerrado (8am Madrid = 2am ET). Ver sección de mejoras pendientes.
2. **Briefing en 2 mensajes**: El output del LLM supera los 4096 caracteres de Telegram. El formatter lo divide correctamente pero lo ideal sería recibir un solo mensaje. Ver sección de mejoras pendientes.

---

## Estructura del proyecto

```
morning_coffee/
│
├── CLAUDE.md                        # Este archivo
├── main.py                          # Entry point: ejecuta el pipeline completo
├── scheduler.py                     # APScheduler: corre main.py todos los días a las 8am
├── requirements.txt
├── .env                             # Variables de entorno (NUNCA commitear)
├── .env.example                     # Template de variables sin valores reales
├── .gitignore
│
├── collectors/
│   ├── __init__.py
│   ├── tech_news.py                 # RSS feeds de tech + Hacker News API
│   ├── arxiv_papers.py              # Papers de ArXiv (cs.AI, cs.LG, cs.CL)
│   ├── github_trending.py           # Scraping de GitHub Trending (mensual, sin repetidos)
│   ├── markets.py                   # yfinance + Fear & Greed Index
│   └── startups.py                  # TechCrunch + a16z + YC RSS feeds
│
├── agent/
│   ├── __init__.py
│   ├── prompts.py                   # System prompt + user template (fuente de verdad)
│   ├── summarizer.py                # Llama a Groq API, genera el briefing
│   └── formatter.py                 # Convierte markdown a HTML de Telegram
│
├── delivery/
│   ├── __init__.py
│   └── telegram_bot.py              # Envía el briefing al chat de Mayer
│
├── storage/
│   ├── __init__.py
│   ├── supabase_client.py           # Guarda log de cada briefing enviado
│   └── seen_repos.json              # Repos de GitHub ya mostrados (auto-generado)
│
└── utils/
    ├── __init__.py
    ├── logger.py                    # Logging consistente en todo el proyecto
    └── retry.py                     # Decorator de retry con backoff exponencial
```

---

## Variables de entorno (.env)

```bash
# Groq (LLM — gratuito, sin tarjeta de crédito)
GROQ_API_KEY=gsk_...

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...          # ID numérico — obtener con /getUpdates después de enviar /start al bot

# Supabase
SUPABASE_URL=https://xxxx.supabase.co    # Solo el base URL, sin /rest/v1/ ni trailing slash
SUPABASE_KEY=eyJ...                       # Anon/public key (no la secret key)

# Portafolio de Mayer
PORTFOLIO_STOCKS=BRK-B,SOFI,DLR,SKM,CLSK   # Yahoo Finance usa guión, no punto (BRK-B no BRK.B)
PORTFOLIO_ETFS=SMH,XLU
PORTFOLIO_CRYPTO=TIBBIR36743-USD

# Scheduler
BRIEFING_HOUR=8
BRIEFING_MINUTE=0
TIMEZONE=Europe/Madrid
```

### Notas importantes sobre credenciales
- **TELEGRAM_CHAT_ID**: debe ser el ID numérico de tu cuenta personal. Obtenerlo: enviar `/start` al bot en Telegram, luego `curl "https://api.telegram.org/bot{TOKEN}/getUpdates"` y buscar `"chat":{"id": XXXXXXX}`.
- **SUPABASE_URL**: nunca incluir `/rest/v1/` ni trailing slash. El cliente Python lo agrega solo.
- **Supabase RLS**: la tabla `briefings` tiene RLS deshabilitado (`ALTER TABLE briefings DISABLE ROW LEVEL SECURITY`). Si se habilita, agregar política de INSERT para el rol `anon`.

---

## Stack tecnológico

| Componente | Tecnología | Notas |
|---|---|---|
| Lenguaje | Python 3.10+ | |
| LLM | Groq API — `llama-3.3-70b-versatile` | Gratis, sin tarjeta. Reemplazó Claude por costo |
| Colección RSS | `feedparser` 6.0+ | Sincrónico → `run_in_executor` |
| Mercados financieros | `yfinance` 0.2+ | `period="5d"` + `dropna` para manejar horario US |
| Web scraping | `httpx` + `beautifulsoup4` + `lxml` | GitHub trending mensual |
| Scheduler | `apscheduler` 3.10+ | `AsyncIOScheduler` |
| Telegram | `httpx` directo (no librería) | Send-only, sin overhead de polling |
| Base de datos | `supabase` 2.0+ | Tabla `briefings`, RLS deshabilitado |
| Variables de entorno | `python-dotenv` | |
| Logging | stdlib `logging` | Formato: `timestamp \| level \| module \| message` |

### requirements.txt

```
feedparser>=6.0.0
yfinance>=0.2.40
httpx>=0.27.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
apscheduler>=3.10.0
python-telegram-bot>=20.0
supabase>=2.0.0
python-dotenv>=1.0.0
pytz>=2024.1
groq>=0.9.0
```

---

## Fuentes de datos por sección

### Sección 1 — IA y Tech

| Fuente | URL | Método |
|---|---|---|
| The Verge AI | `https://www.theverge.com/ai-artificial-intelligence/rss/index.xml` | RSS |
| TechCrunch AI | `https://techcrunch.com/category/artificial-intelligence/feed/` | RSS |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/technology-lab` | RSS |
| Hacker News Top | `https://hacker-news.firebaseio.com/v0/topstories.json` | REST API |

**Lógica de Hacker News:** top 30 IDs → fetch paralelo → filtrar score > 100 → top 5.

### Sección 2 — Papers de ArXiv

Feeds: `cs.AI`, `cs.LG`, `cs.CL` — deduplicados por `arxiv_id`, top 4 más recientes.

### Sección 3 — GitHub Trending

- URL: `https://github.com/trending?since=monthly` (mensual, pool más estable que diario)
- Scraping con `httpx` + `beautifulsoup4`
- **Deduplicación**: repos ya mostrados se guardan en `storage/seen_repos.json` (ventana de 60 repos). Si todos fueron vistos, se resetea el historial.
- Selectores CSS: `article.Box-row`, `h2.h3 a`, `p.col-9`, `span.d-inline-block.float-sm-right`, `span[itemprop='programmingLanguage']`
- Este collector es el más frágil ante cambios de diseño de GitHub. Si falla, el briefing continúa igual.

### Sección 4 — Mercados e Inversiones

**yfinance:**
```python
data = yf.download(tickers, period="5d", interval="1d", auto_adjust=True)
close = data["Close"].dropna(how="all")  # elimina días sin trading
# Comparar last two rows
```
`period="5d"` en vez de `"2d"` porque a las 8am Madrid (2am ET) el mercado US aún no abrió.
`dropna(how="all")` elimina filas donde todos los valores son NaN.

**Fear & Greed Index:** `https://api.alternative.me/fng/` — gratuito, sin auth.

⚠️ **Issue conocido:** tickers de acciones US y ETFs no devuelven datos antes de que abra el mercado. Ver mejoras pendientes.

### Sección 5 — Startups y Tendencias

RSS de TechCrunch, a16z, Y Combinator — top 4 items por feed.

---

## LLM — Groq API (agent/summarizer.py)

```python
from groq import Groq

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

response = _client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    max_tokens=1500,
    messages=[
        {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ],
)
return response.choices[0].message.content
```

Groq usa la interfaz OpenAI-compatible. `response.choices[0].message.content` es el texto generado.

---

## Formato Telegram (agent/formatter.py)

Telegram solo acepta un subconjunto de HTML. La conversión:
- `**texto**` → `<b>texto</b>`
- `*texto*` → `<i>texto</i>`
- `` `texto` `` → `<code>texto</code>`
- `[texto](url)` → `<a href="url">texto</a>`
- `## Header` → `<b>Header</b>`
- Escapar `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;` **antes** de insertar tags HTML

**Límite 4096 chars**: el formatter divide en chunks en límites de párrafo. El briefing actual produce 2 mensajes. Ver mejoras pendientes.

**Fallback**: si Telegram rechaza el HTML (400), reintenta como texto plano con tags removidos.

---

## Pipeline — main.py

```python
results = await asyncio.gather(
    tech_news.fetch(),
    arxiv_papers.fetch(),
    github_trending.fetch(),
    markets.fetch(),        # retorna dict, no str
    startups.fetch(),
    return_exceptions=True, # un fallo no cancela el resto
)
# → summarizer → formatter → telegram_bot → supabase (en finally)
```

**Nota importante:** `markets.fetch()` es el único collector que retorna `dict[str, str]` con claves `portfolio_data`, `fear_greed_value`, `fear_greed_label`. Todos los demás retornan `str`. `_process_results()` en `main.py` maneja este caso especial.

---

## Supabase — Schema

```sql
CREATE TABLE briefings (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    date        DATE NOT NULL,
    raw_content TEXT,
    sent        BOOLEAN DEFAULT FALSE,
    error       TEXT
);
ALTER TABLE briefings DISABLE ROW LEVEL SECURITY;
```

El log se escribe en un bloque `finally` — siempre se ejecuta aunque el pipeline falle.

---

## Mejoras pendientes

### 1. Datos de mercado fuera de horario US
**Problema:** yfinance no devuelve datos para acciones US antes de que abra el mercado (8am Madrid = 2am ET). Solo funcionan tickers no dependientes del NYSE/NASDAQ.

**Opciones:**
- **Alpha Vantage** (gratuito con límites): devuelve el último precio de cierre vía API REST independientemente del horario
- **Twelve Data** (gratuito con límites): similar, con endpoint `/quote`
- Cambiar la hora del briefing a después del cierre US (22:30 Madrid) para tener datos del día completo
- Usar `period="5d"` y mostrar el último cierre disponible con fecha explícita ("Último cierre: miércoles")

### 2. Briefing en 2 mensajes
**Problema:** El LLM genera ~5700 chars, superando el límite de 4096 de Telegram.

**Opciones:**
- Reducir `max_tokens` de 1500 a 800-1000 en `agent/summarizer.py`
- Ser más restrictivo en el system prompt: "Máximo 400 palabras" (actualmente dice 700)
- Reducir items por sección (3 noticias en vez de 4, 2 repos en vez de 5)
- Aceptar 2 mensajes y mejorarlo visualmente (agregar separador entre chunks)

---

## Deploy

### Opción A — Railway (recomendado para empezar)
```
# Procfile
worker: python scheduler.py
```
Costo: ~$5/mes.

### Opción B — Hetzner VPS
```bash
pip install -r requirements.txt
screen -S briefing python scheduler.py  # mantiene el proceso vivo
```
Costo: ~€4/mes (plan CX11).

---

## Lo que este agente NO hace

- No hace trading automático
- No envía alertas en tiempo real (solo 8am)
- No tiene interfaz web
- No aprende de feedback del usuario
- No scrapea sitios que bloqueen activamente bots
