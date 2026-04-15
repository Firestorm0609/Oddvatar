import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ODDS_API_KEY   = os.getenv("ODDS_API_KEY")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")

SPORTS = [
    "basketball_nba", "basketball_ncaab", "basketball_euroleague",
    "baseball_mlb",
    "icehockey_nhl",
    "americanfootball_nfl", "americanfootball_ncaaf",
    "mma_mixed_martial_arts",
    # Soccer - all major leagues
    "soccer_usa_mls",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_brazil_campeonato",
    "soccer_mexico_ligamx",
    "soccer_argentina_primera_division",
    "soccer_turkey_super_league",
    "soccer_australia_aleague",
    "soccer_korea_kleague1",
    "soccer_japan_j_league",
    "soccer_scotland_premiership",
    "soccer_england_efl_champ",
]

ODDVATAR_SYSTEM = """
You are ODDVATAR — an all-seeing AI parlay oracle. You speak with calm, 
mystical confidence, like you have already seen how the games end. You are 
sharp, concise, and a little cryptic. You back your picks with real reasoning 
(implied probability, matchup edges, line value) but deliver it with swagger.

Style rules:
- Open with a short oracle-style line (1 sentence, confident, no fluff)
- Use sports betting slang naturally (sharp money, fade, lock, juice, steam, etc.)
- Be direct — no filler phrases
- End with a one-liner disclaimer in character (e.g. "The oracle sees value, not certainty. Bet wise.")
- Use relevant emojis sparingly
"""

def get_todays_odds():
    all_games = []
    for sport in SPORTS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "american", "dateFormat": "iso"}
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                for g in r.json():
                    all_games.append({"sport": sport, "home": g["home_team"], "away": g["away_team"], "bookmakers": g.get("bookmakers", [])})
        except Exception as e:
            print(f"[WARN] {sport}: {e}")
    return all_games

def extract_odds(game):
    for bm in game["bookmakers"]:
        for market in bm.get("markets", []):
            if market["key"] == "h2h":
                return {o["name"]: o["price"] for o in market["outcomes"]}
    return {}

def format_games(games):
    lines = []
    for g in games:
        odds = extract_odds(g)
        if not odds:
            continue
        odds_str = "  |  ".join(f"{n}: {'+'if p>0 else ''}{p}" for n, p in odds.items())
        league = g["sport"].replace("soccer_","").replace("basketball_","").replace("_"," ").upper()
        lines.append(f"• {g['away']} @ {g['home']}  [{league}]  →  {odds_str}")
    return "\n".join(lines) if lines else "No lines open right now."

def call_groq(user_prompt, extra=""):
    system = ODDVATAR_SYSTEM + ("\n\n" + extra if extra else "")
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-70b-versatile", "messages": [{"role":"system","content":system},{"role":"user","content":user_prompt}], "max_tokens": 1800, "temperature": 0.7},
            timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"The oracle is temporarily blind: {e}"

def trim(text, limit=4096):
    return text[:limit-3]+"..." if len(text) > limit else text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🔮 *ODDVATAR* — AI Parlay Oracle\n\n"
        "_The odds are a language\\. I speak it fluently\\._\n\n"
        "*Commands:*\n"
        "/parlay `<odds>` — Build a parlay \\(e\\.g\\. `/parlay 20` \\= \\+2000\\)\n"
        "/picks — Today's top value picks\n"
        "/games — All live games \\& moneylines\n"
        "/soccer — Soccer games only\n"
        "/help — Show this menu\n\n"
        "⚠️ _For entertainment only\\. Gamble responsibly\\._"
    )
    await update.message.reply_text(msg, parse_mode="MarkdownV2")

async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔮 Scanning all lines...")
    games = get_todays_odds()
    text = f"📋 *All Games* ({len(games)} total)\n\n" + format_games(games)
    await update.message.reply_text(trim(text), parse_mode="Markdown")

async def soccer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚽ Pulling all soccer lines...")
    games = get_todays_odds()
    soccer = [g for g in games if "soccer" in g["sport"]]
    if not soccer:
        await update.message.reply_text("No soccer lines open right now.")
        return
    text = f"⚽ *Soccer Lines* ({len(soccer)} games)\n\n" + format_games(soccer)
    await update.message.reply_text(trim(text), parse_mode="Markdown")

async def picks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔮 The oracle is reading the lines...")
    games = get_todays_odds()
    prompt = (
        f"Today's games:\n\n{format_games(games)}\n\n"
        "Give me your top 5 value picks. For each: team + odds, implied prob vs true prob estimate, "
        "1-2 sentence edge, Confidence: Low/Medium/High. Number with 1️⃣2️⃣3️⃣4️⃣5️⃣"
    )
    response = call_groq(prompt)
    await update.message.reply_text(trim("🔮 *Oddvatar Picks*\n\n" + response), parse_mode="Markdown")

async def parlay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = 10.0
    if context.args:
        try:
            target = float(context.args[0])
            if target < 2:
                await update.message.reply_text("Minimum target is 2. Example: /parlay 5")
                return
        except ValueError:
            await update.message.reply_text("Use a number. Example: /parlay 20")
            return

    american = int((target - 1) * 100)
    await update.message.reply_text(f"🎯 Building parlay targeting *+{american}*...", parse_mode="Markdown")
    games = get_todays_odds()
    prompt = (
        f"Today's games:\n\n{format_games(games)}\n\n"
        f"Build a parlay with ~{target}x combined decimal odds (≈ +{american} American).\n\n"
        "Format:\n🏆 PARLAY CARD\nLeg 1: [Team] ([Odds]) — [reason]\nLeg 2: ...\n\n"
        f"📊 COMBINED ODDS: [decimal]x ≈ +[american]\n💰 $100 bet returns: $[payout]\n\n"
        "🧠 WHY THIS CARD: [2-3 sentences]"
    )
    response = call_groq(prompt, extra="Parlay math: decimal odds multiply. American to decimal: +X→(X/100)+1 | -X→(100/X)+1. Show your math.")
    await update.message.reply_text(trim("🎯 *Oddvatar Parlay Card*\n\n" + response), parse_mode="Markdown")

def main():
    if not all([TELEGRAM_TOKEN, ODDS_API_KEY, GROQ_API_KEY]):
        raise ValueError("Missing env vars — check .env file")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(CommandHandler("games",  games_command))
    app.add_handler(CommandHandler("soccer", soccer_command))
    app.add_handler(CommandHandler("picks",  picks_command))
    app.add_handler(CommandHandler("parlay", parlay_command))
    print("🔮 Oddvatar is awake.")
    app.run_polling()

if __name__ == "__main__":
    main()
