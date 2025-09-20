# bot.py — مراقبة S&P500 + Nasdaq100 (RSI + دعم/مقاومة + أخبار مترجمة)

import time
import requests
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from googletrans import Translator
from datetime import datetime, timezone

# ================== الإعدادات ==================
TOKEN        = "8230094281:AAEzAJ9GsK5kGqAxYBtH4UdJc2nDQ7kk4lQ"
CHAT_ID      = "-100xxxxxxxxxxxx"     # آي دي القناة
NEWSAPI_KEY  = "مفتاح_NewsAPI"
INTERVAL_MIN = 10                     # كل كم دقيقة يفحص
RSI_MIN      = 40
RSI_MAX      = 70
BATCH_SIZE   = 50                     # كم سهم يفحص في كل دورة (لتخفيف الضغط)
# ==============================================

TG_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
translator = Translator()

# ====== إرسال تيليجرام ======
def send_message(text: str):
    try:
        requests.post(TG_URL, data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        }, timeout=15)
    except Exception as e:
        print("Telegram send error:", e)

# ====== جلب خبر مترجم ======
def news_for_symbol(symbol: str):
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": symbol,
            "pageSize": 1,
            "sortBy": "publishedAt",
            "language": "en",
            "apiKey": NEWSAPI_KEY
        }
        r = requests.get(url, params=params, timeout=15)
        arts = (r.json() or {}).get("articles") or []
        if not arts:
            return None
        a = arts[0]
        title = a.get("title") or ""
        desc  = a.get("description") or ""
        src   = (a.get("source") or {}).get("name", "")
        link  = a.get("url") or ""

        try:
            title_ar = translator.translate(title, dest="ar").text if title else ""
            desc_ar  = translator.translate(desc,  dest="ar").text if desc else ""
        except:
            title_ar, desc_ar = title, desc

        block = f"📰 خبر {symbol}\n{title_ar}"
        if desc_ar: block += f"\n{desc_ar}"
        if src:     block += f"\n📌 المصدر: {src}"
        if link:    block += f"\n🔗 {link}"
        return block
    except:
        return None

# ====== تحليل السهم ======
def analyze_stock(symbol: str):
    try:
        df = yf.download(symbol, period="1mo", interval="1d", progress=False)
        if df.empty:
            return None
        price = df["Close"].iloc[-1]
        rsi = ta.rsi(df["Close"], length=14).iloc[-1]
        if pd.isna(rsi):
            return None
        if not (RSI_MIN <= rsi <= RSI_MAX):
            return None

        support = df["Low"].tail(20).min()
        resistance = df["High"].tail(20).max()
        target1 = round(price * 1.05, 2)
        target2 = round(price * 1.10, 2)

        news_block = news_for_symbol(symbol)

        msg = f"""
🚀 {symbol}
💵 السعر: {round(price,2)}
📈 مقاومة: {round(resistance,2)}
📉 دعم (وقف): {round(support,2)}
🎯 هدف1: {target1} | 🎯 هدف2: {target2}
📊 RSI: {round(rsi,2)}
"""
        if news_block:
            msg += "\n—\n" + news_block
        return msg.strip()
    except:
        return None

# ====== جلب قوائم المؤشرات ======
def get_sp500_tickers():
    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        return table[0]["Symbol"].tolist()
    except:
        return []

def get_nasdaq100_tickers():
    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        return table[4]["Ticker"].tolist()
    except:
        return []

# ====== تشغيل دورة واحدة ======
def run_once():
    tickers = list(set(get_sp500_tickers() + get_nasdaq100_tickers()))
    if not tickers:
        send_message("⚠️ تعذر جلب قائمة الأسهم.")
        return
    found = 0
    for sym in tickers[:BATCH_SIZE]:  # دفعة أولى
        msg = analyze_stock(sym)
        if msg:
            send_message(msg)
            found += 1
    if found == 0:
        send_message("ℹ️ لا توجد أسهم تحقق شروط الزخم حالياً.")

# ====== التشغيل المستمر ======
def main():
    send_message("✅ البوت بدأ (S&P500 + Nasdaq100)")
    while True:
        run_once()
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
