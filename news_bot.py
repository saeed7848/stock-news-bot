# bot.py — مراقبة S&P500 + Nasdaq100 (RSI + زخم + أخبار مترجمة + دعم/مقاومة/أهداف)

import time
import requests
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from googtrans import Translator
from datetime import datetime, timezone

# ========= الإعدادات =========
TOKEN        = "8230094281:AAEzAJ9GsK5kGqAxYBtH4UdJc2nDQ7kk4lQ"
CHAT_ID      = "-1003055214239"   # مثل: -100xxxxxxxxxxxx
NEWSAPI_KEY  = "277a6d15a59b40d6ac43db37ac7627fa"

INTERVAL_MIN = 10      # كل كم دقيقة يفحص
RSI_MIN      = 40
RSI_MAX      = 70
BATCH_SIZE   = 50      # كم سهم يفحص في كل دورة (لتخفيف الضغط)
MIN_PCT      = 2.0     # أقل تغير يومي ٪ ليعتبر زخم
VOL_MULT     = 1.5     # حجم اليوم > 1.5 * متوسط 20 يوم
# ============================

TG_URL      = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
translator  = Translator()

def send_message(text: str):
    try:
        requests.post(TG_URL, data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        }, timeout=15)
    except Exception as e:
        print("Telegram send error:", e)

# ===== أخبار سريعـة (NewsAPI) =====
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
            desc_ar  = translator.translate(desc,  dest="ar").text if desc  else ""
        except Exception:
            title_ar, desc_ar = title, desc

        block = f"📰 خبر عن {symbol}\n{title_ar}"
        if desc_ar:
            block += f"\n📝 {desc_ar}"
        if src:
            block += f"\n📌 المصدر: {src}"
        if link:
            block += f"\n🔗 {link}"
        return block
    except Exception as e:
        print("news_for_symbol error:", e)
        return None

# ===== تحليل السهم (سعر/RSI/دعم/مقاومة/أهداف) =====
def analyze_stock(symbol: str):
    try:
        df = yf.download(symbol, period="2mo", interval="1d", progress=False)
        if df.empty:
            return None

        # السعر الحالي والتغير
        price = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[-2]) if len(df) > 1 else price
        pct   = (price - prev) / prev * 100.0 if prev else 0.0

        # RSI 14
        rsi = ta.rsi(df["Close"], length=14).iloc[-1]
        if pd.isna(rsi):
            return None

        # أحجام
        vol_today = float(df["Volume"].iloc[-1])
        vol_avg20 = float(df["Volume"].tail(20).mean())

        # دعم/مقاومة سهلة (Pivot بسيط)
        recent = df.tail(10)
        support    = float(recent["Low"].min())
        resistance = float(recent["High"].max())

        # أهداف مبدئية (خطوة 1.5% و 3%)
        target1 = round(price * 1.015, 2)
        target2 = round(price * 1.03,  2)
        stop    = round(support * 0.99, 2)

        # فلترة الزخم
        if not (RSI_MIN <= rsi <= RSI_MAX):
            return None
        if pct < MIN_PCT and vol_today < vol_avg20 * VOL_MULT:
            return None

        # خبر (إن وجد)
        news_block = news_for_symbol(symbol)

        msg = (
            f"🚀 {symbol}\n"
            f"السعر: 💵 {round(price,2)}\n"
            f"التغير اليومي: {round(pct,2)}%\n"
            f"RSI: {round(float(rsi),1)}\n"
            f"الحجم: {int(vol_today):,} | متوسط 20يوم: {int(vol_avg20):,}\n"
            f"الدعم: {round(support,2)} | المقاومة: {round(resistance,2)}\n"
            f"الأهداف: 🎯 {target1} ، {target2}\n"
            f"وقف الخسارة: ⛔ {stop}"
        )
        if news_block:
            msg += f"\n\n{news_block}"
        return msg
    except Exception as e:
        print("analyze_stock error:", symbol, e)
        return None

# ===== قوائم المؤشرات (ويكيبيديا) =====
def get_sp500_tickers():
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        syms = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        return syms
    except Exception as e:
        print("get_sp500_tickers error:", e)
        return []

def get_nasdaq100_tickers():
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        # عادة الجدول الرابع/الأخير يحوي الرموز:
        for t in tables:
            if "Ticker" in t.columns or "Ticker symbol" in t.columns or "Symbol" in t.columns:
                col = "Ticker" if "Ticker" in t.columns else ("Ticker symbol" if "Ticker symbol" in t.columns else "Symbol")
                return t[col].astype(str).str.replace(".", "-", regex=False).tolist()
        return []
    except Exception as e:
        print("get_nasdaq100_tickers error:", e)
        return []

# ===== اختيار “المتحركين” (زخم) من القائمتين ثم فلترة RSI/حجم/تغير) =====
def get_movers():
    try:
        syms = set(get_sp500_tickers() + get_nasdaq100_tickers())
        if not syms:
            return []
        # خذ أول BATCH_SIZE رمز فقط لكل دورة لتقليل الضغط
        return list(syms)[:BATCH_SIZE]
    except Exception as e:
        print("get_movers error:", e)
        return []

# ===== تشغيل دورة واحدة =====
def run_once():
    tickers = get_movers()
    if not tickers:
        send_message("⚠️ تعذّر جلب قائمة الأسهم.")
        return

    found = 0
    for sym in tickers:
        msg = analyze_stock(sym)
        if msg:
            send_message(msg)
            found += 1

    if found == 0:
        send_message("ℹ️ لا توجد أسهم تحقق شروط الزخم حاليا.")

# ===== التشغيل المستمر =====
def main():
    send_message("✅ البوت بدأ (S&P500 + Nasdaq100)")
    while True:
        run_once()
        time.sleep(INTERVAL_MIN * 60)

if _name_ == "_main_":
    main()__main__":
    main()
