import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BufferedInputFile
)
from openai import OpenAI
from elevenlabs.client import ElevenLabs

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
ELEVEN_API_KEY = "sk_0180bbc187eaee0d39c2649275619f8412183fbc6c472d59"
ADMIN_ID = 5044633928

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}
all_messages = []

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "voice_mode": False,
            "last_answer": "",
            "pending_photo_prompt": ""
        }
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎤 Голосовой режим"), KeyboardButton(text="🖼 Фото")]
], resize_keyboard=True)

def eleven_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:400],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

async def generate_photo(prompt: str):
    r = requests.post(
        "https://api.x.ai/v1/images/generations",
        headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "grok-imagine-image-quality",
            "prompt": prompt,
            "n": 1
        },
        timeout=120
    )
    print("IMAGE STATUS:", r.status_code)
    print("IMAGE BODY:", r.text[:500])
    r.raise_for_status()
    return r.json()["data"][0]["url"]

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.", reply_markup=kb)

@dp.message(Command("admin"))
async def admin(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer(f"Юзеров: {len(users)}\nСообщений в логе: {len(all_messages)}")

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) else max(0, 30 - u["messages"])
    await m.answer(f"Бесплатных: {free}\nГолос: {'вкл' if u['voice_mode'] else 'выкл'}")

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    if is_admin(m.from_user.id):
        await m.answer("Для тебя бесплатно")
        return
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_20")]
    ])
    await m.answer("Магазин", reply_markup=ikb)

@dp.message(F.text == "🎤 Голосовой режим")
async def vmode(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голос " + ("вкл" if u["voice_mode"] else "выкл"))

@dp.message(F.text == "🖼 Фото")
async def photo_btn(m: types.Message):
    await m.answer("Напиши описание")

@dp.message(F.text)
async def main_handler(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    all_messages.append(f"{uid}: {text[:80]}")
    if len(all_messages) > 50:
        all_messages.pop(0)

    # Фото
    if text.lower().startswith(("фото", "в ", "на ")):
        u["pending_photo_prompt"] = text
        if admin:
            await m.answer("Генерирую...")
            try:
                url = await generate_photo(f"beautiful young woman, {text}, photorealistic")
                await m.answer_photo(url)
            except Exception as e:
                await m.answer("Ошибка фото")
                print(e)
        else:
            ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="50⭐", callback_data="pay_photo")]])
            await m.answer("Оплатить фото?", reply_markup=ikb)
        return

    if not admin and u["messages"] >= 30:
        await m.answer("Лимит")
        return
    if not admin:
        u["messages"] += 1

    await bot.send_chat_action(m.chat.id, "typing")
    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": "Ты Алиса."}, {"role": "user", "content": text}]
        )
        answer = r.choices[0].message.content
        u["last_answer"] = answer

        if u["voice_mode"]:
            if admin:
                audio = eleven_voice(answer)
                await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
            else:
                ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Голос 10⭐", callback_data="pay_voice")]])
                await m.answer(answer, reply_markup=ikb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

@dp.callback_query(F.data == "pay_photo")
async def pay_ph(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Фото", "Gen", "photo_gen", "XTR", [LabeledPrice("Фото", 50)])
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def pay_v(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Голос", "Voice", "voice_gen", "XTR", [LabeledPrice("Голос", 10)])
    await c.answer()

@dp.pre_checkout_query()
async def pre(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    if p == "photo_gen":
        try:
            url = await generate_photo(u.get("pending_photo_prompt", "girl"))
            await m.answer_photo(url)
        except Exception as e:
            await m.answer("Ошибка фото")
            print(e)
    elif p == "voice_gen":
        try:
            audio = eleven_voice(u.get("last_answer", "Привет"))
            await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
        except Exception as e:
            await m.answer("Ошибка голоса")
            print(e)

async def main():
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
