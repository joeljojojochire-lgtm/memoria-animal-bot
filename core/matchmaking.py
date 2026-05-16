import uuid
import json
import logging
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)

async def add_to_queue(user_id: int, username: str, chat_group_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        # Verificar si ya está en la cola de ESTE grupo específico
        async with db.execute(
            "SELECT 1 FROM queue WHERE user_id = ? AND chat_group_id = ?", 
            (user_id, chat_group_id)
        ) as cursor:
            if await cursor.fetchone():
                # Contamos cuántos hay en total para devolver el número correcto
                async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as c2:
                    r2 = await c2.fetchone()
                    return {"status": "already_in_queue", "current_count": r2[0]}

        # Insertar jugador vinculándolo a este grupo
        await db.execute(
            "INSERT INTO queue (user_id, username, chat_group_id) VALUES (?, ?, ?)",
            (user_id, username, chat_group_id)
        )
        await db.commit()

        # Contar el total acumulado en el grupo
        async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

    if current_count >= 5:
        return await _create_room_from_group(chat_group_id)
        
    return {"status": "queued", "current_count": current_count}


async def force_start_queue(chat_group_id: int) -> dict:
    """Fuerza el inicio del juego con los usuarios acumulados en este grupo específico."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

    if current_count < 2:
        return {"status": "not_enough_players", "current_count": current_count}

    return await _create_room_from_group(chat_group_id)


async def _create_room_from_group(chat_group_id: int) -> dict:
    room_id = str(uuid.uuid4())[:8].upper()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Extraer los usuarios en espera de este grupo
        async with db.execute("SELECT user_id, username FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            rows = await cursor.fetchall()
            
        players = [{"user_id": r[0], "username": r[1]} for r in rows]
        player_ids = [p["user_id"] for p in players]

        # Insertar la sala en la estructura original compatible con tu game_manager
        await db.execute("""
            INSERT INTO rooms (room_id, state, players_count, players, alive) 
            VALUES (?, 'waiting', ?, ?, ?)
        """, (room_id, len(players), json.dumps(players), json.dumps(player_ids)))
        
        # Limpiar la cola de este grupo únicamente
        await db.execute("DELETE FROM queue WHERE chat_group_id = ?", (chat_group_id,))
        await db.commit()

    logger.info(f"🎮 Sala por grupo {room_id} CREADA con {len(players)} jugadores.")
    return {
        "room_id": room_id,
        "players_count": len(players)
    }