import aiosqlite
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    """Inicializa la base de datos creando las tablas necesarias si no existen."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Tabla de Usuarios/Estadísticas
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                wins INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            )
        """)
        # Tabla de Salas de Juego activas
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                state TEXT DEFAULT 'waiting',
                players_count INTEGER,
                players TEXT,
                alive TEXT
            )
        """)
        await db.commit()
    logger.info("Tables 'users' and 'rooms' checked/created successfully.")

async def create_user(user_id: int, username: str):
    """Registra un usuario nuevo en la base de datos o actualiza su username si ya existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username) 
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        await db.commit()