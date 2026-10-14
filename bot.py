import asyncio
import aiohttp
import os
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8881143340:AAHcv2eH_qe65SRpP5ez5VFC1q8KyNVaf48"
LAT, LON = 45.2047, 39.2183
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CHECK_INTERVAL = 600

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
subscribers = set()
last_state = {}

WEATHER_EMOJI = {0:"☀️",1:"🌤",2:"⛅️",3:"☁️",45:"🌫",48:"🌫",51:"🌦",53:"🌦",55:"🌧",56:"🌧",57:"🌧",61:"🌧",63:"🌧",65:"🌧",66:"🌧",67:"🌧",71:"🌨",73:"❄️",75:"❄️",77:"❄️",80:"🌧",81:"🌧",82:"🌧",85:"🌨",86:"🌨",95:"⛈",96:"⛈",99:"⛈"}
WEATHER_DESC = {0:"Ясно",1:"Преимущественно ясно",2:"Переменная облачность",3:"Пасмурно",45:"Туман",48:"Изморозь",51:"Слабая морось",53:"Морось",55:"Сильная морось",61:"Небольшой дождь",63:"Дождь",65:"Сильный дождь",71:"Небольшой снег",73:"Снег",75:"Сильный снег",80:"Ливень",81:"Ливень",82:"Сильный ливень",95:"Гроза",96:"Гроза с градом",99:"Сильная гроза"}
DAYS_SHORT = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
MONTHS_SHORT = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]

def emoji(code): return WEATHER_EMOJI.get(code, "❓")
def desc(code): return WEATHER_DESC.get(code, "Неизвестно")

async def fetch_forecast(days=16):
    params = {"latitude":LAT,"longitude":LON,
        "current":"temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,uv_index",
        "hourly":"temperature_2m,weather_code,precipitation,wind_speed_10m",
        "daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone":"auto","forecast_days":days}
    async with aiohttp.ClientSession() as s:
        async with s.get(FORECAST_URL, params=params) as r:
            return await r.json()

async def fetch_year_archive(year):
    params = {"latitude":LAT,"longitude":LON,"start_date":f"{year}-01-01","end_date":f"{year}-12-31","daily":"temperature_2m_mean","timezone":"auto"}
    async with aiohttp.ClientSession() as s:
        async with s.get(ARCHIVE_URL, params=params) as r:
            return await r.json()

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Сегодня", callback_data="today"), InlineKeyboardButton(text="🌤 Завтра", callback_data="tomorrow")],
        [InlineKeyboardButton(text="📅 Неделя", callback_data="week"), InlineKeyboardButton(text="📆 Месяц", callback_data="month")],
        [InlineKeyboardButton(text="🗓 Год (климат)", callback_data="year")],
        [InlineKeyboardButton(text="🔔 Подписаться", callback_data="sub")],
        [InlineKeyboardButton(text="🔕 Отписаться", callback_data="unsub")]])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]])

def render_today(data):
    c = data["current"]; today = datetime.now().strftime("%Y-%m-%d")
    lines = []; h = data["hourly"]
    for i, t in enumerate(h["time"]):
        if t.startswith(today):
            hh = int(t[11:13]); temp = round(h["temperature_2m"][i])
            code = h["weather_code"][i]; rain = h["precipitation"][i]; wind = round(h["wind_speed_10m"][i])
            r_s = f" 🌧{rain:.1f}мм" if rain > 0 else ""
            lines.append(f"`{hh:02d}:00` {emoji(code)} {temp:+d}°C 💨{wind}км/ч{r_s}")
    return (f"📍 *Динской район — Сегодня*\n\n{emoji(c['weather_code'])} *{desc(c['weather_code'])}*\n"
            f"🌡 Температура: *{round(c['temperature_2m'])}°C*\n🤔 Ощущается: *{round(c['apparent_temperature'])}°C*\n"
            f"💨 Ветер: *{round(c['wind_speed_10m'])} км/ч*\n💧 Влажность: *{c['relative_humidity_2m']}%*\n"
            f"🔆 УФ-индекс: *{round(c.get('uv_index') or 0)}*\n\n🕐 *По часам:*\n" + "\n".join(lines))

def render_tomorrow(data):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    d, h = data["daily"], data["hourly"]
    idx = d["time"].index(tomorrow); lines = []
    for i, t in enumerate(h["time"]):
        if t.startswith(tomorrow):
            hh = int(t[11:13]); temp = round(h["temperature_2m"][i])
            c = h["weather_code"][i]; r = h["precipitation"][i]; w = round(h["wind_speed_10m"][i])
            r_s = f" 🌧{r:.1f}мм" if r > 0 else ""
            lines.append(f"`{hh:02d}:00` {emoji(c)} {temp:+d}°C 💨{w}км/ч{r_s}")
    return (f"📍 *Динской район — Завтра*\n\n{emoji(d['weather_code'][idx])} *{desc(d['weather_code'][idx])}*\n"
            f"🌡 Макс/мин: *{round(d['temperature_2m_max'][idx])}°C / {round(d['temperature_2m_min'][idx])}°C*\n"
            f"💨 Ветер до: *{round(d['wind_speed_10m_max'][idx])} км/ч*\n💧 Осадки: *{d['precipitation_sum'][idx]:.1f} мм*\n\n"
            f"🕐 *По часам:*\n" + "\n".join(lines))

def render_days_range(data, days, title):
    d = data["daily"]; lines = [f"📍 *Динской район — {title}*\n"]
    for i in range(min(days, len(d["time"]))):
        date = datetime.fromisoformat(d["time"][i]); wd = DAYS_SHORT[date.weekday()]
        code = d["weather_code"][i]
        tmax, tmin = round(d["temperature_2m_max"][i]), round(d["temperature_2m_min"][i])
        rain = d["precipitation_sum"][i]; wind = round(d["wind_speed_10m_max"][i])
        r_s = f" 🌧{rain:.1f}мм" if rain > 0 else ""
        lbl = "Сегодня" if i == 0 else ("Завтра" if i == 1 else wd)
        lines.append(f"*{lbl}* ({date.day} {MONTHS_SHORT[date.month-1]}): {emoji(code)} {desc(code)}\n   🌡 {tmax:+d}°C / {tmin:+d}°C 💨{wind}км/ч{r_s}")
    return "\n".join(lines)

async def render_year():
    year = datetime.now().year - 1
    data = await fetch_year_archive(year)
    d = data["daily"]; sums, counts = [0.0]*12, [0]*12
    for i, t in enumerate(d["time"]):
        v = d["temperature_2m_mean"][i]
        if v is None: continue
        m = int(t[5:7]) - 1; sums[m] += v; counts[m] += 1
    lines = [f"📍 *Динской район — климат за {year} год*\n"]
    for m in range(12):
        if counts[m] == 0: continue
        avg = sums[m] / counts[m]
        icon = "❄️" if m in (0,1,11) else "☀️" if m in (5,6,7) else "🌤"
        lines.append(f"{icon} *{MONTHS_SHORT[m]}*: *{avg:+.1f}°C*")
    return "\n".join(lines)

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer("👋 *Погода в Динском районе*\nВыберите раздел:", reply_markup=main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery):
    await c.message.edit_text("Меню:", reply_markup=main_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "today")
async def cb_today(c: CallbackQuery):
    await c.answer("Загружаю…")
    await c.message.edit_text(render_today(await fetch_forecast(2)), reply_markup=back_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "tomorrow")
async def cb_tomorrow(c: CallbackQuery):
    await c.answer("Загружаю…")
    await c.message.edit_text(render_tomorrow(await fetch_forecast(3)), reply_markup=back_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "week")
async def cb_week(c: CallbackQuery):
    await c.answer("Загружаю…")
    await c.message.edit_text(render_days_range(await fetch_forecast(7), 7, "Неделя"), reply_markup=back_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "month")
async def cb_month(c: CallbackQuery):
    await c.answer("Загружаю…")
    await c.message.edit_text(render_days_range(await fetch_forecast(16), 16, "Месяц"), reply_markup=back_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "year")
async def cb_year(c: CallbackQuery):
    await c.answer("Считаю…")
    await c.message.edit_text("⏳ Загружаю архив…", reply_markup=back_kb())
    await c.message.edit_text(await render_year(), reply_markup=back_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "sub")
async def cb_sub(c: CallbackQuery):
    subscribers.add(c.from_user.id)
    await c.answer("Вы подписаны 🔔", show_alert=True)

@dp.callback_query(F.data == "unsub")
async def cb_unsub(c: CallbackQuery):
    subscribers.discard(c.from_user.id)
    await c.answer("Вы отписаны 🔕", show_alert=True)

async def weather_monitor():
    global last_state
    await asyncio.sleep(15)
    while True:
        try:
            data = await fetch_forecast(2); cur = data["current"]
            new_state = {"temp": round(cur["temperature_2m"]), "code": cur["weather_code"], "wind": round(cur["wind_speed_10m"])}
            if last_state and subscribers:
                changed = (abs(new_state["temp"] - last_state["temp"]) >= 2 or
                          new_state["code"] != last_state["code"] or
                          abs(new_state["wind"] - last_state["wind"]) >= 5)
                if changed:
                    text = (f"🔔 *Погода изменилась!*\n\n{emoji(new_state['code'])} *{desc(new_state['code'])}*\n"
                            f"🌡 {new_state['temp']:+d}°C\n💨 Ветер: {new_state['wind']} км/ч")
                    for uid in list(subscribers):
                        try: await bot.send_message(uid, text, parse_mode="Markdown")
                        except Exception: subscribers.discard(uid)
            last_state = new_state
        except Exception as e:
            print("monitor error:", e)
        await asyncio.sleep(CHECK_INTERVAL)

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"Web server on port {port}")

async def main():
    asyncio.create_task(weather_monitor())
    asyncio.create_task(start_webserver())
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())