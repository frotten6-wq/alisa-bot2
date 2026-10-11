import os
import asyncio
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BufferedInputFile
)
from openai import OpenAI
from elevenlabs.client import ElevenLabs

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
ELEVEN_API_KEY = "sk_0180bbc187eaee0d39c2649275619f8412183fbc6c472d59"
ADMIN_ID = 5044633928

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# ==================== ДАННЫЕ ====================
users = {}
logs = []

def get_user(uid: int) -> dict:
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "paid_messages": 0,
            "relationship": 0,
            "voice_mode": False,
            "name": None,
            "history": [],
            "last_answer": "",
            "photo_prompt": "",
            "joined": datetime.now().isoformat()
        }
    return users[uid]

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def add_log(text: str):
    logs.append(f"[{datetime.now().strftime('%H:%M')}] {text}")
    if len(logs) > 50:
        logs.pop(0)

# ==================== КЛАВИАТУРА ====================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💬 Написать"), KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎁 Подарок")],
        [KeyboardButton(text="🎤 Голос"), KeyboardButton(text="🖼 Фото")]
    ],
    resize_keyboard=True
)

# ==================== ГОЛОС И ФОТО ====================
def generate_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:450],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

def generate_image(prompt: str) -> str:
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
        timeout=100
    )
    r.raise_for_status()
    return r.json()["data"][0]["url"]

# ==================== СТАРТ И АДМИНКА ====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет. Я Алиса.\n\n"
        "Можем просто поболтать или пойти дальше.\n"
        "30 бесплатных сообщений.",
        reply_markup=main_kb
    )

@dp.message(Command("admin"))
async def admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    total = len(users)
    msgs = sum(u["messages"] for u in users.values())
    await message.answer(
        f"<b>Админ-панель</b>\n\n"
        f"Пользователей: {total}\n"
        f"Сообщений: {msgs}\n"
        f"В логе: {len(logs)}\n\n"
        f"/logs — последние сообщения",
        parse_mode="HTML"
    )

@dp.message(Command("logs"))
async def show_logs(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not logs:
        await message.answer("Лог пуст")
        return
    await message.answer("Последние записи:\n\n" + "\n".join(logs[-15:]))

# ==================== КНОПКИ ====================
@dp.message(F.text == "📊 Профиль")
async def profile(message: types.Message):
    u = get_user(message.from_user.id)
    admin = is_admin(message.from_user.id)
    free = "∞" if admin else max(0, 30 - u["messages"])
    name = u["name"] or "не указано"
    await message.answer(
        f"Имя: {name}\n"
        f"Отношения: {u['relationship']}/100\n"
        f"Бесплатных: {free}\n"
        f"Платных: {u['paid_messages']}\n"
        f"Голос: {'вкл' if u['voice_mode'] else 'выкл'}"
    )

@dp.message(F.text == "🛒 Магазин")
async def shop(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("Для тебя всё бесплатно")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="buy_50")],
        [InlineKeyboardButton(text="150 сообщений — 80⭐", callback_data="buy_150")]
    ])
    await message.answer("Магазин:", reply_markup=kb)

@dp.message(F.text == "🎁 Подарок")
async def gifts(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цветы — 15⭐", callback_data="gift_5")],
        [InlineKeyboardButton(text="Ужин — 40⭐", callback_data="gift_12")],
        [InlineKeyboardButton(text="Бельё — 70⭐", callback_data="gift_20")]
    ])
    await message.answer("Выбери подарок:", reply_markup=kb)

@dp.message(F.text == "🎤 Голос")
async def toggle_voice(message: types.Message):
    u = get_user(message.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    status = "включён" if u["voice_mode"] else "выключен"
    await message.answer(f"Голосовой режим {status}")

@dp.message(F.text == "🖼 Фото")
async def photo_help(message: types.Message):
    await message.answer("Напиши, какое фото хочешь.\nПример: в белье на кровати")

@dp.message(F.text.lower().startswith("меня зовут"))
async def set_name(message: types.Message):
    name = message.text.split(maxsplit=2)[-1]
    get_user(message.from_user.id)["name"] = name
    await message.answer(f"Хорошо, {name}")

# ==================== ОСНОВНОЙ ОБРАБОТЧИК ====================
@dp.message(F.text)
async def handle_text(message: types.Message):
    text = message.text.strip()
    uid = message.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    add_log(f"{uid}: {text[:50]}")

    # Фото
    low = text.lower()
    if low.startswith("фото") or "бель" in low or low.startswith("в "):
        u["photo_prompt"] = text
        if admin:
            await message.answer("Генерирую...")
            try:
                url = generate_image(f"beautiful young woman, {text}, detailed")
                await message.answer_photo(url)
            except Exception as e:
                await message.answer("Не вышло сгенерировать")
                print("IMG ERROR:", e)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
            ])
            await message.answer("Сгенерировать за 50⭐?", reply_markup=kb)
        return

    # Лимит
    if not admin and u["messages"] >= 30 and u["paid_messages"] <= 0:
        await message.answer("Сообщения закончились. Загляни в магазин.")
        return

    if not admin:
        if u["messages"] < 30:
            u["messages"] += 1
        else:
            u["paid_messages"] -= 1

    u["relationship"] = min(100, u["relationship"] + 1)
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 8:
        u["history"] = u["history"][-8:]

    await bot.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(0.6)

    name_part = f" Пользователя зовут {u['name']}." if u["name"] else ""
    system = (
        "Ты Алиса, 23 года. Живая, естественная, с лёгким чувством юмора. "
        "Поддерживаешь разговор, иногда задаёшь вопросы. "
        "Если пишут обычно — общаешься интересно. "
        "Если откровенно — плавно подстраиваешься, без резких отказов. "
        "Эмодзи используй редко."
        + name_part
    )

    messages = [{"role": "system", "content": system}] + u["history"]

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=messages,
            temperature=0.84,
            max_tokens=400
        )
        answer = r.choices[0].message.content
        u["last_answer"] = answer
        u["history"].append({"role": "assistant", "content": answer})

        if u["voice_mode"]:
            if admin or u["paid_messages"] >= 10:
                if not admin:
                    u["paid_messages"] -= 10
                audio = generate_voice(answer)
                await message.answer_voice(BufferedInputFile(audio, "voice.mp3"))
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Голосовым — 10⭐", callback_data="pay_voice")]
                ])
                await message.answer(answer, reply_markup=kb)
        else:
            await message.answer(answer)

    except Exception as e:
        await message.answer("Что-то пошло не так...")
        print("CHAT ERROR:", e)

# ==================== CALLBACK ОПЛАТА ====================
@dp.callback_query(F.data == "pay_photo")
async def invoice_photo(callback: types.CallbackQuery):
    await bot.send_invoice(
        callback.from_user.id,
        "Фото",
        "Генерация изображения",
        "photo",
        "XTR",
        [LabeledPrice(label="Фото", amount=50)]
    )
    await callback.answer()

@dp.callback_query(F.data == "pay_voice")
async def invoice_voice(callback: types.CallbackQuery):
    await bot.send_invoice(
        callback.from_user.id,
        "Голосовой ответ",
        "Алиса ответит голосом",
        "voice",
        "XTR",
        [LabeledPrice(label="Голос", amount=10)]
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def invoice_messages(callback: types.CallbackQuery):
    mapping = {"buy_20": (20, 15), "buy_50": (50, 35), "buy_150": (150, 80)}
    amount, price = mapping.get(callback.data, (20, 15))
    await bot.send_invoice(
        callback.from_user.id,
        f"{amount} сообщений",
        "Пакет сообщений",
        f"msg_{amount}",
        "XTR",
        [LabeledPrice(label="Сообщения", amount=price)]
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def invoice_gift(callback: types.CallbackQuery):
    mapping = {"gift_5": (5, 15, "Цветы"), "gift_12": (12, 40, "Ужин"), "gift_20": (20, 70, "Бельё")}
    rel, price, name = mapping.get(callback.data, (5, 15, "Подарок"))
    await bot.send_invoice(
        callback.from_user.id,
        name,
        "Подарок для Алисы",
        f"gift_{rel}",
        "XTR",
        [LabeledPrice(label=name, amount=price)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    u = get_user(message.from_user.id)

    if payload == "photo":
        await message.answer("Генерирую фото...")
        try:
            url = generate_image(u.get("photo_prompt") or "beautiful woman")
            await message.answer_photo(url)
        except Exception as e:
            await message.answer("Ошибка генерации")
            print(e)

    elif payload == "voice":
        try:
            audio = generate_voice(u.get("last_answer") or "Привет")
            await message.answer_voice(BufferedInputFile(audio, "v.mp3"))
        except Exception as e:
            await message.answer("Ошибка голоса")
            print(e)

    elif payload.startswith("msg_"):
        amount = int(payload.split("_")[1])
        u["paid_messages"] += amount
        await message.answer(f"Добавлено {amount} сообщений")

    elif payload.startswith("gift_"):
        rel = int(payload.split("_")[1])
        u["relationship"] = min(100, u["relationship"] + rel)
        await message.answer("Спасибо за подарок...")

# ==================== ЗАПУСК ====================
async def main():
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
