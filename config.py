# ============================================================
#  config.py — настройки и игровые конфиги
# ============================================================

API_TOKEN = '8992844797:AAFDOcOd56AF_3bHV8AQRHIm-ZFkyARlrX0'   # <-- замените
ADMIN_IDS: set[int] = {8070273258}          # <-- Telegram ID администраторов
ADMIN_USERNAME = "@Dexp0v"

DB_PATH = 'shakal_game.db'

# ──────────────────────────────────────────────────────────
#  Игровые параметры
# ──────────────────────────────────────────────────────────
WORK_COOLDOWN   = 3600          # секунды между работами
WORK_MIN        = 5_000
WORK_MAX        = 25_000
WORK_EXP        = 10

CASINO_MIN_BET  = 1_000
DAILY_BONUS_MIN = 1_000
DAILY_BONUS_MAX = 5_000

GARAGE_PRICE    = 100_000

STARTING_BALANCE = 500

GANG_CREATION_COST  = 50_000
GANG_DEFAULT_MAX_MEMBERS = 20

TOP_REWARD_COOLDOWN = 86_400    # 24 ч

# ──────────────────────────────────────────────────────────
#  Майнинг
# ──────────────────────────────────────────────────────────
class MiningCards:
    CARDS_CONFIG: dict[int, dict] = {
        1: {"name": "GTX 1060", "price": 250_000,   "hashrate": 0.5,  "power": 120,  "emoji": "🟢"},
        2: {"name": "RTX 3060", "price": 500_000,   "hashrate": 1.2,  "power": 170,  "emoji": "🔵"},
        3: {"name": "RTX 4090", "price": 1_500_000, "hashrate": 3.5,  "power": 450,  "emoji": "🟣"},
        4: {"name": "ASIC S19", "price": 5_000_000, "hashrate": 10.0, "power": 3250, "emoji": "🔥"},
    }

# ──────────────────────────────────────────────────────────
#  Банды
# ──────────────────────────────────────────────────────────
class GangRanks:
    RANKS: dict[int, dict] = {
        1: {"name": "🟢 Рекрут",      "permissions": ["chat", "deposit"]},
        2: {"name": "🔵 Солдат",      "permissions": ["chat", "deposit", "withdraw_small", "capture"]},
        3: {"name": "🟣 Заместитель", "permissions": ["chat", "deposit", "withdraw", "capture", "invite", "kick"]},
        4: {"name": "🔴 Лидер",       "permissions": ["chat", "deposit", "withdraw", "capture", "invite", "kick", "promote", "demote", "disband"]},
    }

# ──────────────────────────────────────────────────────────
#  Квесты
# ──────────────────────────────────────────────────────────
class Quests:
    DAILY_QUESTS: dict[int, dict] = {
        1: {"name": "⚒ Работай 3 раза",    "reward": 10_000, "target": 3,     "type": "work",     "emoji": "⚒"},
        2: {"name": "🎰 Сыграй в казино",   "reward":  5_000, "target": 1,     "type": "casino",   "emoji": "🎰"},
        3: {"name": "🤝 Пригласи друга",    "reward": 15_000, "target": 1,     "type": "referral", "emoji": "🤝"},
        4: {"name": "⚡️ Майни 0.001 BTC",  "reward": 20_000, "target": 0.001, "type": "mining",   "emoji": "⚡️"},
    }
    WEEKLY_QUESTS: dict[int, dict] = {
        1: {"name": "🏆 Войди в Топ-10",       "reward":  50_000, "target": 1,    "type": "top",      "emoji": "🏆"},
        2: {"name": "🔫 Захвати 5 районов",    "reward":  75_000, "target": 5,    "type": "capture",  "emoji": "🔫"},
        3: {"name": "⚡️ Майни 0.01 BTC",      "reward": 100_000, "target": 0.01, "type": "mining",   "emoji": "⚡️"},
        4: {"name": "💼 Развивай бизнес",      "reward":  80_000, "target": 3,    "type": "business", "emoji": "💼"},
    }

# ──────────────────────────────────────────────────────────
#  Бизнесы
# ──────────────────────────────────────────────────────────
BUSINESS_INCOME = {
    1: 5_000,
    2: 25_000,
    3: 100_000,
}
