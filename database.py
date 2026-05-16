# ============================================================
#  database.py — инициализация и миграции базы данных
# ============================================================

import sqlite3
import time
import logging

from config import DB_PATH

log = logging.getLogger(__name__)


def get_connection() -> tuple[sqlite3.Connection, sqlite3.Cursor]:
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")    # лучше параллелизм
    db.execute("PRAGMA foreign_keys=ON")
    cur = db.cursor()
    return db, cur


def _add_column(cur: sqlite3.Cursor, table: str, col: str, col_type: str) -> None:
    try:
        cur.execute(f"SELECT {col} FROM {table} LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            log.info("Добавлен столбец %s.%s", table, col)
        except Exception as exc:
            log.error("Ошибка добавления столбца %s.%s: %s", table, col, exc)


def init_db(db: sqlite3.Connection, cur: sqlite3.Cursor) -> None:
    """Создаёт таблицы и выполняет миграции."""

    # ── Основные таблицы ──────────────────────────────────
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY,
            nickname    TEXT    NOT NULL,
            gender      TEXT,
            level       INTEGER DEFAULT 1,
            exp         INTEGER DEFAULT 0,
            balance     INTEGER DEFAULT 500,
            referrer_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS promo (
            code        TEXT    PRIMARY KEY,
            reward      INTEGER NOT NULL,
            uses        INTEGER NOT NULL,
            created_at  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS crypto (
            name        TEXT    PRIMARY KEY,
            price       INTEGER NOT NULL,
            last_update INTEGER DEFAULT 0,
            change_24h  REAL    DEFAULT 0.0,
            volume      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS territories (
            territory_id    INTEGER PRIMARY KEY,
            owner_gang_id   INTEGER DEFAULT 0,
            defense         INTEGER DEFAULT 100,
            last_attack     INTEGER DEFAULT 0,
            income          INTEGER DEFAULT 5000,
            name            TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS activated_promo (
            user_id         INTEGER NOT NULL,
            code            TEXT    NOT NULL,
            activated_at    INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, code)
        );

        CREATE TABLE IF NOT EXISTS business (
            user_id     INTEGER PRIMARY KEY,
            type        TEXT,
            income      INTEGER,
            last_collect INTEGER
        );

        CREATE TABLE IF NOT EXISTS gangs (
            gang_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            owner_id        INTEGER NOT NULL,
            balance         INTEGER DEFAULT 0,
            members_count   INTEGER DEFAULT 1,
            materials       INTEGER DEFAULT 0,
            description     TEXT    DEFAULT '',
            created_at      INTEGER DEFAULT 0,
            level           INTEGER DEFAULT 1,
            exp             INTEGER DEFAULT 0,
            max_members     INTEGER DEFAULT 20,
            logo            TEXT    DEFAULT '',
            color           TEXT    DEFAULT '#000000',
            reputation      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS gang_requests (
            user_id     INTEGER NOT NULL,
            gang_id     INTEGER NOT NULL,
            timestamp   INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, gang_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            rules   TEXT
        );

        CREATE TABLE IF NOT EXISTS gang_logs (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            gang_id     INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            action      TEXT    NOT NULL,
            timestamp   INTEGER DEFAULT 0,
            details     TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS items (
            item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            type        TEXT,
            price       INTEGER,
            power       INTEGER DEFAULT 0,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS user_items (
            user_id     INTEGER NOT NULL,
            item_id     INTEGER NOT NULL,
            count       INTEGER DEFAULT 1,
            equipped    INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            tx_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      INTEGER NOT NULL,
            type        TEXT    NOT NULL,
            timestamp   INTEGER DEFAULT 0,
            description TEXT
        );
    """)

    # ── Миграции users ─────────────────────────────────────
    user_columns = [
        ('last_work',        'INTEGER DEFAULT 0'),
        ('last_top_reward',  'INTEGER DEFAULT 0'),
        ('business',         'INTEGER DEFAULT 0'),
        ('has_garage',       'INTEGER DEFAULT 0'),
        ('btc_balance',      'REAL    DEFAULT 0.0'),
        ('gang_id',          'INTEGER DEFAULT 0'),
        ('gang_rank',        'INTEGER DEFAULT 0'),
        ('warn_count',       'INTEGER DEFAULT 0'),
        ('mining_power',     'INTEGER DEFAULT 0'),
        ('mining_cards',     "TEXT    DEFAULT '[]'"),
        ('total_invested',   'INTEGER DEFAULT 0'),
        ('total_earned',     'INTEGER DEFAULT 0'),
        ('daily_quests',     "TEXT    DEFAULT '{}'"),
        ('weekly_quests',    "TEXT    DEFAULT '{}'"),
        ('last_daily_reset', 'INTEGER DEFAULT 0'),
        ('last_weekly_reset','INTEGER DEFAULT 0'),
        ('notifications',    'INTEGER DEFAULT 1'),
        ('privacy_settings', "TEXT    DEFAULT '{\"show_balance\":true,\"show_level\":true}'"),
        ('theme',            'INTEGER DEFAULT 0'),
        ('auto_sell_btc',    'INTEGER DEFAULT 0'),
        ('cards_level',      'INTEGER DEFAULT 0'),
        ('gang_exp',         'INTEGER DEFAULT 0'),
        ('last_login',       'INTEGER DEFAULT 0'),
        ('playtime',         'INTEGER DEFAULT 0'),
        ('achievements',     "TEXT    DEFAULT '[]'"),
        ('language',         "TEXT    DEFAULT 'ru'"),
    ]
    for col, ctype in user_columns:
        _add_column(cur, 'users', col, ctype)

    # ── Индексы для производительности ────────────────────
    cur.executescript("""
        CREATE INDEX IF NOT EXISTS idx_users_balance      ON users(balance DESC);
        CREATE INDEX IF NOT EXISTS idx_users_level        ON users(level DESC, exp DESC);
        CREATE INDEX IF NOT EXISTS idx_users_mining       ON users(mining_power DESC);
        CREATE INDEX IF NOT EXISTS idx_users_referrer     ON users(referrer_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_user  ON transactions(user_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_gang_logs_gang     ON gang_logs(gang_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_territories_owner  ON territories(owner_gang_id);
    """)

    # ── Начальные данные ───────────────────────────────────
    now = int(time.time())

    for i in range(1, 51):
        cur.execute(
            "INSERT OR IGNORE INTO territories (territory_id, owner_gang_id, name) VALUES (?, 0, ?)",
            (i, f"Район #{i}"),
        )

    cur.executemany(
        "INSERT OR IGNORE INTO crypto (name, price, last_update) VALUES (?, ?, ?)",
        [('BTC', 5_000_000, now), ('ETH', 350_000, now), ('DOGE', 50, now)],
    )

    cur.executemany(
        "INSERT OR IGNORE INTO promo (code, reward, uses, created_at) VALUES (?, ?, ?, ?)",
        [('SHAKAL', 25_000, 100, now), ('SORRY', 1_000_000, 50, now), ('WELCOME', 5_000, 1000, now)],
    )

    # ── Починить битые JSON-поля ───────────────────────────
    cur.executescript("""
        UPDATE users SET privacy_settings = '{"show_balance":true,"show_level":true}'
            WHERE privacy_settings IS NULL OR privacy_settings = '' OR privacy_settings = 'null';
        UPDATE users SET mining_cards = '[]'
            WHERE mining_cards IS NULL OR mining_cards = '' OR mining_cards = 'null';
        UPDATE users SET daily_quests = '{}'
            WHERE daily_quests IS NULL OR daily_quests = '' OR daily_quests = 'null';
        UPDATE users SET weekly_quests = '{}'
            WHERE weekly_quests IS NULL OR weekly_quests = '' OR weekly_quests = 'null';
        UPDATE users SET achievements = '[]'
            WHERE achievements IS NULL OR achievements = '' OR achievements = 'null';
    """)

    db.commit()
    log.info("База данных инициализирована.")
