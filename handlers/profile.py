# ============================================================
#  handlers/profile.py — профиль пользователя
# ============================================================

import time
import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import GangRanks, Quests, ADMIN_IDS
from utils.helpers import require_registered, require_registered_cb, safe_json_loads, fmt, ts_to_str

router = Router(name="profile")


def _build_profile_text(u: tuple, cur: sqlite3.Cursor, user_id: int) -> str:
    privacy     = safe_json_loads(u[24], {"show_balance": True, "show_level": True})
    bal_text    = f"{fmt(u[5])}₽" if privacy.get("show_balance", True) else "★★★★★★"
    lvl_text    = f"{u[3]} LVL"   if privacy.get("show_level",   True) else "★★★★"

    gang_info = ""
    if u[12] and u[12] > 0:
        gang = cur.execute("SELECT name, level FROM gangs WHERE gang_id=?", (u[12],)).fetchone()
        rank_name = GangRanks.RANKS.get(u[13] or 0, {}).get("name", "—")
        gang_info = (
            f"┣━━ <b>БАНДА</b> ━━━━━━━\n"
            f"┃ 🔫 {gang[0] if gang else '?'}\n"
            f"┃ 🎖 Ранг: {rank_name}\n"
            f"┃ 📊 Уровень банды: {gang[1] if gang else 0}\n"
        )

    mining_cards = safe_json_loads(u[16], [])
    cards_count  = sum(c.get('count', 0) for c in mining_cards)

    daily_q   = safe_json_loads(u[19], {})
    weekly_q  = safe_json_loads(u[20], {})
    done_d = sum(1 for qid, q in Quests.DAILY_QUESTS.items()
                 if daily_q.get(str(qid), 0) >= q['target'])
    done_w = sum(1 for qid, q in Quests.WEEKLY_QUESTS.items()
                 if weekly_q.get(str(qid), 0) >= q['target'])

    text = (
        f"📋 <b>КАРТОЧКА ПЕРСОНАЖА</b>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━\n"
        f"┃ 👤 <b>Ник:</b> <code>{u[1]}</code>\n"
        f"┃ 🆔 <b>ID:</b> <code>{u[0]}</code>\n"
        f"┃ ⚤ <b>Пол:</b> {u[2] or '—'}\n"
        f"┣━━ <b>СТАТИСТИКА</b> ━━━\n"
        f"┃ 📊 <b>Уровень:</b> {lvl_text}\n"
        f"┃ 📈 <b>Опыт:</b> {u[4]}/100 EXP\n"
        f"┣━━ <b>ЭКОНОМИКА</b> ━━━\n"
        f"┃ 💵 <b>Баланс:</b> {bal_text}\n"
        f"┃ ₿ <b>BTC:</b> {u[11] or 0:.6f}\n"
        f"┃ 💰 <b>Инвестировано:</b> {fmt(u[17] or 0)}₽\n"
        f"┃ 💸 <b>Заработано:</b> {fmt(u[18] or 0)}₽\n"
        f"┣━━ <b>МАЙНИНГ</b> ━━━━━\n"
        f"┃ ⚡️ <b>Мощность:</b> {u[15] or 0} MH/s\n"
        f"┃ 🖥 <b>Видеокарт:</b> {cards_count} шт.\n"
        f"┃ 🏠 <b>Гараж:</b> {'✅' if u[10] else '❌'}\n"
        f"┣━━ <b>КВЕСТЫ</b> ━━━━━━\n"
        f"┃ 📅 <b>Ежедневных:</b> {done_d}/{len(Quests.DAILY_QUESTS)}\n"
        f"┃ 📆 <b>Еженедельных:</b> {done_w}/{len(Quests.WEEKLY_QUESTS)}\n"
    )
    if gang_info:
        text += gang_info
    text += "┗━━━━━━━━━━━━━━━━━━━━━━"
    return text


@router.message(F.text == "👤 Мой Профиль")
@require_registered
async def profile(message: types.Message, cur: sqlite3.Cursor, **_):
    u = cur.execute("SELECT * FROM users WHERE id=?", (message.from_user.id,)).fetchone()
    if not u:
        await message.answer("❌ Профиль не найден! Введите /start")
        return

    text    = _build_profile_text(u, cur, message.from_user.id)
    is_admin = message.from_user.id in ADMIN_IDS

    buttons = []
    if is_admin:
        buttons.append([InlineKeyboardButton(text="📢 Рассылка",        callback_data="admin_broadcast")])
        buttons.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")])
    buttons += [
        [InlineKeyboardButton(text="📊 Подробная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton(text="🔄 Обновить",             callback_data="refresh_profile")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_profile")
@require_registered_cb
async def refresh_profile(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    u = cur.execute("SELECT * FROM users WHERE id=?", (callback.from_user.id,)).fetchone()
    if not u:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    text = _build_profile_text(u, cur, callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="HTML",
                                     reply_markup=callback.message.reply_markup)
    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "detailed_stats")
@require_registered_cb
async def detailed_stats(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid = callback.from_user.id
    u   = cur.execute("""
        SELECT nickname, level, exp, balance, btc_balance, mining_power, has_garage,
               total_invested, total_earned, last_work, last_top_reward,
               (SELECT COUNT(*) FROM users      WHERE referrer_id=?)  AS ref_cnt,
               (SELECT COUNT(*) FROM transactions WHERE user_id=?)    AS tx_cnt,
               (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? AND type='work') AS work_sum
        FROM users WHERE id=?
    """, (uid, uid, uid, uid)).fetchone()

    days   = max(1, (int(time.time()) - (u[9] or 0)) // 86_400) if u[9] else 1
    avg    = (u[13] or 0) // days

    text = (
        f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 {u[0]} · {u[1]} LVL ({u[2]}/100 EXP)\n"
        f"💵 Баланс: {fmt(u[3])}₽ | ₿ {u[4] or 0:.6f}\n\n"
        f"⚡️ <b>Майнинг:</b>\n"
        f"• Мощность: {u[5] or 0} MH/s | Гараж: {'✅' if u[6] else '❌'}\n"
        f"• Инвестиции: {fmt(u[7] or 0)}₽\n"
        f"• Заработано: {fmt(u[8] or 0)}₽\n\n"
        f"📈 <b>Активность:</b>\n"
        f"• Рефералов: {u[11] or 0} | Транзакций: {u[12] or 0}\n"
        f"• Заработано работой: {fmt(u[13] or 0)}₽\n"
        f"• Среднедневной доход: {fmt(avg)}₽\n\n"
        f"⏰ Последняя работа: {ts_to_str(u[9])}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="refresh_profile")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
