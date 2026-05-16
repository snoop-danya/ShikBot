# ============================================================
#  handlers/registration.py — регистрация и /start
# ============================================================

import time
import random
import sqlite3
import logging

from aiogram import Router, F, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import STARTING_BALANCE, DAILY_BONUS_MIN, DAILY_BONUS_MAX
from utils.helpers import validate_nickname, fmt
from utils.keyboards import main_menu

log = logging.getLogger(__name__)
router = Router(name="registration")


class Reg(StatesGroup):
    nickname = State()
    gender   = State()


@router.message(CommandStart())
async def cmd_start(
    message: types.Message,
    state: FSMContext,
    command: CommandObject,
    cur: sqlite3.Cursor,
    db: sqlite3.Connection,
):
    user_id = message.from_user.id
    user = cur.execute("SELECT nickname, level, balance, last_login FROM users WHERE id=?", (user_id,)).fetchone()

    if not user:
        # Парсим реферала
        ref_id: int | None = None
        if command.args and command.args.strip().isdigit():
            candidate = int(command.args.strip())
            if candidate != user_id:
                ref_id = candidate

        await state.update_data(referrer_id=ref_id)
        await message.answer(
            "🏙 <b>ДОБРО ПОЖАЛОВАТЬ В БОТ Dexp0v Money!</b>\n\n"
            "Ты прибыл в город возможностей — здесь есть всё:\n"
            "от майнинга до бандитских разборок.\n\n"
            "✏️ Как тебя называть? (3–15 символов):",
            parse_mode="HTML",
        )
        await state.set_state(Reg.nickname)
        return

    # Уже зарегистрирован — обновляем last_login
    now = int(time.time())
    last_login = user[3] or 0
    bonus_text = ""

    if now - last_login >= 86_400:
        bonus = random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)
        cur.execute(
            "UPDATE users SET balance=balance+?, last_login=? WHERE id=?",
            (bonus, now, user_id),
        )
        db.commit()
        bonus_text = f"\n\n🎁 <b>Ежедневный бонус:</b> +{fmt(bonus)}₽"
    else:
        cur.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
        db.commit()

    await message.answer(
        f"🐺 Рады видеть тебя, <b>{user[0]}</b>!\n"
        f"📊 Уровень: {user[1]} | Баланс: {fmt(user[2])}₽{bonus_text}",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )


# ── Ввод ника ────────────────────────────────────────────

@router.message(Reg.nickname)
async def reg_nick(message: types.Message, state: FSMContext, cur: sqlite3.Cursor):
    nick = message.text.strip() if message.text else ""
    err  = validate_nickname(nick)
    if err:
        await message.answer(f"❌ {err}")
        return

    if cur.execute("SELECT 1 FROM users WHERE nickname=?", (nick,)).fetchone():
        await message.answer("❌ Этот ник уже занят! Выбери другой.")
        return

    await state.update_data(nickname=nick)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мужчина ♂️", callback_data="sg_male"),
         InlineKeyboardButton(text="Женщина ♀️", callback_data="sg_female")],
        [InlineKeyboardButton(text="Другое 👤",   callback_data="sg_other")],
    ])
    await message.answer(
        "👤 <b>Выбери пол своего персонажа:</b>\n\n"
        "Это повлияет на некоторые игровые события.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await state.set_state(Reg.gender)


# ── Выбор пола ───────────────────────────────────────────

GENDERS = {"sg_male": "Мужчина ♂️", "sg_female": "Женщина ♀️", "sg_other": "Другое 👤"}

@router.callback_query(F.data.in_(GENDERS), Reg.gender)
async def reg_gender(
    callback: types.CallbackQuery,
    state: FSMContext,
    cur: sqlite3.Cursor,
    db: sqlite3.Connection,
):
    data    = await state.get_data()
    nick    = data.get("nickname", "Игрок")
    ref_id  = data.get("referrer_id")
    gender  = GENDERS[callback.data]
    user_id = callback.from_user.id
    now     = int(time.time())

    # Двойная проверка — вдруг успел нажать дважды
    if cur.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
        await state.clear()
        await callback.message.answer("Главное меню:", reply_markup=main_menu())
        return

    cur.execute(
        "INSERT INTO users (id, nickname, gender, level, exp, balance, referrer_id, last_login) "
        "VALUES (?, ?, ?, 1, 0, ?, ?, ?)",
        (user_id, nick, gender, STARTING_BALANCE, ref_id, now),
    )

    # Реферальный бонус
    if ref_id and cur.execute("SELECT 1 FROM users WHERE id=?", (ref_id,)).fetchone():
        cur.execute("UPDATE users SET balance=balance+5000 WHERE id=?", (ref_id,))
        log.info("Реферальный бонус %s → %s", ref_id, user_id)

    db.commit()
    await state.clear()

    await callback.message.answer(
        f"🎉 <b>Добро пожаловать, {nick}!</b>\n\n"
        f"Твой стартовый баланс: <b>{fmt(STARTING_BALANCE)}₽</b>\n\n"
        f"Изучи меню ниже — здесь можно:\n"
        f"• ⚒ Работать и зарабатывать\n"
        f"• 🎰 Рисковать в казино\n"
        f"• ⚡️ Майнить криптовалюту\n"
        f"• 🔫 Создать банду и захватывать районы\n\n"
        f"Удачи в городе! 🏙",
        reply_markup=main_menu(),
        parse_mode="HTML",
    )
