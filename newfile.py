import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, FSInputFile, BufferedInputFile
from openai import OpenAI
from elevenlabs.client import ElevenLabs

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
ELEVEN_API_KEY = "sk_0180bbc187eaee0d39c2649275619f8412183fbc6c472d59"

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "messages": 0, "paid": 0, "relationship": 0,
            "name": None, "history": [], "voice_mode": False
        }
    return users[uid]

def get_level(p):
    if p < 25: return "знакомство"
    if p < 60: return "флирт"
    return "близкие"

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎁 Подарок"), KeyboardButton(text="🎤 Голосовой режим")],
    [KeyboardButton(text="🖼 Сгенерировать фото")]
], resize_keyboard=True)

def generate_voice_eleven(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text,
        voice_id="EXAVITQu4vr4xnSDxMaL",  # Sarah или другой голос
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

def generate_image_grok(prompt: str) -> str:
    response = requests.post(
        "https://api.x.ai/v1/images/generations",
        headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "grok-imagine-image-quality",
            "prompt": prompt,
            "n": 1
        }
    )
    data = response.json()
    return data["data"][0]["url"]

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.", reply_markup=kb)

@dp.message(F.text == "🎤 Голосовой режим")
async def toggle_voice(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer(f"Голосовой режим {'включён' if u['voice_mode'] else 'выключен'}")

@dp.message(F.text == "🖼 Сгенерировать фото")
async def ask_photo(m: types.Message):
    await m.answer("Напиши, какое фото хочешь (50⭐).\nПример: фото в белье")

@dp.message(F.text.lower().startswith("фото "))
async def gen_photo(m: types.Message):
    u = get_user(m.from_user.id)
    if u["paid"] < 50:
        await m.answer("Нужно 50 платных сообщений")
        return
    u["paid"] -= 50
    prompt = m.text[5:]
    await m.answer("Генерирую...")
    try:
        url = generate_image_grok(f"красивая девушка, {prompt}, высокое качество")
        await m.answer_photo(url)
    except Exception as e:
        await m.answer("Не получилось сгенерировать")
        print(e)

@dp.message(F.text)
async def chat(m: types.Message):
    u = get_user(m.from_user.id)
    if u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Бесплатные закончились")
        return
    if u["messages"] < 30:
        u["messages"] += 1
    else:
        u["paid"] -= 1

    u["history"].append({"role": "user", "content": m.text})
    if len(u["history"]) > 6:
        u["history"] = u["history"][-6:]

    await bot.send_chat_action(m.chat.id, "typing")

    system = "Ты Алиса, живая девушка 23 лет. Общайся естественно."
    messages = [{"role": "system", "content": system}] + u["history"]

    try:
        r = client.chat.completions.create(model="grok-4", messages=messages, temperature=0.8)
        answer = r.choices[0].message.content
        u["history"].append({"role": "assistant", "content": answer})

        if u["voice_mode"] and u["paid"] >= 15:
            u["paid"] -= 15
            audio = generate_voice_eleven(answer)
            await m.answer_voice(BufferedInputFile(audio, filename="voice.mp3"))
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

# Остальные обработчики (магазин, оплата и т.д.) оставь из предыдущей версии
# или скажи — допишу полный файл

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
