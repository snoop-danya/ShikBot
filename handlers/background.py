# ============================================================
#  handlers/background.py — фоновые задачи
# ============================================================

import asyncio
import logging
import random
import time
import sqlite3
from datetime import datetime

from config import BUSINESS_INCOME, DAILY_BONUS_MIN, DAILY_BONUS_MAX

log = logging.getLogger(__name__)


async def hourly_income_loop(db: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """
    Каждый час:
    • Начисляет доход от бизнесов
    • Начисляет доход от территорий банде
    • Начисляет/продаёт намайненные BTC
    """
    while True:
        await asyncio.sleep(3600)
        try:
            now = int(time.time())

            # Доход бизнесов
            for biz_type, income in BUSINESS_INCOME.items():
                cur.execute(
                    "UPDATE users SET balance=balance+? WHERE business=?",
                    (income, biz_type),
                )

            # Доход территорий → общак банд
            territories = cur.execute(
                "SELECT owner_gang_id, income FROM territories WHERE owner_gang_id!=0"
            ).fetchall()
            for owner_id, income in territories:
                cur.execute(
                    "UPDATE gangs SET balance=balance+? WHERE gang_id=?",
                    (income, owner_id),
                )

            # Майнинг
            btc_price = cur.execute("SELECT price FROM crypto WHERE name='BTC'").fetchone()
            if btc_price:
                btc_price = btc_price[0]
                miners = cur.execute(
                    "SELECT id, mining_power, btc_balance, auto_sell_btc FROM users WHERE mining_power>0"
                ).fetchall()
                for user_id, power, btc_bal, auto_sell in miners:
                    hourly_btc = (power * 24) / 1_000_000
                    if auto_sell:
                        rub = int(hourly_btc * btc_price)
                        cur.execute(
                            "UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE id=?",
                            (rub, rub, user_id),
                        )
                        cur.execute(
                            "INSERT INTO transactions (user_id,amount,type,timestamp,description) VALUES (?,?,?,?,?)",
                            (user_id, rub, 'mining_reward', now, f'Авто-продажа {hourly_btc:.6f} BTC'),
                        )
                    else:
                        new_btc = (btc_bal or 0) + hourly_btc
                        cur.execute(
                            "UPDATE users SET btc_balance=? WHERE id=?",
                            (new_btc, user_id),
                        )

            db.commit()
            log.info("✅ Часовое начисление %s", datetime.now().strftime('%H:%M:%S'))

        except Exception as exc:
            log.error("❌ Ошибка в hourly_income_loop: %s", exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass


async def daily_reset_loop(db: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """
    Каждые 24 часа:
    • Сбрасывает ежедневные квесты (через SQL)
    • Начисляет небольшой случайный бонус активным пользователям
    """
    while True:
        await asyncio.sleep(86_400)
        try:
            now = int(time.time())

            # Сброс квестов
            cur.execute(
                "UPDATE users SET daily_quests='{}', last_daily_reset=? "
                "WHERE last_daily_reset < ? - 86400",
                (now, now),
            )

            # Бонус активным
            active_users = cur.execute(
                "SELECT id FROM users WHERE last_login > ?",
                (now - 86_400,),
            ).fetchall()

            for (uid,) in active_users:
                if random.random() < 0.4:       # 40% шанс
                    bonus = random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)
                    cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (bonus, uid))

            db.commit()
            log.info("✅ Ежедневный сброс %s", datetime.now().strftime('%H:%M:%S'))

        except Exception as exc:
            log.error("❌ Ошибка в daily_reset_loop: %s", exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass


async def crypto_price_loop(db: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """
    Каждые 6 часов обновляет цены криптовалют (±5% рандом).
    """
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            now    = int(time.time())
            coins  = cur.execute("SELECT name, price FROM crypto").fetchall()
            for name, price in coins:
                change = random.uniform(-0.05, 0.05)
                new_p  = max(1, int(price * (1 + change)))
                cur.execute(
                    "UPDATE crypto SET price=?, change_24h=?, last_update=? WHERE name=?",
                    (new_p, round(change * 100, 2), now, name),
                )
            db.commit()
            log.info("📈 Цены крипты обновлены")
        except Exception as exc:
            log.error("❌ Ошибка в crypto_price_loop: %s", exc, exc_info=True)
