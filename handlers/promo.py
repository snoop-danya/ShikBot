# ============================================================
#  handlers/promo.py — промокоды и рефералы
# ============================================================

import time
import sqlite3

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_USERNAME
from utils.helpers import require_registered, require_registered_cb, add_transaction, fmt, ts_to_str

router = Router(name="promo")


class PromoState(StatesGroup):
    waiting_for_code = State()


# ──────────────────────────────────────────────────────────
#  Промокоды
# ──────────────────────────────────────────────────────────

@router.message(F.text == "🎁 Промокод")
@require_registered
async def promo_start(message: types.Message, state: FSMContext, cur: sqlite3.Cursor, **_):
    uid    = message.from_user.id
    used   = cur.execute("SELECT COUNT(*) FROM activated_promo WHERE user_id=?", (uid,)).fetchone()[0]
    await message.answer(
        f"🎟 <b>АКТИВАЦИЯ ПРОМОКОДА</b>\n\n"
        f"Активировано промокодов: {used}\n\n"
        f"Введите промокод (регистр важен):",
        parse_mode="HTML",
    )
    await state.set_state(PromoState.waiting_for_code)


@router.message(PromoState.waiting_for_code)
async def promo_apply(message: types.Message, state: FSMContext,
                      cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    await state.clear()
    code    = message.text.strip().upper() if message.text else ""
    uid     = message.from_user.id

    if not code:
        await message.answer("❌ Введите промокод!")
        return

    promo = cur.execute("SELECT reward, uses FROM promo WHERE code=?", (code,)).fetchone()
    if not promo:
        await message.answer("❌ <b>Промокод не найден!</b>", parse_mode="HTML")
        return

    if cur.execute("SELECT 1 FROM activated_promo WHERE user_id=? AND code=?", (uid, code)).fetchone():
        await message.answer("⚠️ <b>Вы уже активировали этот промокод!</b>", parse_mode="HTML")
        return

    if promo[1] <= 0:
        await message.answer("📉 <b>Лимит активаций исчерпан!</b>", parse_mode="HTML")
        return

    reward = promo[0]
    cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (reward, uid))
    cur.execute("UPDATE promo SET uses=uses-1 WHERE code=?", (code,))
    cur.execute("INSERT INTO activated_promo (user_id, code, activated_at) VALUES (?,?,?)",
                (uid, code, int(time.time())))
    add_transaction(db, cur, uid, reward, 'promo_code', f'Промокод {code}')

    await message.answer(
        f"🎊 <b>Промокод активирован!</b>\n"
        f"💰 Начислено: <b>+{fmt(reward)}₽</b>",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
#  Рефералы
# ──────────────────────────────────────────────────────────

@router.message(F.text == "🤝 Рефералы")
@require_registered
async def refs_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    import bot_instance as _bi
    uid  = message.from_user.id
    cnt  = cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]
    me   = await _bi.bot.get_me()
    link = f"https://t.me/{me.username}?start={uid}"

    text = (
        f"🤝 <b>ПАРТНЁРСКАЯ ПРОГРАММА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Приглашено: <b>{cnt}</b> чел.\n"
        f"💰 Бонус за реферала: <b>5 000₽</b>\n\n"
        f"🎁 <b>БОНУСЫ ЗА ДОСТИЖЕНИЯ:</b>\n"
        f"• 10 друзей → 50 000₽\n"
        f"• 50 друзей → 500 000₽\n"
        f"• 100 друзей → 1 000 000₽\n\n"
        f"📞 Для получения: {ADMIN_USERNAME}\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n<code>{link}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои рефералы",  callback_data="ref_list")],
        [InlineKeyboardButton(text="🎁 Проверить бонус", callback_data="check_ref_bonuses")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "ref_list")
@require_registered_cb
async def ref_list(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid  = callback.from_user.id
    refs = cur.execute(
        "SELECT nickname, level, balance, last_login FROM users WHERE referrer_id=? ORDER BY last_login DESC LIMIT 20",
        (uid,)
    ).fetchall()

    if not refs:
        text = "📋 <b>РЕФЕРАЛЫ</b>\n\nПока нет рефералов."
    else:
        text = "📋 <b>МОИ РЕФЕРАЛЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, r in enumerate(refs, 1):
            text += f"{i}. <b>{r[0]}</b> · LVL {r[1]} · {fmt(r[2])}₽ · {ts_to_str(r[3], '%d.%m')}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_refs")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "check_ref_bonuses")
@require_registered_cb
async def check_ref_bonuses(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid = callback.from_user.id
    cnt = cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]

    bonuses = []
    if cnt >= 10:  bonuses.append("• 10 друзей — 50 000₽ ✅")
    if cnt >= 50:  bonuses.append("• 50 друзей — 500 000₽ ✅")
    if cnt >= 100: bonuses.append("• 100 друзей — 1 000 000₽ ✅")

    text = (
        f"🎁 <b>ДОСТУПНЫЕ БОНУСЫ</b>\n\n"
        f"Рефералов: {cnt}\n\n"
        f"{chr(10).join(bonuses) if bonuses else '❌ Бонусов пока нет'}\n\n"
        f"📞 Для получения напишите {ADMIN_USERNAME}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_refs")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "back_to_refs")
@require_registered_cb
async def back_to_refs(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    await refs_menu(callback.message, cur=cur)
