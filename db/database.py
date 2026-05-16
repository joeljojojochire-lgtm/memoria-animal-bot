import aiosqlite
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    """Inicializa la base de datos creando las tablas necesarias si no existen."""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Tabla de Usuarios/Estadísticas
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                wins INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            )
        """)
        
        # 2. Nueva Tabla de Cola de Espera (Soporta múltiples grupos independientes)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                user_id INTEGER,
                username TEXT,
                chat_group_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_group_id)
            )
        """)
        
        # 3. Tabla de Salas de Juego activas
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'playing',
                current_level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 4. Nueva Tabla de Jugadores por Sala (Para controlar quién sigue vivo en el juego)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS room_players (
                room_id TEXT,
                user_id INTEGER,
                username TEXT,
                status TEXT DEFAULT 'alive', -- 'alive' o 'dead' (eliminado)
                PRIMARY KEY (room_id, user_id),
                FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE
            )
        """)
        
        await db.commit()
    logger.info("Base de datos estructurada e inicializada con éxito (Tablas: users, queue, rooms, room_players).")

async def create_user(user_id: int, username: str):
    """Registra un usuario nuevo en la base de datos o actualiza su username si ya existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username) 
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        await db.commit()