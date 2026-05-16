# ============================================================
#  handlers/settings.py — настройки пользователя
# ============================================================

import sqlite3

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_USERNAME
from utils.helpers import (
    require_registered, require_registered_cb,
    safe_json_loads, safe_json_dumps,
    validate_nickname, fmt, ts_to_str,
)
from utils.keyboards import main_menu

router = Router(name="settings")


class SettingsStates(StatesGroup):
    waiting_for_nickname = State()


# ──────────────────────────────────────────────────────────
#  Главное меню настроек
# ──────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройки")
@require_registered
async def settings_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    uid  = message.from_user.id
    u    = cur.execute("SELECT nickname, theme, notifications FROM users WHERE id=?", (uid,)).fetchone()

    text = (
        f"⚙️ <b>НАСТРОЙКИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Никнейм: <code>{u[0]}</code>\n"
        f"🔔 Уведомления: {'✅' if u[2] else '❌'}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Сменить ник",      callback_data="change_nickname_start")],
        [InlineKeyboardButton(text="🔒 Приватность",      callback_data="privacy_settings_menu")],
        [InlineKeyboardButton(text="🔔 Уведомления",      callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="📊 Статистика аккаунта", callback_data="account_stats")],
        [InlineKeyboardButton(text="📜 История транзакций",  callback_data="transaction_history")],
        [InlineKeyboardButton(text="ℹ️ О боте",           callback_data="about_bot")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "back_to_settings")
@require_registered_cb
async def back_to_settings(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    await settings_menu(callback.message, cur=cur)


# ──────────────────────────────────────────────────────────
#  Смена ника
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "change_nickname_start")
@require_registered_cb
async def change_nick_start(callback: types.CallbackQuery, state: FSMContext, cur: sqlite3.Cursor, **_):
    nick = cur.execute("SELECT nickname FROM users WHERE id=?", (callback.from_user.id,)).fetchone()[0]
    await callback.message.answer(
        f"✏️ <b>Смена никнейма</b>\n\n"
        f"Текущий: <code>{nick}</code>\n\n"
        f"Введите новый ник (3–15 символов):",
        parse_mode="HTML",
    )
    await state.set_state(SettingsStates.waiting_for_nickname)


@router.message(SettingsStates.waiting_for_nickname)
async def process_nick_change(message: types.Message, state: FSMContext,
                               cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid     = message.from_user.id
    new_nick = message.text.strip() if message.text else ""
    err      = validate_nickname(new_nick)
    if err:
        await message.answer(f"❌ {err}")
        return
    if cur.execute("SELECT 1 FROM users WHERE nickname=? AND id!=?", (new_nick, uid)).fetchone():
        await message.answer("❌ Этот никнейм занят!")
        return

    old = cur.execute("SELECT nickname FROM users WHERE id=?", (uid,)).fetchone()[0]
    cur.execute("UPDATE users SET nickname=? WHERE id=?", (new_nick, uid))
    db.commit()
    await state.clear()
    await message.answer(
        f"✅ <b>Никнейм изменён!</b>\n"
        f"<code>{old}</code> → <code>{new_nick}</code>",
        reply_markup=main_menu(), parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
#  Приватность
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "privacy_settings_menu")
@require_registered_cb
async def privacy_menu(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid  = callback.from_user.id
    raw  = cur.execute("SELECT privacy_settings FROM users WHERE id=?", (uid,)).fetchone()[0]
    priv = safe_json_loads(raw, {"show_balance": True, "show_level": True})

    sb = "✅" if priv.get("show_balance", True) else "❌"
    sl = "✅" if priv.get("show_level",   True) else "❌"

    text = (
        f"🔒 <b>НАСТРОЙКИ ПРИВАТНОСТИ</b>\n\n"
        f"{sb} Показывать баланс\n"
        f"{sl} Показывать уровень"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'Скрыть' if priv.get('show_balance',True) else 'Показывать'} баланс",
                              callback_data="toggle_show_balance")],
        [InlineKeyboardButton(text=f"{'Скрыть' if priv.get('show_level',True) else 'Показывать'} уровень",
                              callback_data="toggle_show_level")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


def _toggle_privacy(cur: sqlite3.Cursor, db: sqlite3.Connection, uid: int, field: str) -> bool:
    raw  = cur.execute("SELECT privacy_settings FROM users WHERE id=?", (uid,)).fetchone()[0]
    priv = safe_json_loads(raw, {"show_balance": True, "show_level": True})
    priv[field] = not priv.get(field, True)
    cur.execute("UPDATE users SET privacy_settings=? WHERE id=?", (safe_json_dumps(priv), uid))
    db.commit()
    return priv[field]


@router.callback_query(F.data == "toggle_show_balance")
@require_registered_cb
async def toggle_balance(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    now_visible = _toggle_privacy(cur, db, callback.from_user.id, "show_balance")
    await callback.answer(f"Баланс теперь {'виден' if now_visible else 'скрыт'}", show_alert=True)
    await privacy_menu(callback, cur=cur, db=db)


@router.callback_query(F.data == "toggle_show_level")
@require_registered_cb
async def toggle_level(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    now_visible = _toggle_privacy(cur, db, callback.from_user.id, "show_level")
    await callback.answer(f"Уровень теперь {'виден' if now_visible else 'скрыт'}", show_alert=True)
    await privacy_menu(callback, cur=cur, db=db)


# ──────────────────────────────────────────────────────────
#  Уведомления
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "toggle_notifications")
@require_registered_cb
async def toggle_notifs(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid    = callback.from_user.id
    status = cur.execute("SELECT notifications FROM users WHERE id=?", (uid,)).fetchone()[0]
    new    = 0 if status else 1
    cur.execute("UPDATE users SET notifications=? WHERE id=?", (new, uid))
    db.commit()
    await callback.answer(f"🔔 Уведомления {'включены' if new else 'отключены'}", show_alert=True)
    await settings_menu(callback.message, cur=cur)


# ──────────────────────────────────────────────────────────
#  Статистика аккаунта
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "account_stats")
@require_registered_cb
async def account_stats(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    import time
    uid = callback.from_user.id
    u   = cur.execute("""
        SELECT nickname, level, exp, balance, btc_balance, mining_power, has_garage,
               total_invested, total_earned, last_work, last_login,
               (SELECT COUNT(*) FROM users WHERE referrer_id=?)          AS ref_cnt,
               (SELECT COUNT(*) FROM activated_promo WHERE user_id=?)    AS promo_cnt,
               (SELECT COUNT(*) FROM transactions WHERE user_id=?)       AS tx_cnt
        FROM users WHERE id=?
    """, (uid, uid, uid, uid)).fetchone()

    days = max(1, (int(time.time()) - (u[10] or 0)) // 86_400) if u[10] else 1

    text = (
        f"📊 <b>СТАТИСТИКА АККАУНТА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {u[0]} · {u[1]} LVL ({u[2]}/100 EXP)\n"
        f"💵 {fmt(u[3])}₽ | ₿ {u[4] or 0:.6f}\n\n"
        f"⚡️ Мощность: {u[5] or 0} MH/s | Гараж: {'✅' if u[6] else '❌'}\n"
        f"💰 Инвестиции: {fmt(u[7] or 0)}₽\n"
        f"💸 Заработано: {fmt(u[8] or 0)}₽\n\n"
        f"👥 Рефералов: {u[11] or 0}\n"
        f"🎫 Промокодов: {u[12] or 0}\n"
        f"💳 Транзакций: {u[13] or 0}\n"
        f"📅 В игре: {days} дней\n\n"
        f"⏰ Посл. работа: {ts_to_str(u[9])}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ──────────────────────────────────────────────────────────
#  История транзакций
# ──────────────────────────────────────────────────────────

TX_NAMES = {
    'work': '⚒ Работа', 'casino_win': '🎰 Выигрыш', 'casino_loss': '🎰 Проигрыш',
    'btc_sell': '₿ Продажа BTC', 'mining_investment': '⚡️ Инвестиция', 'garage_purchase': '🏠 Гараж',
    'gang_deposit': '💵 Вклад банде', 'gang_withdraw': '💸 Снятие банды', 'quest_reward': '🎁 Квест',
    'promo_code': '🎫 Промокод', 'level_up': '📊 Уровень', 'admin_gift': '🎁 Подарок',
    'top_reward': '🏆 Топ', 'mining_reward': '⚡️ Майнинг',
}


@router.callback_query(F.data == "transaction_history")
@require_registered_cb
async def tx_history(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid = callback.from_user.id
    txs = cur.execute("""
        SELECT amount, type, timestamp, description FROM transactions
        WHERE user_id=? ORDER BY timestamp DESC LIMIT 20
    """, (uid,)).fetchall()

    if not txs:
        text = "📜 <b>История транзакций</b>\n\nПока пусто."
    else:
        text = "📜 <b>ИСТОРИЯ ТРАНЗАКЦИЙ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for tx in txs:
            amt   = tx[0]
            name  = TX_NAMES.get(tx[1], tx[1])
            dt    = ts_to_str(tx[2], '%d.%m %H:%M')
            sign  = "+" if amt >= 0 else ""
            text += f"{name} · <b>{sign}{fmt(amt)}₽</b> · <i>{dt}</i>\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ──────────────────────────────────────────────────────────
#  О боте
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "about_bot")
@require_registered_cb
async def about_bot(callback: types.CallbackQuery, **_):
    text = (
        "ℹ️ <b>О БОТЕ ШАКАЛ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏙 Экономическая игра с:\n"
        "• ⚒ Работой и заработком\n"
        "• 🎰 Казино\n"
        "• ⚡️ Майнингом криптовалюты\n"
        "• 🔫 Бандами и территориями\n"
        "• 📜 Квестами\n\n"
        f"📞 Поддержка: {ADMIN_USERNAME}\n\n"
        "Версия: 2.0 (рефакторинг)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Написать поддержке",
                              url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
