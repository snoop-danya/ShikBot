# ============================================================
#  handlers/admin.py — административные команды
# ============================================================

import time
import sqlite3
import logging

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS
from utils.helpers import admin_only, admin_only_cb, fmt

log    = logging.getLogger(__name__)
router = Router(name="admin")


class AdminStates(StatesGroup):
    broadcast_text  = State()
    promo_code      = State()
    promo_reward    = State()
    promo_uses      = State()
    give_uid        = State()
    give_amount     = State()


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ──────────────────────────────────────────────────────────
#  /admin — панель
# ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def admin_panel(message: types.Message, cur: sqlite3.Cursor, **_):
    users_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    gangs_count = cur.execute("SELECT COUNT(*) FROM gangs").fetchone()[0]
    total_bal   = cur.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0]

    text = (
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Игроков: {users_count}\n"
        f"🔫 Банд: {gangs_count}\n"
        f"💰 Всего денег: {fmt(total_bal)}₽\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка",        callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="💸 Выдать деньги",   callback_data="admin_give_money")],
        [InlineKeyboardButton(text="📊 Статистика",       callback_data="admin_stats")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ──────────────────────────────────────────────────────────
#  Рассылка
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_broadcast")
@admin_only_cb
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext, **_):
    await callback.message.answer(
        "📢 <b>Рассылка</b>\n\nВведите текст (поддерживается HTML):",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.broadcast_text)


@router.message(AdminStates.broadcast_text)
async def admin_broadcast_send(
    message: types.Message, state: FSMContext,
    cur: sqlite3.Cursor, **_
):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    import bot_instance as _bi
    users  = cur.execute("SELECT id FROM users").fetchall()
    sent, failed = 0, 0

    prog = await message.answer(f"📤 Рассылка... 0/{len(users)}")
    for i, (uid,) in enumerate(users, 1):
        try:
            await _bi.bot.send_message(uid, message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            try:
                await prog.edit_text(f"📤 Рассылка... {i}/{len(users)}")
            except Exception:
                pass

    await prog.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n"
        f"• Успешно: {sent}\n"
        f"• Ошибок: {failed}",
        parse_mode="HTML",
    )
    await state.clear()


# ──────────────────────────────────────────────────────────
#  Промокод
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create_promo")
@admin_only_cb
async def admin_promo_start(callback: types.CallbackQuery, state: FSMContext, **_):
    await callback.message.answer("🎫 Введите код промокода (только буквы/цифры):")
    await state.set_state(AdminStates.promo_code)


@router.message(AdminStates.promo_code)
async def admin_promo_code(message: types.Message, state: FSMContext,
                            cur: sqlite3.Cursor, **_):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    code = message.text.strip().upper() if message.text else ""
    if not code.isalnum():
        await message.answer("❌ Только буквы и цифры!")
        return
    if cur.execute("SELECT 1 FROM promo WHERE code=?", (code,)).fetchone():
        await message.answer("❌ Такой промокод уже есть!")
        return
    await state.update_data(promo_code=code)
    await message.answer(f"✅ Код: <code>{code}</code>\n\nВведите награду (руб.):", parse_mode="HTML")
    await state.set_state(AdminStates.promo_reward)


@router.message(AdminStates.promo_reward)
async def admin_promo_reward(message: types.Message, state: FSMContext, **_):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        reward = int(message.text.strip())
        if reward <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите положительное число!")
        return
    await state.update_data(promo_reward=reward)
    await message.answer("Введите количество использований:")
    await state.set_state(AdminStates.promo_uses)


@router.message(AdminStates.promo_uses)
async def admin_promo_uses(message: types.Message, state: FSMContext,
                            cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        uses = int(message.text.strip())
        if uses <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введите положительное число!")
        return

    data   = await state.get_data()
    code   = data['promo_code']
    reward = data['promo_reward']

    cur.execute("INSERT INTO promo (code, reward, uses, created_at) VALUES (?,?,?,?)",
                (code, reward, uses, int(time.time())))
    db.commit()
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n"
        f"🎫 Код: <code>{code}</code>\n"
        f"💰 Награда: {fmt(reward)}₽\n"
        f"👥 Использований: {uses}",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
#  Выдать деньги игроку
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_give_money")
@admin_only_cb
async def admin_give_start(callback: types.CallbackQuery, state: FSMContext, **_):
    await callback.message.answer("💸 Введите Telegram ID игрока:")
    await state.set_state(AdminStates.give_uid)


@router.message(AdminStates.give_uid)
async def admin_give_uid(message: types.Message, state: FSMContext, cur: sqlite3.Cursor, **_):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        target = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("❌ Введите числовой ID!")
        return
    if not cur.execute("SELECT 1 FROM users WHERE id=?", (target,)).fetchone():
        await message.answer("❌ Игрок не найден!")
        return
    await state.update_data(give_uid=target)
    await message.answer("💰 Введите сумму:")
    await state.set_state(AdminStates.give_amount)


@router.message(AdminStates.give_amount)
async def admin_give_amount(message: types.Message, state: FSMContext,
                             cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        amount = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число!")
        return

    data   = await state.get_data()
    target = data['give_uid']
    cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, target))
    nick = cur.execute("SELECT nickname FROM users WHERE id=?", (target,)).fetchone()[0]
    from utils.helpers import add_transaction
    add_transaction(db, cur, target, amount, 'admin_gift', f'Подарок от администратора')
    await state.clear()

    import bot_instance as _bi
    try:
        await _bi.bot.send_message(target,
            f"🎁 <b>Администратор начислил вам {fmt(amount)}₽!</b>",
            parse_mode="HTML")
    except Exception:
        pass

    await message.answer(f"✅ Игроку {nick} ({target}) выдано {fmt(amount)}₽")


# ──────────────────────────────────────────────────────────
#  Статистика
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
@admin_only_cb
async def admin_stats(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    users    = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active24 = cur.execute("SELECT COUNT(*) FROM users WHERE last_login > ?",
                           (int(time.time()) - 86_400,)).fetchone()[0]
    gangs    = cur.execute("SELECT COUNT(*) FROM gangs").fetchone()[0]
    tx_today = cur.execute("SELECT COUNT(*) FROM transactions WHERE timestamp > ?",
                           (int(time.time()) - 86_400,)).fetchone()[0]
    total_rub = cur.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0]

    text = (
        f"📊 <b>СТАТИСТИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Всего игроков: {users}\n"
        f"🟢 Активных (24ч): {active24}\n"
        f"🔫 Банд: {gangs}\n"
        f"💳 Транзакций сегодня: {tx_today}\n"
        f"💰 Всего денег в игре: {fmt(total_rub)}₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Панель", callback_data="admin_back")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_back")
@admin_only_cb
async def admin_back(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    await admin_panel(callback.message, cur=cur)
