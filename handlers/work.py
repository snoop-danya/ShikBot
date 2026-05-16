# ============================================================
#  handlers/work.py — работа и казино
# ============================================================

import time
import random
import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import WORK_COOLDOWN, WORK_MIN, WORK_MAX, WORK_EXP, CASINO_MIN_BET
from utils.helpers import (
    require_registered, require_registered_cb,
    add_stats, add_transaction, fmt,
)
from utils.keyboards import main_menu

router = Router(name="work")

JOBS = [
    ("💼 Менеджер",       "работал менеджером"),
    ("🚕 Таксист",         "катал пассажиров"),
    ("🍕 Курьер",          "развозил пиццу"),
    ("🔧 Механик",         "чинил машины"),
    ("👨‍💻 Программист",    "писал код"),
    ("🎲 Крупье",          "работал в казино"),
    ("🏗 Строитель",       "строил дома"),
    ("🎸 Музыкант",        "играл на улице"),
    ("📦 Грузчик",         "таскал коробки"),
    ("🌮 Повар",           "готовил еду"),
]


# ──────────────────────────────────────────────────────────
#  РАБОТА
# ──────────────────────────────────────────────────────────

@router.message(F.text == "⚒ Биржа Труда")
@require_registered
async def work_menu(message: types.Message, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    user_id   = message.from_user.id
    last_work = cur.execute("SELECT last_work FROM users WHERE id=?", (user_id,)).fetchone()[0] or 0
    now       = int(time.time())
    cooldown  = now - last_work

    if cooldown < WORK_COOLDOWN:
        remaining = WORK_COOLDOWN - cooldown
        m, s = divmod(remaining, 60)
        await message.answer(
            f"⏳ <b>Ты уже работал сегодня!</b>\n\n"
            f"Следующая работа через: <b>{m:02d}:{s:02d}</b>",
            parse_mode="HTML",
        )
        return

    job_name, job_desc  = random.choice(JOBS)
    money = random.randint(WORK_MIN, WORK_MAX)
    bonus = 0

    # Бонус за стрик (каждый 5-й уровень)
    level = cur.execute("SELECT level FROM users WHERE id=?", (user_id,)).fetchone()[0]
    if level and level % 5 == 0:
        bonus = money // 2

    total     = money + bonus
    new_lvl, new_exp = add_stats(db, cur, user_id, total, WORK_EXP)
    cur.execute("UPDATE users SET last_work=? WHERE id=?", (now, user_id))
    db.commit()

    # Обновляем прогресс квеста "work"
    _update_quest_progress(cur, db, user_id, "work", 1)

    text = (
        f"⚒ <b>БИРЖА ТРУДА</b>\n\n"
        f"{job_name} — ты {job_desc}!\n\n"
        f"💰 Заработано: <b>+{fmt(money)}₽</b>"
    )
    if bonus:
        text += f"\n🎉 Бонус уровня: <b>+{fmt(bonus)}₽</b>"
    text += (
        f"\n\n📊 Опыт: {new_exp}/100 | Уровень: {new_lvl}\n"
        f"⏰ Следующая работа через <b>1 час</b>"
    )

    await message.answer(text, parse_mode="HTML")


def _update_quest_progress(cur: sqlite3.Cursor, db: sqlite3.Connection,
                            user_id: int, quest_type: str, delta: float) -> None:
    """Обновляет прогресс дневных квестов нужного типа."""
    from config import Quests
    from utils.helpers import safe_json_loads, safe_json_dumps

    row = cur.execute("SELECT daily_quests FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return
    quests = safe_json_loads(row[0], {})
    for qid, q in Quests.DAILY_QUESTS.items():
        if q['type'] == quest_type:
            key = str(qid)
            quests[key] = round(quests.get(key, 0) + delta, 6)
    cur.execute("UPDATE users SET daily_quests=? WHERE id=?", (safe_json_dumps(quests), user_id))
    db.commit()


# ──────────────────────────────────────────────────────────
#  КАЗИНО
# ──────────────────────────────────────────────────────────

SLOTS = ["🍎", "🍋", "💎", "🍒", "🔔", "⭐️", "🎯", "🍀"]


def _casino_keyboard(last_data: str | None = None) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🔸 1 000₽",   callback_data="bet_1000"),
         InlineKeyboardButton(text="🔸 5 000₽",   callback_data="bet_5000")],
        [InlineKeyboardButton(text="🔸 10 000₽",  callback_data="bet_10000"),
         InlineKeyboardButton(text="🔸 50 000₽",  callback_data="bet_50000")],
        [InlineKeyboardButton(text="🔥 ВСЁ НА ЗЕРО", callback_data="bet_all")],
        [InlineKeyboardButton(text="📊 Статистика",   callback_data="casino_stats")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="casino_main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(F.text == "🎰 Казино")
@require_registered
async def casino_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    uid     = message.from_user.id
    balance = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    text    = (
        f"🎰 <b>КАЗИНО «УДАЧА»</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Твой баланс: <b>{fmt(balance)}₽</b>\n\n"
        f"Сделай ставку и испытай удачу!\n\n"
        f"🎰 Три одинаковых — джекпот!\n"
        f"💎 Три бриллианта — СУПЕР ДЖЕКПОТ (×10)!\n"
        f"🔸 Два одинаковых — ×1.5"
    )
    await message.answer(text, reply_markup=_casino_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("bet_"))
@require_registered_cb
async def casino_play(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid      = callback.from_user.id
    balance  = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    bet_part = callback.data.split("_")[1]

    if bet_part == "all":
        amount = balance
    else:
        try:
            amount = int(bet_part)
        except ValueError:
            await callback.answer("❌ Неверная ставка", show_alert=True)
            return

    if amount < CASINO_MIN_BET:
        await callback.answer(f"❌ Минимальная ставка: {fmt(CASINO_MIN_BET)}₽", show_alert=True)
        return
    if amount > balance:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    # Списываем ставку
    cur.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, uid))
    db.commit()

    res = [random.choice(SLOTS) for _ in range(3)]
    res_str = " | ".join(res)

    if res[0] == res[1] == res[2]:
        if res[0] == "💎":
            win, msg_extra = amount * 10, "💎 <b>СУПЕР ДЖЕКПОТ!</b>"
        else:
            win, msg_extra = amount * 3, "🎊 <b>ДЖЕКПОТ!</b>"
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        win, msg_extra = int(amount * 1.5), "💰 <b>Неплохо!</b>"
    else:
        win, msg_extra = 0, "💀 Увы, не повезло..."

    if win:
        cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (win, uid))
        add_transaction(db, cur, uid, win,    'casino_win',  f'Выигрыш в казино')
        result_line = f"{msg_extra} Выигрыш: <b>+{fmt(win)}₽</b>"
    else:
        add_transaction(db, cur, uid, -amount, 'casino_loss', f'Проигрыш в казино')
        result_line = msg_extra

    db.commit()
    _update_quest_progress(cur, db, uid, "casino", 1)

    new_bal = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]

    text = (
        f"🎰 <b>{res_str}</b>\n\n"
        f"{result_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Баланс: <b>{fmt(new_bal)}₽</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сыграть снова", callback_data=callback.data)],
        [InlineKeyboardButton(text="🔙 В казино",       callback_data="back_to_casino")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "casino_stats")
@require_registered_cb
async def casino_stats(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid  = callback.from_user.id
    wins = cur.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='casino_win'", (uid,)
    ).fetchone()[0]
    losses = cur.execute(
        "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='casino_loss'", (uid,)
    ).fetchone()[0]
    total_bets = cur.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND type IN ('casino_win','casino_loss')", (uid,)
    ).fetchone()[0]

    profit = wins + losses
    text = (
        f"📊 <b>СТАТИСТИКА КАЗИНО</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎰 Всего ставок: {total_bets}\n"
        f"✅ Выиграно: {fmt(wins)}₽\n"
        f"❌ Проиграно: {fmt(abs(losses))}₽\n"
        f"📈 Итог: {fmt(profit)}₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В казино", callback_data="back_to_casino")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "back_to_casino")
@require_registered_cb
async def back_to_casino(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid     = callback.from_user.id
    balance = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    text    = (
        f"🎰 <b>КАЗИНО «УДАЧА»</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Твой баланс: <b>{fmt(balance)}₽</b>\n\n"
        f"Сделай ставку!"
    )
    try:
        await callback.message.edit_text(text, reply_markup=_casino_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=_casino_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "casino_main_menu")
@require_registered_cb
async def casino_main_menu(callback: types.CallbackQuery, **_):
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
