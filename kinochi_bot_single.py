# ================= CONFIG =================
# Sinov uchun tokenni shu yerga yozishingiz mumkin.
# Masalan: BOT_TOKEN = "123456:ABC..."
BOT_TOKEN = "8970884665:AAFWMvQFezpLMeggLPDZZ-Emd-QiWMVB9bk"

# Telegram user ID'ingizni shu yerga yozing.
ADMINS = [5437530757]

DB_PATH = "kinochi.db"

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

if not BOT_TOKEN or BOT_TOKEN == "TOKENNI_SHU_YERGA_QOYING":
    raise RuntimeError("BOT_TOKEN ni fayl ichidagi CONFIG bo'limida kiriting.")



# ================= STATES.PY =================
from aiogram.fsm.state import State, StatesGroup


class AddMovie(StatesGroup):
    video = State()
    field = State()  # nom, til, sifat, janr, kategoriya — ketma-ket so'raladi
    code = State()


class EditMovie(StatesGroup):
    value = State()


class FindMovie(StatesGroup):
    query = State()


class AddChannel(StatesGroup):
    channel = State()


class EditTemplate(StatesGroup):
    value = State()

# ================= DATABASE.PY =================

from typing import Any, Optional

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    full_name  TEXT,
    username   TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS movies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    title      TEXT NOT NULL DEFAULT '',
    language   TEXT NOT NULL DEFAULT '',
    quality    TEXT NOT NULL DEFAULT '',
    genre      TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    caption    TEXT NOT NULL DEFAULT '',
    file_id    TEXT NOT NULL,
    file_type  TEXT NOT NULL DEFAULT 'video',
    views      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS channels (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    username    TEXT,
    invite_link TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Baza ulanmagan. Avval db.connect() chaqiring.")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        """Eski bazaga yangi ustunlarni qo'shadi (ma'lumotlar saqlanib qoladi)."""
        async with self.conn.execute("PRAGMA table_info(movies)") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for column in ("language", "quality", "genre", "category"):
            if column not in existing:
                await self.conn.execute(
                    f"ALTER TABLE movies ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---------- ichki yordamchilar ----------

    async def _fetchone(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def _scalar(self, sql: str, params: tuple = ()) -> Any:
        row = await self._fetchone(sql, params)
        return row[0] if row else None

    # ---------- foydalanuvchilar ----------

    async def add_user(self, user_id: int, full_name: str, username: str | None) -> bool:
        """Yangi foydalanuvchi bo'lsa True qaytaradi."""
        async with self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username) VALUES (?, ?, ?)",
            (user_id, full_name, username),
        ) as cur:
            created = cur.rowcount > 0
        if not created:
            await self.conn.execute(
                "UPDATE users SET full_name = ?, username = ? WHERE user_id = ?",
                (full_name, username, user_id),
            )
        await self.conn.commit()
        return created

    async def count_users(self) -> int:
        return await self._scalar("SELECT COUNT(*) FROM users") or 0

    async def count_users_since(self, days: int) -> int:
        return await self._scalar(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ) or 0

    async def all_user_ids(self) -> list[int]:
        rows = await self._fetchall("SELECT user_id FROM users")
        return [row["user_id"] for row in rows]

    # ---------- kinolar ----------

    async def add_movie(
        self,
        code: str,
        title: str,
        file_id: str,
        file_type: str = "video",
        language: str = "",
        quality: str = "",
        genre: str = "",
        category: str = "",
        caption: str = "",
    ) -> bool:
        """Kod band bo'lsa False qaytaradi."""
        try:
            await self.conn.execute(
                """
                INSERT INTO movies
                    (code, title, language, quality, genre, category, caption, file_id, file_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (code, title, language, quality, genre, category, caption, file_id, file_type),
            )
        except aiosqlite.IntegrityError:
            return False
        await self.conn.commit()
        return True

    async def get_movie_by_code(self, code: str) -> Optional[aiosqlite.Row]:
        return await self._fetchone("SELECT * FROM movies WHERE code = ?", (code,))

    async def get_movie(self, movie_id: int) -> Optional[aiosqlite.Row]:
        return await self._fetchone("SELECT * FROM movies WHERE id = ?", (movie_id,))

    async def search_movies(self, query: str, limit: int = 15) -> list[aiosqlite.Row]:
        pattern = f"%{query}%"
        return await self._fetchall(
            """
            SELECT * FROM movies
            WHERE title LIKE ? OR caption LIKE ? OR genre LIKE ? OR language LIKE ?
            ORDER BY views DESC, id DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, limit),
        )

    async def list_movies(self, offset: int = 0, limit: int = 8) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM movies ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )

    async def count_movies(self) -> int:
        return await self._scalar("SELECT COUNT(*) FROM movies") or 0

    async def total_views(self) -> int:
        return await self._scalar("SELECT COALESCE(SUM(views), 0) FROM movies") or 0

    async def top_movies(self, limit: int = 5) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM movies ORDER BY views DESC, id DESC LIMIT ?", (limit,)
        )

    async def increment_views(self, movie_id: int) -> None:
        await self.conn.execute("UPDATE movies SET views = views + 1 WHERE id = ?", (movie_id,))
        await self.conn.commit()

    async def update_movie_field(self, movie_id: int, field: str, value: str) -> bool:
        if field not in {"code", "title", "language", "quality", "genre", "category", "caption"}:
            raise ValueError(f"Ruxsat etilmagan maydon: {field}")
        try:
            await self.conn.execute(
                f"UPDATE movies SET {field} = ? WHERE id = ?", (value, movie_id)
            )
        except aiosqlite.IntegrityError:
            return False
        await self.conn.commit()
        return True

    async def delete_movie(self, movie_id: int) -> None:
        await self.conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
        await self.conn.commit()

    # ---------- sozlamalar ----------

    async def get_setting(self, key: str, default: str = "") -> str:
        value = await self._scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else value

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.conn.commit()

    async def delete_setting(self, key: str) -> None:
        await self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        await self.conn.commit()

    # ---------- majburiy obuna kanallari ----------

    async def add_channel(
        self, chat_id: int, title: str, username: str | None, invite_link: str | None
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO channels (chat_id, title, username, invite_link)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                username = excluded.username,
                invite_link = excluded.invite_link
            """,
            (chat_id, title, username, invite_link),
        )
        await self.conn.commit()

    async def list_channels(self) -> list[aiosqlite.Row]:
        return await self._fetchall("SELECT * FROM channels ORDER BY rowid")

    async def count_channels(self) -> int:
        return await self._scalar("SELECT COUNT(*) FROM channels") or 0

    async def delete_channel(self, chat_id: int) -> None:
        await self.conn.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        await self.conn.commit()


db = Database()

# ================= KEYBOARDS.PY =================

from typing import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


PAGE_SIZE = 8

# Kanal tanlash tugmasi uchun identifikator (javobda ham shu qaytadi)
CHANNEL_REQUEST_ID = 1

# ---------- reply klaviaturalar ----------

BTN_ADMIN = "🛠 Admin panel"
BTN_ADD_MOVIE = "➕ Kino qo'shish"
BTN_MOVIES = "🎬 Kinolar"
BTN_STATS = "📊 Statistika"
BTN_CHANNELS = "📢 Majburiy obuna"
BTN_TEMPLATE = "🧩 Shablon"
BTN_BACK = "◀️ Bosh menyu"
BTN_CANCEL = "❌ Bekor qilish"
BTN_SELECT_CHANNEL = "📢 Kanalni tanlash"
BTN_SKIP = "⏭ O'tkazib yuborish"

# Menyu tugmalari — FSM holatidagi handlerlar ularni ushlab qolmasligi uchun
MENU_BUTTONS = frozenset(
    {
        BTN_ADMIN,
        BTN_ADD_MOVIE,
        BTN_MOVIES,
        BTN_STATS,
        BTN_CHANNELS,
        BTN_TEMPLATE,
        BTN_BACK,
        BTN_CANCEL,
        BTN_SKIP,
        BTN_SELECT_CHANNEL,
    }
)


def main_menu(user_id: int) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    """Oddiy foydalanuvchida klaviatura yo'q, adminda — admin tugmasi."""
    if not is_admin(user_id):
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_ADMIN)]],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_MOVIE), KeyboardButton(text=BTN_MOVIES)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_CHANNELS)],
            [KeyboardButton(text=BTN_TEMPLATE), KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def step_menu(options: Sequence[str] = (), skip: bool = True) -> ReplyKeyboardMarkup:
    """Bosqichli so'rovlar uchun: tayyor variantlar + o'tkazib yuborish/bekor qilish."""
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=option) for option in options[i : i + 2]]
        for i in range(0, len(options), 2)
    ]
    last = [KeyboardButton(text=BTN_CANCEL)]
    if skip:
        last.insert(0, KeyboardButton(text=BTN_SKIP))
    rows.append(last)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def select_channel_menu() -> ReplyKeyboardMarkup:
    """Tugma bosilganda Telegram kanal tanlash oynasini ochadi."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=BTN_SELECT_CHANNEL,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=CHANNEL_REQUEST_ID,
                        chat_is_channel=True,
                        bot_is_member=True,
                        request_title=True,
                        request_username=True,
                    ),
                )
            ],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


# ---------- inline klaviaturalar ----------


def subscribe_kb(channels: Sequence) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, channel in enumerate(channels, start=1):
        url = channel["invite_link"]
        if channel["username"]:
            url = f"https://t.me/{channel['username']}"
        if not url:
            continue
        rows.append(
            [InlineKeyboardButton(text=f"📢 {channel['title'] or f'Kanal {index}'}", url=url)]
        )
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def movies_list_kb(movies: Sequence, page: int, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"🎬 {movie['code']} — {movie['title'][:30] or 'nomsiz'}",
                callback_data=f"movie:{movie['id']}:{page}",
            )
        ]
        for movie in movies
    ]

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        if pages > 3:
            nav.append(InlineKeyboardButton(text="⏮", callback_data="page:0"))
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{page + 1}"))
        if pages > 3:
            nav.append(InlineKeyboardButton(text="⏭", callback_data=f"page:{pages - 1}"))
    rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔎 Kod yoki nom bo'yicha topish", callback_data="find")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def found_movies_kb(movies: Sequence) -> InlineKeyboardMarkup:
    """Admin qidiruvi natijalari — bosilganda boshqaruv kartochkasi ochiladi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🎬 {movie['code']} — {movie['title'][:30] or 'nomsiz'}",
                    callback_data=f"movie:{movie['id']}:0",
                )
            ]
            for movie in movies
        ]
    )


def movie_manage_kb(movie_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Tahrirlash", callback_data=f"edit:{movie_id}:{page}"
                ),
                InlineKeyboardButton(
                    text="🗑 O'chirish", callback_data=f"del:{movie_id}:{page}"
                ),
            ],
            [InlineKeyboardButton(text="◀️ Ro'yxat", callback_data=f"page:{page}")],
        ]
    )


def edit_movie_kb(movie_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗂 Kod", callback_data=f"field:code:{movie_id}:{page}"
                ),
                InlineKeyboardButton(
                    text="🍿 Nom", callback_data=f"field:title:{movie_id}:{page}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🇺🇿 Til", callback_data=f"field:language:{movie_id}:{page}"
                ),
                InlineKeyboardButton(
                    text="💾 Sifat", callback_data=f"field:quality:{movie_id}:{page}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎞️ Janr", callback_data=f"field:genre:{movie_id}:{page}"
                ),
                InlineKeyboardButton(
                    text="⛔️ Kategoriya", callback_data=f"field:category:{movie_id}:{page}"
                ),
            ],
            [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"movie:{movie_id}:{page}")],
        ]
    )


def confirm_delete_kb(movie_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, o'chirilsin", callback_data=f"delyes:{movie_id}:{page}"
                ),
                InlineKeyboardButton(
                    text="❌ Yo'q", callback_data=f"movie:{movie_id}:{page}"
                ),
            ]
        ]
    )


def template_kb(is_custom: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="tpl_edit")]]
    if is_custom:
        rows.append(
            [InlineKeyboardButton(text="♻️ Standart shablon", callback_data="tpl_reset")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_kb(channels: Sequence) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"🗑 {channel['title'] or channel['chat_id']}",
                callback_data=f"chdel:{channel['chat_id']}",
            )
        ]
        for channel in channels
    ]
    rows.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="chadd")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================= UTILS.PY =================

import html
import logging
import re

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError


logger = logging.getLogger(__name__)

SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}


async def unsubscribed_channels(bot: Bot, user_id: int) -> list:
    """Foydalanuvchi obuna bo'lmagan majburiy kanallar ro'yxati."""
    result = []
    for channel in await db.list_channels():
        try:
            member = await bot.get_chat_member(channel["chat_id"], user_id)
        except TelegramAPIError as error:
            # Bot kanalda admin emas yoki kanal o'chirilgan — foydalanuvchini bloklamaymiz
            logger.warning("Kanalni tekshirib bo'lmadi (%s): %s", channel["chat_id"], error)
            continue
        if member.status not in SUBSCRIBED_STATUSES:
            result.append(channel)
    return result


SEPARATOR = "➖➖➖➖➖➖➖➖➖➖➖➖"

DEFAULT_TEMPLATE = (
    "🍿 <b>{nom}</b>\n"
    f"{SEPARATOR}\n"
    "{tavsif}\n"
    "🇺🇿 Tili: <b>{til}</b>\n"
    "💾 Sifati: <b>{sifat}</b>\n"
    "🎞 Janri: <b>{janr}</b>\n"
    "⛔️ Kategoriya: <b>{kategoriya}</b>\n"
    f"{SEPARATOR}\n"
    "🗂 Kod: <code>{kod}</code>\n"
    "👁 Ko'rildi: {korishlar} marta\n"
    "🤖 {bot}"
)

# Har bir o'rin egallovchi va uning izohi (admin panelda ko'rsatiladi)
PLACEHOLDERS = {
    "nom": "kino nomi",
    "til": "tili",
    "sifat": "sifati",
    "janr": "janri",
    "kategoriya": "ko'rish kategoriyasi",
    "kod": "kino kodi",
    "korishlar": "necha marta ko'rilgani",
    "bot": "bot havolasi (@username)",
    "tavsif": "erkin tavsif (eski kinolarda)",
}

TEMPLATE_KEY = "caption_template"
CAPTION_LIMIT = 1024

# Bot ishga tushganda to'ldiriladi
BOT_USERNAME = ""
TEMPLATE = DEFAULT_TEMPLATE


def set_bot_username(username: str) -> None:
    global BOT_USERNAME
    BOT_USERNAME = username or ""


def set_template(template: str) -> None:
    """Bo'sh qiymat berilsa — standart shablonga qaytadi."""
    global TEMPLATE
    TEMPLATE = template.strip() or DEFAULT_TEMPLATE


def number(value: int) -> str:
    """1245 -> «1 245»"""
    return f"{value:,}".replace(",", " ")


def esc(text) -> str:
    """HTML uchun xavfsiz matn. Apostrof (O'zbek) o'zgarishsiz qoladi."""
    return html.escape(str(text), quote=False)


def field(movie, name: str) -> str:
    """Ustun bazada bo'lmasa ham (eski yozuvlar) xatolik bermaydi."""
    try:
        return movie[name] or ""
    except (IndexError, KeyError):
        return ""


COLUMNS = {
    "nom": "title",
    "til": "language",
    "sifat": "quality",
    "janr": "genre",
    "kategoriya": "category",
    "kod": "code",
    "tavsif": "caption",
}

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def template_values(movie, views: int | None = None) -> dict[str, str]:
    values = {key: esc(field(movie, column)) for key, column in COLUMNS.items()}
    values["korishlar"] = number(movie["views"] if views is None else views)
    values["bot"] = f"@{BOT_USERNAME}" if BOT_USERNAME else ""
    return values


def render_template(template: str, values: dict[str, str]) -> str:
    """Qiymati bo'sh o'rin egallovchi bo'lgan qator butunlay tushib qoladi."""
    lines: list[str] = []
    for line in template.split("\n"):
        used = [name for name in PLACEHOLDER_RE.findall(line) if name in values]
        if used and not all(values[name] for name in used):
            continue
        rendered = PLACEHOLDER_RE.sub(
            lambda match: values.get(match.group(1), match.group(0)), line
        )
        # Ketma-ket takrorlangan ajratgichlarni yig'ishtiramiz
        if lines and rendered.strip() and rendered == lines[-1]:
            continue
        lines.append(rendered)
    return "\n".join(lines).strip()


def movie_caption(movie, views: int | None = None) -> str:
    """Foydalanuvchiga yuboriladigan caption — joriy shablon bo'yicha."""
    return render_template(TEMPLATE, template_values(movie, views))


# Shablonni ko'rib chiqish uchun namuna
SAMPLE_MOVIE = {
    "title": "Buni ishq deydilar 2",
    "language": "O'zbek tilida",
    "quality": "720p",
    "genre": "Romantic komediya",
    "category": "16+",
    "code": "1320",
    "caption": "",
    "views": 1245,
}


def template_preview(template: str) -> str:
    return render_template(template, template_values(SAMPLE_MOVIE))


def movie_info(movie) -> str:
    """Admin panelidagi batafsil ma'lumot."""
    dash = lambda name: esc(field(movie, name)) or "—"
    return (
        f"🎬 <b>{esc(field(movie, 'title')) or 'Nomsiz'}</b>\n\n"
        f"🗂 Kod: <code>{esc(movie['code'])}</code>\n"
        f"🇺🇿 Tili: {dash('language')}\n"
        f"💾 Sifati: {dash('quality')}\n"
        f"🎞️ Janri: {dash('genre')}\n"
        f"⛔️ Kategoriya: {dash('category')}\n"
        f"📦 Turi: {movie['file_type']}\n"
        f"👁 Ko'rishlar: {movie['views']}\n"
        f"🗓 Qo'shilgan: {movie['created_at']}"
    )

# ================= MIDDLEWARES/SUBSCRIPTION.PY =================

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject


TEXT = (
    "👋 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling.\n\n"
    "Obuna bo'lgach — <b>✅ Tekshirish</b> tugmasini bosing."
)


class SubscriptionMiddleware(BaseMiddleware):
    """Majburiy obuna tekshiruvi. Adminlar va tekshirish tugmasi chetlab o'tiladi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        bot: Bot = data["bot"]

        if user is None or is_admin(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "check_subs":
            return await handler(event, data)

        channels = await unsubscribed_channels(bot, user.id)
        if not channels:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(TEXT, reply_markup=subscribe_kb(channels))
        elif isinstance(event, CallbackQuery):
            await event.answer("Avval kanallarga obuna bo'ling.", show_alert=True)
            if event.message:
                await event.message.answer(TEXT, reply_markup=subscribe_kb(channels))
        return None

# ================= HANDLERS/START.PY =================


from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message


router = Router()

WELCOME = (
    "🎬 <b>Kinochi botga xush kelibsiz, {name}!</b>\n\n"
    "Kino topish uchun:\n"
    "• kino <b>kodini</b> yuboring (masalan: <code>101</code>)\n"
    "• yoki kino <b>nomini</b> yozing (masalan: <code>Titanik</code>)"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.add_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
    )
    await message.answer(
        WELCOME.format(name=esc(message.from_user.first_name)),
        reply_markup=main_menu(message.from_user.id),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Yordam</b>\n\n"
        "Kino kodini yoki nomini yuboring — bot uni topib beradi.\n"
        "/start — botni qayta ishga tushirish"
    )


@router.callback_query(F.data == "check_subs")
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    channels = await unsubscribed_channels(bot, callback.from_user.id)
    if channels:
        await callback.answer("❌ Siz hali barcha kanallarga obuna bo'lmadingiz.", show_alert=True)
        return

    await callback.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.", show_alert=True)
    await db.add_user(
        callback.from_user.id,
        callback.from_user.full_name,
        callback.from_user.username,
    )
    if callback.message:
        await callback.message.delete()
        await callback.message.answer(
            WELCOME.format(name=esc(callback.from_user.first_name)),
            reply_markup=main_menu(callback.from_user.id),
        )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()

# ================= HANDLERS/SEARCH.PY =================

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


router = Router()
logger = logging.getLogger(__name__)

NOT_FOUND = (
    "😔 Hech narsa topilmadi.\n\n"
    "Kod to'g'ri kiritilganini tekshiring yoki kino nomini boshqacha yozib ko'ring."
)


async def send_movie(message: Message, movie, count_view: bool = True) -> bool:
    # Ko'rishlar soni caption'da darhol yangilangan holda ko'rinadi
    caption = movie_caption(movie, views=movie["views"] + (1 if count_view else 0))
    try:
        if movie["file_type"] == "document":
            await message.answer_document(movie["file_id"], caption=caption)
        else:
            await message.answer_video(movie["file_id"], caption=caption)
    except TelegramAPIError as error:
        logger.error("Kinoni yuborib bo'lmadi (id=%s): %s", movie["id"], error)
        await message.answer("⚠️ Bu kinoni yuborishda xatolik yuz berdi. Adminga xabar bering.")
        return False
    if count_view:
        await db.increment_views(movie["id"])
    return True


def results_kb(movies) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🎬 {movie['title'][:40] or movie['code']}",
                    callback_data=f"get:{movie['id']}",
                )
            ]
            for movie in movies
        ]
    )


@router.message(F.text & ~F.text.startswith("/"))
async def search(message: Message) -> None:
    query = message.text.strip()
    if not query:
        return

    await db.add_user(
        message.from_user.id, message.from_user.full_name, message.from_user.username
    )

    movie = await db.get_movie_by_code(query)
    if movie:
        await send_movie(message, movie)
        return

    movies = await db.search_movies(query)
    if not movies:
        await message.answer(NOT_FOUND)
        return

    if len(movies) == 1:
        await send_movie(message, movies[0])
        return

    await message.answer(
        f"🔎 «{esc(query)}» bo'yicha {len(movies)} ta natija topildi:",
        reply_markup=results_kb(movies),
    )


@router.callback_query(F.data.startswith("get:"))
async def get_movie(callback: CallbackQuery) -> None:
    movie_id = int(callback.data.split(":")[1])
    movie = await db.get_movie(movie_id)
    if not movie:
        await callback.answer("Bu kino o'chirilgan.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await send_movie(callback.message, movie)

# ================= HANDLERS/ADMIN.PY =================

import logging
import re
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MessageOriginChannel


from .search import send_movie

logger = logging.getLogger(__name__)

router = Router()
# Butun router faqat adminlar uchun ishlaydi
router.message.filter(F.from_user.id.in_(ADMINS))
router.callback_query.filter(F.from_user.id.in_(ADMINS))

FIELD_NAMES = {
    "code": "kod",
    "title": "nom",
    "language": "til",
    "quality": "sifat",
    "genre": "janr",
    "category": "kategoriya",
    "caption": "tavsif",
}


@dataclass(frozen=True)
class Step:
    """Kino qo'shishda ketma-ket so'raladigan maydon."""

    name: str
    prompt: str
    options: tuple[str, ...] = ()
    required: bool = False


STEPS: tuple[Step, ...] = (
    Step("title", "🍿 <b>Kino nomini</b> yuboring:", required=True),
    Step(
        "language",
        "🇺🇿 <b>Tilini</b> yuboring:",
        ("O'zbek tilida", "Rus tilida", "Ingliz tilida", "O'zbek subtitr"),
    ),
    Step("quality", "💾 <b>Sifatini</b> yuboring:", ("480p", "720p", "1080p", "4K")),
    Step("genre", "🎞️ <b>Janrini</b> yuboring (masalan: Romantic komediya):"),
    Step("category", "⛔️ <b>Ko'rish kategoriyasini</b> yuboring:", ("6+", "12+", "16+", "18+")),
)

STEP_OPTIONS: dict[str, tuple[str, ...]] = {step.name: step.options for step in STEPS}

# Admin shablonda HTML teglarini qo'lda yozganini aniqlash uchun
HTML_TAG_RE = re.compile(r"</?(b|strong|i|em|u|s|code|pre|a|tg-spoiler|blockquote)\b", re.I)


# ---------- panel ----------


@router.message(F.text == BTN_ADMIN)
async def open_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🛠 <b>Admin panel</b>\n\nKerakli bo'limni tanlang:", reply_markup=admin_menu()
    )


@router.message(F.text == BTN_BACK)
async def close_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 Bosh menyu", reply_markup=main_menu(message.from_user.id))


@router.message(F.text == BTN_CANCEL)
@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("🛠 Admin panel", reply_markup=admin_menu())
        return
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_menu())


# ---------- kino qo'shish ----------


@router.message(F.text == BTN_ADD_MOVIE)
async def add_movie_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddMovie.video)
    await message.answer(
        "🎬 Avval kinoning <b>o'zini</b> (video yoki fayl) yuboring.\n\n"
        "Keyin nomi, tili, sifati, janri va kategoriyasi ketma-ket so'raladi.",
        reply_markup=cancel_menu(),
    )


@router.message(AddMovie.video, F.video | F.document | F.animation)
async def add_movie_file(message: Message, state: FSMContext) -> None:
    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.animation:
        file_id, file_type = message.animation.file_id, "animation"
    else:
        file_id, file_type = message.document.file_id, "document"

    await state.update_data(file_id=file_id, file_type=file_type, step=0)
    await state.set_state(AddMovie.field)
    await message.answer("✅ Fayl qabul qilindi.")
    await ask_step(message, 0)


@router.message(AddMovie.video)
async def add_movie_wrong(message: Message) -> None:
    await message.answer("⚠️ Iltimos, video yoki fayl yuboring.")


async def ask_step(message: Message, index: int) -> None:
    step = STEPS[index]
    hint = "" if step.required else f"\n\n<i>Kerak bo'lmasa — «{BTN_SKIP}»</i>"
    await message.answer(
        f"{step.prompt}{hint}",
        reply_markup=step_menu(step.options, skip=not step.required),
    )


@router.message(AddMovie.field, F.text)
async def add_movie_field(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data.get("step", 0)
    step = STEPS[index]
    value = message.text.strip()

    if value == BTN_SKIP:
        if step.required:
            await message.answer("⚠️ Bu maydon majburiy, o'tkazib yuborib bo'lmaydi.")
            return
        value = ""

    await state.update_data(**{step.name: value}, step=index + 1)

    if index + 1 < len(STEPS):
        await ask_step(message, index + 1)
        return

    await state.set_state(AddMovie.code)
    await message.answer(
        "🗂 Oxirgi qadam — kino <b>kodini</b> yuboring (masalan: <code>1320</code>).\n"
        "Foydalanuvchi shu kodni yozib kinoni topadi.",
        reply_markup=cancel_menu(),
    )


@router.message(AddMovie.field)
async def add_movie_field_wrong(message: Message) -> None:
    await message.answer("⚠️ Javobni matn ko'rinishida yuboring.")


@router.message(AddMovie.code, F.text)
async def add_movie_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    if len(code) > 32 or "\n" in code:
        await message.answer("⚠️ Kod juda uzun. 32 belgigacha bo'lgan kod yuboring.")
        return

    if await db.get_movie_by_code(code):
        await message.answer(
            f"⚠️ <code>{esc(code)}</code> kodi allaqachon band. Boshqa kod yuboring."
        )
        return

    data = await state.get_data()
    added = await db.add_movie(
        code=code,
        title=data.get("title", ""),
        language=data.get("language", ""),
        quality=data.get("quality", ""),
        genre=data.get("genre", ""),
        category=data.get("category", ""),
        file_id=data["file_id"],
        file_type=data["file_type"],
    )
    await state.clear()

    if not added:
        await message.answer("⚠️ Kod band ekan, qaytadan urinib ko'ring.", reply_markup=admin_menu())
        return

    movie = await db.get_movie_by_code(code)
    await message.answer(
        "✅ Kino saqlandi! Foydalanuvchi uni shunday ko'radi:", reply_markup=admin_menu()
    )
    await send_movie(message, movie, count_view=False)


@router.message(AddMovie.code)
async def add_movie_code_wrong(message: Message) -> None:
    await message.answer("⚠️ Kodni matn ko'rinishida yuboring.")


# ---------- statistika ----------


@router.message(F.text == BTN_STATS)
async def stats(message: Message) -> None:
    users = await db.count_users()
    today = await db.count_users_since(1)
    week = await db.count_users_since(7)
    movies = await db.count_movies()
    views = await db.total_views()
    channels = await db.count_channels()
    top = await db.top_movies(5)

    text = (
        "📊 <b>Umumiy statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users}</b>\n"
        f"➕ Bugun qo'shilgan: <b>{today}</b>\n"
        f"📅 Hafta davomida: <b>{week}</b>\n\n"
        f"🎬 Kinolar: <b>{movies}</b>\n"
        f"👁 Jami ko'rishlar: <b>{views}</b>\n"
        f"📢 Majburiy kanallar: <b>{channels}</b>"
    )
    if top:
        rows = "\n".join(
            f"{i}. {esc(m['title'] or m['code'])} — {m['views']} 👁"
            for i, m in enumerate(top, start=1)
        )
        text += f"\n\n🔥 <b>Eng ko'p ko'rilganlar:</b>\n{rows}"

    await message.answer(text, reply_markup=admin_menu())


# ---------- kinolar ro'yxati ----------


async def render_page(page: int) -> tuple[str, object | None]:
    total = await db.count_movies()
    if total == 0:
        return "🎬 Hozircha bazada kino yo'q.", None

    page = max(0, min(page, (total - 1) // PAGE_SIZE))
    movies = await db.list_movies(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    text = (
        f"🎬 <b>Kinolar</b> (jami: {total})\n\n"
        "Tahrirlash yoki o'chirish uchun ro'yxatdan tanlang.\n"
        "Tezroq yo'l — kino <b>kodini</b> yoki <b>nomini</b> shu yerga yozib yuboring."
    )
    return text, movies_list_kb(movies, page, total)


@router.message(F.text == BTN_MOVIES)
async def movies_list(message: Message, state: FSMContext) -> None:
    # Ro'yxat ochiq turganda yozilgan matn kod/nom bo'yicha qidiruv sifatida qabul qilinadi
    await state.set_state(FindMovie.query)
    text, markup = await render_page(0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "find")
async def movie_find_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FindMovie.query)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "🔎 Kino <b>kodini</b> (masalan: <code>1320</code>) yoki <b>nomini</b> yuboring:",
            reply_markup=cancel_menu(),
        )


@router.message(FindMovie.query, F.text, ~F.text.in_(MENU_BUTTONS))
async def movie_find(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    movie = await db.get_movie_by_code(query)
    if movie:
        await state.clear()
        await message.answer(movie_info(movie), reply_markup=movie_manage_kb(movie["id"], 0))
        return

    movies = await db.search_movies(query, limit=20)
    if not movies:
        await message.answer(
            f"😔 «{esc(query)}» bo'yicha hech narsa topilmadi.\n"
            "Boshqa kod yoki nom yuboring."
        )
        return

    if len(movies) == 1:
        await state.clear()
        await message.answer(
            movie_info(movies[0]), reply_markup=movie_manage_kb(movies[0]["id"], 0)
        )
        return

    await message.answer(
        f"🔎 «{esc(query)}» bo'yicha {len(movies)} ta natija:",
        reply_markup=found_movies_kb(movies),
    )


@router.callback_query(F.data.startswith("page:"))
async def movies_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    text, markup = await render_page(page)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("movie:"))
async def movie_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, movie_id, page = callback.data.split(":")
    movie = await db.get_movie(int(movie_id))
    if not movie:
        await callback.answer("Bu kino topilmadi.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            movie_info(movie), reply_markup=movie_manage_kb(int(movie_id), int(page))
        )


# ---------- o'chirish ----------


@router.callback_query(F.data.startswith("del:"))
async def movie_delete_confirm(callback: CallbackQuery) -> None:
    _, movie_id, page = callback.data.split(":")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "🗑 Ushbu kino o'chirilsinmi? Bu amalni orqaga qaytarib bo'lmaydi.",
            reply_markup=confirm_delete_kb(int(movie_id), int(page)),
        )


@router.callback_query(F.data.startswith("delyes:"))
async def movie_delete(callback: CallbackQuery) -> None:
    _, movie_id, page = callback.data.split(":")
    await db.delete_movie(int(movie_id))
    await callback.answer("🗑 O'chirildi", show_alert=True)
    text, markup = await render_page(int(page))
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


# ---------- tahrirlash ----------


@router.callback_query(F.data.startswith("edit:"))
async def movie_edit_menu(callback: CallbackQuery) -> None:
    _, movie_id, page = callback.data.split(":")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "✏️ Qaysi maydonni tahrirlaysiz?",
            reply_markup=edit_movie_kb(int(movie_id), int(page)),
        )


@router.callback_query(F.data.startswith("field:"))
async def movie_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, field, movie_id, page = callback.data.split(":")
    await state.set_state(EditMovie.value)
    await state.update_data(field=field, movie_id=int(movie_id), page=int(page))
    await callback.answer()
    if callback.message:
        options = STEP_OPTIONS.get(field, ())
        can_skip = field not in {"code", "title"}
        hint = f"\n\n<i>Bo'sh qoldirish uchun — «{BTN_SKIP}»</i>" if can_skip else ""
        await callback.message.answer(
            f"✏️ Yangi <b>{FIELD_NAMES[field]}</b> ni yuboring:{hint}",
            reply_markup=step_menu(options, skip=can_skip),
        )


@router.message(EditMovie.value, F.text)
async def movie_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field, movie_id, page = data["field"], data["movie_id"], data["page"]
    value = message.text.strip()

    if value == BTN_SKIP:
        if field in {"code", "title"}:
            await message.answer("⚠️ Bu maydonni bo'sh qoldirib bo'lmaydi.")
            return
        value = ""

    if field == "code":
        existing = await db.get_movie_by_code(value)
        if existing and existing["id"] != movie_id:
            await message.answer("⚠️ Bu kod band. Boshqa kod yuboring.")
            return

    updated = await db.update_movie_field(movie_id, field, value)
    await state.clear()
    if not updated:
        await message.answer("⚠️ Saqlab bo'lmadi. Qaytadan urinib ko'ring.", reply_markup=admin_menu())
        return

    movie = await db.get_movie(movie_id)
    await message.answer("✅ Yangilandi.", reply_markup=admin_menu())
    if movie:
        await message.answer(movie_info(movie), reply_markup=movie_manage_kb(movie_id, page))


@router.message(EditMovie.value)
async def movie_edit_value_wrong(message: Message) -> None:
    await message.answer("⚠️ Qiymatni matn ko'rinishida yuboring.")


# ---------- caption shabloni ----------


async def template_text() -> tuple[str, bool]:
    saved = await db.get_setting(TEMPLATE_KEY)
    current = saved or DEFAULT_TEMPLATE
    hints = "\n".join(f"<code>{{{key}}}</code> — {name}" for key, name in PLACEHOLDERS.items())
    text = (
        f"🧩 <b>Caption shabloni</b> "
        f"({'o‘zgartirilgan' if saved else 'standart'})\n\n"
        f"<b>Hozirgi ko'rinishi:</b>\n{template_preview(current)}\n\n"
        f"<b>Shablon matni:</b>\n<pre>{esc(current)}</pre>\n\n"
        f"<b>O'rin egallovchilar:</b>\n{hints}\n\n"
        "<i>Qiymati bo'sh bo'lgan o'rin egallovchi turgan qator umuman chiqmaydi.</i>"
    )
    return text, bool(saved)


@router.message(F.text == BTN_TEMPLATE)
async def template_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, is_custom = await template_text()
    await message.answer(text, reply_markup=template_kb(is_custom))


@router.callback_query(F.data == "tpl_edit")
async def template_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTemplate.value)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "✏️ Yangi shablonni yuboring.\n\n"
            "Telegram'ning o'z formatlashidan foydalaning (<b>qalin</b>, <i>kursiv</i>, "
            "<code>monospace</code>) — u avtomatik saqlanadi.\n"
            f"O'rin egallovchilar: {', '.join('{' + key + '}' for key in PLACEHOLDERS)}",
            reply_markup=cancel_menu(),
        )


@router.message(EditTemplate.value, F.text)
async def template_save(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    # Admin HTML teglarini o'zi yozgan bo'lsa — o'sha holicha, aks holda
    # Telegram'dagi formatlashini (qalin, kursiv) HTML ga o'giramiz
    template = raw if HTML_TAG_RE.search(raw) else message.html_text.strip()

    unknown = {
        name for name in PLACEHOLDER_RE.findall(template) if name not in PLACEHOLDERS
    }
    if unknown:
        await message.answer(
            "⚠️ Noma'lum o'rin egallovchi: "
            + ", ".join(f"<code>{{{esc(name)}}}</code>" for name in sorted(unknown))
            + "\nRuxsat etilganlar: "
            + ", ".join(f"<code>{{{key}}}</code>" for key in PLACEHOLDERS)
        )
        return

    preview = template_preview(template)
    if len(preview) > CAPTION_LIMIT:
        await message.answer(
            f"⚠️ Shablon juda uzun ({len(preview)} belgi). "
            f"Telegram caption uchun {CAPTION_LIMIT} belgidan oshmasligi kerak."
        )
        return

    # Saqlashdan oldin HTML to'g'riligini Telegram'ning o'zida tekshiramiz
    try:
        await message.answer(preview)
    except TelegramBadRequest as error:
        logger.warning("Shablon HTML xatosi: %s", error)
        await message.answer(
            "❌ Shablonni Telegram qabul qilmadi — HTML teglarida xato bor.\n\n"
            f"<code>{esc(str(error))}</code>\n\n"
            "Teglar juftlanganini tekshiring: <code>&lt;b&gt;...&lt;/b&gt;</code>"
        )
        return

    await db.set_setting(TEMPLATE_KEY, template)
    set_template(template)
    await state.clear()
    await message.answer("☝️ Shablon saqlandi, kinolar shu ko'rinishda yuboriladi.",
                         reply_markup=admin_menu())


@router.message(EditTemplate.value)
async def template_save_wrong(message: Message) -> None:
    await message.answer("⚠️ Shablonni matn ko'rinishida yuboring.")


@router.callback_query(F.data == "tpl_reset")
async def template_reset(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.delete_setting(TEMPLATE_KEY)
    set_template("")
    await callback.answer("♻️ Standart shablon qaytarildi", show_alert=True)
    text, is_custom = await template_text()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=template_kb(is_custom))


# ---------- majburiy obuna kanallari ----------


async def channels_text() -> str:
    channels = await db.list_channels()
    if not channels:
        return "📢 <b>Majburiy obuna</b>\n\nHozircha kanal qo'shilmagan."
    rows = "\n".join(
        f"{i}. {esc(ch['title'] or '—')} "
        f"({'@' + ch['username'] if ch['username'] else ch['chat_id']})"
        for i, ch in enumerate(channels, start=1)
    )
    return (
        f"📢 <b>Majburiy obuna kanallari</b>\n\n{rows}\n\n"
        "O'chirish uchun kanal ustiga bosing."
    )


@router.message(F.text == BTN_CHANNELS)
async def channels_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await channels_text(), reply_markup=channels_kb(await db.list_channels()))


@router.callback_query(F.data == "chadd")
async def channel_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddChannel.channel)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📢 Pastdagi <b>«Kanalni tanlash»</b> tugmasini bosing va ro'yxatdan "
            "kerakli kanalni tanlang.\n\n"
            "Yoki qo'lda yuboring:\n"
            "• kanal username'i: <code>@kanal_nomi</code>\n"
            "• kanal ID'si: <code>-1001234567890</code>\n"
            "• kanaldan biror postni <b>forward</b> qiling\n\n"
            "⚠️ Bot kanalda <b>admin</b> bo'lishi shart!",
            reply_markup=select_channel_menu(),
        )


@router.message(AddChannel.channel, F.chat_shared)
async def channel_add_shared(message: Message, state: FSMContext, bot: Bot) -> None:
    """Admin «Kanalni tanlash» tugmasi orqali kanalni tanlaganda."""
    shared = message.chat_shared
    await save_channel(
        message, state, bot, shared.chat_id, shared_title=shared.title or ""
    )


@router.message(AddChannel.channel)
async def channel_add_manual(message: Message, state: FSMContext, bot: Bot) -> None:
    """Username, ID yoki forward orqali qo'shish."""
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        target: str | int = origin.chat.id
    elif message.text:
        text = message.text.strip()
        target = int(text) if text.lstrip("-").isdigit() else text
    else:
        await message.answer(
            "⚠️ «Kanalni tanlash» tugmasidan foydalaning yoki kanal username'i, "
            "ID'si yoxud forward qilingan postni yuboring."
        )
        return

    await save_channel(message, state, bot, target)


async def save_channel(
    message: Message,
    state: FSMContext,
    bot: Bot,
    target: str | int,
    shared_title: str = "",
) -> None:
    label = f"«{esc(shared_title)}»" if shared_title else f"<code>{target}</code>"
    try:
        chat = await bot.get_chat(target)
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError as error:
        logger.warning("Kanalni olishda xatolik (%s): %s", target, error)
        await message.answer(
            f"❌ {label} kanaliga bot kira olmadi.\n\n"
            f"Sabab (Telegram javobi): <code>{esc(str(error))}</code>\n\n"
            "👉 Nima qilish kerak:\n"
            "1. Kanalni oching → <b>Administrators</b> → <b>Add Admin</b>\n"
            f"2. Botni (@{(await bot.me()).username}) admin qilib qo'shing\n"
            "3. Shundan keyin kanalni yana tanlang\n\n"
            "⚠️ Botni oddiy <b>obunachi</b> qilib qo'shish yetarli emas — "
            "u <b>admin</b> bo'lishi shart."
        )
        return

    if me.status not in {"administrator", "creator"}:
        await message.answer(
            f"❌ Bot {label} kanalida admin emas (hozirgi holati: <code>{me.status}</code>).\n"
            "Kanal sozlamalarida botni administrator qilib qo'ying va qaytadan tanlang."
        )
        return

    invite_link = chat.invite_link
    if not chat.username and not invite_link:
        try:
            link = await bot.create_chat_invite_link(chat.id, name="Kinochi bot")
            invite_link = link.invite_link
        except TelegramAPIError as error:
            logger.warning("Invite link yaratib bo'lmadi (%s): %s", chat.id, error)

    if not chat.username and not invite_link:
        await message.answer(
            "❌ Kanal uchun havola olinmadi. Botga «Invite Users via Link» huquqini bering."
        )
        return

    await db.add_channel(chat.id, chat.title or "", chat.username, invite_link)
    await state.clear()
    await message.answer(
        f"✅ <b>{esc(chat.title or '')}</b> majburiy obunaga qo'shildi.",
        reply_markup=admin_menu(),
    )
    await message.answer(await channels_text(), reply_markup=channels_kb(await db.list_channels()))


@router.callback_query(F.data.startswith("chdel:"))
async def channel_delete(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":")[1])
    await db.delete_channel(chat_id)
    await callback.answer("🗑 Kanal o'chirildi", show_alert=True)
    if callback.message:
        await callback.message.edit_text(
            await channels_text(), reply_markup=channels_kb(await db.list_channels())
        )

# ================= BOT.PY =================

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await db.connect()
    set_template(await db.get_setting(TEMPLATE_KEY))

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Majburiy obuna — barcha handlerlardan oldin ishlaydi
    dp.message.outer_middleware(SubscriptionMiddleware())
    dp.callback_query.outer_middleware(SubscriptionMiddleware())

    dp.include_routers(*get_routers())

    me = await bot.get_me()
    set_bot_username(me.username)
    logger.info("Bot ishga tushdi: @%s | adminlar: %s", me.username, ADMINS or "yo'q")
    if not ADMINS:
        logger.warning("ADMINS bo'sh! .env faylida ADMINS ni to'ldiring.")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()



# ================= RUN =================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
