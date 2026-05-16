# ============================================================
#  handlers/mining.py — майнинг
# ============================================================

import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import MiningCards, GARAGE_PRICE
from utils.helpers import (
    require_registered, require_registered_cb,
    safe_json_loads, safe_json_dumps,
    calculate_mining_income, add_transaction, fmt,
)

router = Router(name="mining")


def _mining_text(uid: int, cur: sqlite3.Cursor) -> str:
    u = cur.execute(
        "SELECT balance, has_garage, btc_balance, mining_power, auto_sell_btc FROM users WHERE id=?", (uid,)
    ).fetchone()
    btc_p = cur.execute("SELECT price FROM crypto WHERE name='BTC'").fetchone()[0]

    income    = calculate_mining_income(u[3] or 0, btc_p)
    auto_mode = "🤖 Авто-продажа: ВКЛ" if u[4] else "🔒 Авто-продажа: ВЫКЛ"

    return (
        f"⚡️ <b>МАЙНИНГ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Баланс: <b>{fmt(u[0])}₽</b>\n"
        f"₿ BTC: <b>{u[2] or 0:.6f}</b>\n"
        f"⚡️ Мощность: <b>{u[3] or 0} MH/s</b>\n"
        f"🏠 Гараж: {'✅ Есть' if u[1] else '❌ Нет'}\n"
        f"{auto_mode}\n\n"
        f"📅 <b>Доходность (≈):</b>\n"
        f"• В час: {fmt(income['hourly_rub'])}₽\n"
        f"• В день: {fmt(income['daily_rub'])}₽\n"
        f"• В месяц: {fmt(income['monthly_rub'])}₽"
    )


def _mining_kb(has_garage: bool, has_btc: bool) -> InlineKeyboardMarkup:
    kb = []
    if not has_garage:
        kb.append([InlineKeyboardButton(text=f"🏠 Купить гараж ({fmt(GARAGE_PRICE)}₽)", callback_data="buy_min_g")])
    else:
        kb.append([InlineKeyboardButton(text="🛒 Магазин карт",    callback_data="mining_shop"),
                   InlineKeyboardButton(text="🖥 Мои карты",       callback_data="my_mining_cards")])
    if has_btc:
        kb.append([InlineKeyboardButton(text="💱 Продать BTC",     callback_data="sell_min_btc")])
    kb.append([InlineKeyboardButton(text="🤖 Переключить авто-продажу", callback_data="toggle_auto_sell")])
    kb.append([InlineKeyboardButton(text="📊 Статистика майнинга",     callback_data="mining_stats")])
    kb.append([InlineKeyboardButton(text="🔄 Обновить",                callback_data="refresh_mining")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(F.text == "⚡️ Майнинг")
@require_registered
async def mining_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    uid = message.from_user.id
    u   = cur.execute("SELECT has_garage, btc_balance FROM users WHERE id=?", (uid,)).fetchone()
    text = _mining_text(uid, cur)
    kb   = _mining_kb(bool(u[0]), bool(u[1] and u[1] > 0))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_mining")
@require_registered_cb
async def refresh_mining(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid = callback.from_user.id
    u   = cur.execute("SELECT has_garage, btc_balance FROM users WHERE id=?", (uid,)).fetchone()
    text = _mining_text(uid, cur)
    kb   = _mining_kb(bool(u[0]), bool(u[1] and u[1] > 0))
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("✅ Обновлено")


# ── Гараж ────────────────────────────────────────────────

@router.callback_query(F.data == "buy_min_g")
@require_registered_cb
async def buy_garage(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = callback.from_user.id
    u   = cur.execute("SELECT balance, has_garage FROM users WHERE id=?", (uid,)).fetchone()
    if u[1]:
        await callback.answer("❌ У вас уже есть гараж!", show_alert=True)
        return
    if u[0] < GARAGE_PRICE:
        await callback.answer(f"❌ Нужно {fmt(GARAGE_PRICE)}₽, у вас {fmt(u[0])}₽", show_alert=True)
        return
    cur.execute("UPDATE users SET balance=balance-?, has_garage=1 WHERE id=?", (GARAGE_PRICE, uid))
    add_transaction(db, cur, uid, -GARAGE_PRICE, 'garage_purchase', 'Покупка гаража для майнинга')
    await callback.answer("✅ Гараж куплен! Теперь покупайте видеокарты.", show_alert=True)
    await refresh_mining(callback, cur=cur, db=db)


# ── Магазин карт ─────────────────────────────────────────

@router.callback_query(F.data == "mining_shop")
@require_registered_cb
async def mining_shop(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid     = callback.from_user.id
    balance = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    btc_p   = cur.execute("SELECT price FROM crypto WHERE name='BTC'").fetchone()[0]

    text = (
        f"🛒 <b>МАГАЗИН ВИДЕОКАРТ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Твой баланс: <b>{fmt(balance)}₽</b>\n\n"
    )
    kb_rows = []
    for card_id, cfg in MiningCards.CARDS_CONFIG.items():
        income  = calculate_mining_income(cfg['hashrate'], btc_p)
        text   += (
            f"{cfg['emoji']} <b>{cfg['name']}</b>\n"
            f"  Цена: {fmt(cfg['price'])}₽\n"
            f"  Хешрейт: {cfg['hashrate']} MH/s\n"
            f"  Доход/день: ≈{fmt(income['daily_rub'])}₽\n\n"
        )
        able    = balance >= cfg['price']
        kb_rows.append([InlineKeyboardButton(
            text=f"{'✅' if able else '❌'} Купить {cfg['name']}",
            callback_data=f"buy_card_{card_id}",
        )])

    kb_rows.append([InlineKeyboardButton(text="🔙 Назад в майнинг", callback_data="refresh_mining")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("buy_card_"))
@require_registered_cb
async def buy_card(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = callback.from_user.id
    try:
        card_level = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    cfg = MiningCards.CARDS_CONFIG.get(card_level)
    if not cfg:
        await callback.answer("❌ Карта не найдена", show_alert=True)
        return

    u = cur.execute("SELECT balance, has_garage, mining_cards FROM users WHERE id=?", (uid,)).fetchone()
    if not u[1]:
        await callback.answer("❌ Сначала купите гараж!", show_alert=True)
        return
    if u[0] < cfg['price']:
        await callback.answer(f"❌ Не хватает {fmt(cfg['price'] - u[0])}₽", show_alert=True)
        return

    cards = safe_json_loads(u[2], [])
    updated = False
    for card in cards:
        if card.get('level') == card_level:
            card['count'] = card.get('count', 0) + 1
            updated = True
            break
    if not updated:
        cards.append({"level": card_level, "count": 1})

    cur.execute(
        "UPDATE users SET balance=balance-?, total_invested=total_invested+?, "
        "mining_cards=?, mining_power=mining_power+? WHERE id=?",
        (cfg['price'], cfg['price'], safe_json_dumps(cards), cfg['hashrate'], uid),
    )
    add_transaction(db, cur, uid, -cfg['price'], 'mining_investment', f"Покупка {cfg['name']}")
    await callback.answer(f"✅ Куплена {cfg['name']} за {fmt(cfg['price'])}₽!", show_alert=True)
    await mining_shop(callback, cur=cur, db=db)


# ── Мои карты ────────────────────────────────────────────

@router.callback_query(F.data == "my_mining_cards")
@require_registered_cb
async def my_cards(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    u     = cur.execute("SELECT mining_cards, mining_power FROM users WHERE id=?", (uid,)).fetchone()
    cards = safe_json_loads(u[0], [])

    if not cards:
        text = "🖥 <b>МОИ ВИДЕОКАРТЫ</b>\n\nУ вас нет видеокарт. Купите в магазине!"
    else:
        text = "🖥 <b>МОИ ВИДЕОКАРТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for card in cards:
            cfg     = MiningCards.CARDS_CONFIG.get(card.get('level', 0), {})
            hs      = cfg.get('hashrate', 0) * card.get('count', 0)
            text   += f"{cfg.get('emoji','💻')} <b>{cfg.get('name','?')}</b> × {card.get('count',0)} — {hs} MH/s\n"
        text += f"\n📊 Итого: {u[1] or 0} MH/s"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить ещё", callback_data="mining_shop")],
        [InlineKeyboardButton(text="🔙 Майнинг",    callback_data="refresh_mining")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ── Продажа BTC ──────────────────────────────────────────

@router.callback_query(F.data == "sell_min_btc")
@require_registered_cb
async def sell_btc(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid   = callback.from_user.id
    u     = cur.execute("SELECT btc_balance FROM users WHERE id=?", (uid,)).fetchone()
    btc_p = cur.execute("SELECT price FROM crypto WHERE name='BTC'").fetchone()[0]

    if not u[0] or u[0] <= 0:
        await callback.answer("❌ У вас нет BTC для продажи!", show_alert=True)
        return

    rub = int(u[0] * btc_p)
    cur.execute(
        "UPDATE users SET balance=balance+?, btc_balance=0, total_earned=total_earned+? WHERE id=?",
        (rub, rub, uid),
    )
    add_transaction(db, cur, uid, rub, 'btc_sell', f'Продажа {u[0]:.6f} BTC')
    await callback.answer(f"✅ Продано {u[0]:.6f} BTC за {fmt(rub)}₽!", show_alert=True)
    await refresh_mining(callback, cur=cur, db=db)


# ── Авто-продажа ─────────────────────────────────────────

@router.callback_query(F.data == "toggle_auto_sell")
@require_registered_cb
async def toggle_auto_sell(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid    = callback.from_user.id
    status = cur.execute("SELECT auto_sell_btc FROM users WHERE id=?", (uid,)).fetchone()[0]
    new    = 0 if status else 1
    cur.execute("UPDATE users SET auto_sell_btc=? WHERE id=?", (new, uid))
    db.commit()
    await callback.answer(f"🤖 Авто-продажа {'ВКЛ' if new else 'ВЫКЛ'}!", show_alert=True)
    await refresh_mining(callback, cur=cur, db=db)


# ── Статистика майнинга ──────────────────────────────────

@router.callback_query(F.data == "mining_stats")
@require_registered_cb
async def mining_stats(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    u     = cur.execute(
        "SELECT mining_power, total_invested, total_earned, btc_balance FROM users WHERE id=?", (uid,)
    ).fetchone()
    btc_p = cur.execute("SELECT price FROM crypto WHERE name='BTC'").fetchone()[0]
    inc   = calculate_mining_income(u[0] or 0, btc_p)
    profit = (u[2] or 0) - (u[1] or 0)

    text = (
        f"📊 <b>СТАТИСТИКА МАЙНИНГА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡️ Мощность: {u[0] or 0} MH/s\n"
        f"💰 Инвестировано: {fmt(u[1] or 0)}₽\n"
        f"💸 Заработано: {fmt(u[2] or 0)}₽\n"
        f"📈 Прибыль: {fmt(profit)}₽\n"
        f"₿ BTC: {u[3] or 0:.6f}\n\n"
        f"📅 В час: {fmt(inc['hourly_rub'])}₽\n"
        f"📅 В день: {fmt(inc['daily_rub'])}₽\n"
        f"📅 В месяц: {fmt(inc['monthly_rub'])}₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Майнинг", callback_data="refresh_mining")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
