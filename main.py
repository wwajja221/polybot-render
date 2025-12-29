import requests
import time
import telegram
import asyncio
import os
from threading import Thread
from flask import Flask
from datetime import datetime

# --- CONFIGURATION PERSO ---
TELEGRAM_TOKEN = "7642660873:AAGiXckpM40zBVyx6ZFbW1OKmvHOFhj-cAs"
CHAT_ID = "1200147518"

# ==========================================
# 🌐 PARTIE 1 : LE FAUX SERVEUR WEB (POUR RENDER)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "<h1>🤖 Bot PolySniper en ligne !</h1>"

def run_web_server():
    # Render nous donne un port spécifique, on doit l'utiliser
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def start_server_thread():
    # On lance le serveur dans un "fil" séparé pour ne pas bloquer le bot
    t = Thread(target=run_web_server)
    t.start()

# ==========================================
# 🤖 PARTIE 2 : LE BOT (Moteur V14)
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

WATCHLIST = {
    # --- LEGENDES ---
    "0xd1c769317bd15de7768a70d0214cf0bbcc531d2b": {"name": "Theo4", "tags": ["politics", "us-election"], "tier": "S"},
    "0x2b38036d0132a0c493c4df42125e839211c21062": {"name": "PuntGod", "tags": ["politics", "crypto"], "tier": "A"},
    "0x6c3aae17140c5e3cde62380daaa323e38575c459": {"name": "Avraham", "tags": ["politics", "middle-east"], "tier": "S"},
    "0x84898b583d56054b502c6564f3edfad43b54e211": {"name": "Domah", "tags": ["volume", "mixed"], "tier": "A"},
    "0x006cc834Cc092684F1B56626E23BEdB3835c16ea": {"name": "TopG", "tags": ["finance"], "tier": "A"},
    # --- AUTRES ---
    "0x1489046ca0f9980fc2d9a950d103d3bec02c1307": {"name": "Whale_1489", "tags": ["mixed"], "tier": "B"},
    "0x7f3c8979d0afa00007bae4747d5347122af05613": {"name": "Whale_7f3c", "tags": ["sports"], "tier": "B"},
    "0xa9b44dca52ed35e59ac2a6f49d1203b8155464ed": {"name": "Whale_a9b4", "tags": ["mixed"], "tier": "B"},
    "0x8e9eedf20dfa70956d49f608a205e402d9df38e4": {"name": "Whale_8e9e", "tags": ["crypto"], "tier": "B"},
    "0x12d6cccfc7470a3f4bafc53599a4779cbf2cf2a8": {"name": "Whale_12d6", "tags": ["mixed"], "tier": "B"},
    "0xc02147dee42356b7a4edbb1c35ac4ffa95f61fa8": {"name": "Whale_c021", "tags": ["mixed"], "tier": "B"},
    "0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f": {"name": "Whale_8f42", "tags": ["mixed"], "tier": "B"},
    "0x06dcaa14f57d8a0573f5dc5940565e6de667af59": {"name": "Whale_06dc", "tags": ["mixed"], "tier": "B"},
    "0xe542afd3881c4c330ba0ebbb603bb470b2ba0a37": {"name": "Whale_e542", "tags": ["mixed"], "tier": "B"},
    "0x4ce73141dbfce41e65db3723e31059a730f0abad": {"name": "Whale_4ce7", "tags": ["mixed"], "tier": "B"}
}

known_positions = set()

async def send_telegram_alert(message):
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Erreur Telegram : {e}")

def get_positions_data(wallet_address):
    time.sleep(0.5) 
    url = f"https://data-api.polymarket.com/positions?user={wallet_address}&limit=20&sortBy=CURRENT&sortDirection=DESC"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200: return response.json()
        return []
    except Exception: return []

def get_real_slug_from_gamma(token_id):
    try:
        url = f"https://gamma-api.polymarket.com/markets?token_id={token_id}"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0].get('slug')
    except Exception: pass
    return None

def get_best_link(pos):
    asset_id = pos.get('asset')
    if asset_id:
        real_slug = get_real_slug_from_gamma(asset_id)
        if real_slug: return f"https://polymarket.com/event/{real_slug}"
    market_info = pos.get('market')
    if market_info and isinstance(market_info, dict):
        event_slug = market_info.get('slug')
        if event_slug: return f"https://polymarket.com/event/{event_slug}"
    return "https://polymarket.com"

def analyze_order_book(asset_id):
    if not asset_id: return None
    url = f"https://clob.polymarket.com/book?token_id={asset_id}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200: return None
        book = resp.json()
        bids, asks = book.get('bids', []), book.get('asks', [])
        if not bids or not asks: return {"status": "DEAD", "spread": 0, "liquidity": 0}
        best_bid, best_ask = float(bids[0]['price']), float(asks[0]['price'])
        spread = best_ask - best_bid
        bid_depth = sum([float(x['size']) for x in bids[:3]])
        ask_depth = sum([float(x['size']) for x in asks[:3]])
        total_depth = (bid_depth + ask_depth) * ((best_bid + best_ask)/2)
        return {"status": "OK", "best_bid": best_bid, "best_ask": best_ask, "spread": spread, "liquidity_usd": total_depth}
    except Exception: return None

def calculate_smart_score(profile, pos, price, liquidity_data):
    score, reasons, special_header = 50, [], False
    if liquidity_data and liquidity_data['status'] == "OK":
        if liquidity_data['spread'] > 0.05:
            score += 20
            reasons.append(f"⚠️ **SPREAD ÉNORME ({liquidity_data['spread']:.2f}cts)**")
            special_header = True
        if liquidity_data['liquidity_usd'] < 500:
            score -= 10
            reasons.append(f"⚠️ **Marché Illiquide** (<500$)")
            special_header = True
    bet_type_name = "Standard"
    if price >= 0.90 or price <= 0.10:
        bet_type_name = "Arbi / Safe"; score += 10
    elif 0.40 <= price <= 0.60:
        bet_type_name = "Coinflip"; score -= 5
    match = any(t in pos.get('slug', '').lower() for t in profile['tags']) or "mixed" in profile['tags']
    if match: score += 15
    else: score -= 20; reasons.append(f"Hors spécialité ({profile['tags'][0]})")
    if float(pos.get('currentValue', 0)) > 5000: score += 10; reasons.append("Grosse conviction")
    return min(max(score, 0), 100), reasons, bet_type_name, special_header, liquidity_data

def format_alert(address, pos, is_test=False):
    profile = WATCHLIST.get(address, {"name": "Inconnu", "tags": ["mixed"], "tier": "C"})
    title = pos.get('title', 'Marché Inconnu')
    link = get_best_link(pos)
    size = float(pos.get('size', 0))
    value = float(pos.get('currentValue', 0))
    price = value / size if size > 0 else 0
    avg_buy = float(pos.get('avgPrice', 0))
    
    liquidity_data = analyze_order_book(pos.get('asset'))
    final_score, reasons, bet_type, is_incentive, liq_info = calculate_smart_score(profile, pos, price, liquidity_data)
    
    header = "🚨💰 <b>INCENTIVE</b>" if is_incentive else "🧪 <b>TEST</b>" if is_test else "📊 <b>NOUVEAU SIGNAL</b>"
    
    liq_block = ""
    if liq_info and liq_info['status'] == "OK":
        warn = "⚠️" if liq_info['spread'] > 0.03 else "💧"
        liq_block = f"\n{warn} <b>Book:</b> Spread {liq_info['spread']:.3f} | Profondeur ~{int(liq_info['liquidity_usd'])}$"

    msg = f"""
{header}
──────────────────
✨ <b>Signal {final_score}/100</b> ({bet_type})
👤 <b>{profile['name']}</b> sur "{title}"
🔗 <a href="{link}">Voir le Marché</a>

📈 <b>{pos.get('outcome', '?')}</b> @ {price:.3f} (Entrée: {avg_buy:.3f})
💰 Taille: {value:,.0f} $
{liq_block}
🔍 <b>Facteurs :</b>
{chr(10).join(['- '+r for r in reasons])}
"""
    return msg

async def main_loop():
    print("🚀 Bot V15 Render Démarré.")
    # Séquence de démarrage
    if WATCHLIST:
        test_addr = list(WATCHLIST.keys())[0]
        pos = get_positions_data(test_addr)
        if pos: await send_telegram_alert(format_alert(test_addr, pos[0], is_test=True))
    
    # Chargement mémoire
    for addr in WATCHLIST:
        p = get_positions_data(addr)
        if p:
            for item in p: known_positions.add(f"{addr}_{item.get('asset')}_{item.get('size')}")
    print("✅ Mémoire OK.")
    
    while True:
        print(f"⏳ Scan...")
        for addr in WATCHLIST:
            p = get_positions_data(addr)
            if not p: continue
            for item in p:
                uid = f"{addr}_{item.get('asset')}_{item.get('size')}"
                if uid not in known_positions:
                    known_positions.add(uid)
                    await send_telegram_alert(format_alert(addr, item))
                    break
        await asyncio.sleep(60)

if __name__ == "__main__":
    # C'est la ligne MAGIQUE qui permet de lancer le site ET le bot en même temps
    start_server_thread()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_loop())
    except KeyboardInterrupt:
        pass
