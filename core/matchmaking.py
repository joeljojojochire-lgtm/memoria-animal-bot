import uuid
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
                async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as c2:
                    r2 = await c2.fetchone()
                    return {"status": "already_in_queue", "current_count": r2[0]}

        # Insertar jugador en la cola vinculándolo al grupo actual
        await db.execute(
            "INSERT INTO queue (user_id, username, chat_group_id) VALUES (?, ?, ?)",
            (user_id, username, chat_group_id)
        )
        await db.commit()

        # Contar cuántos jugadores reales van acumulados en este grupo
        async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

    # Si se alcanzan los 5 jugadores, la sala se crea automáticamente
    if current_count >= 5:
        return await _create_room_from_group(chat_group_id)
        
    return {"status": "queued", "current_count": current_count}


async def force_start_queue(chat_group_id: int) -> dict:
    """Fuerza el inicio con los jugadores que estén en la cola de este grupo."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

    if current_count < 2:
        return {"status": "not_enough_players", "current_count": current_count}

    # 🔧 CORRECCIÓN CRÍTICA: Retornamos el diccionario completo con el estado correcto
    return await _create_room_from_group(chat_group_id)


async def _create_room_from_group(chat_group_id: int) -> dict:
    room_id = str(uuid.uuid4())[:8].upper()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Extraer a todos los miembros listos de este grupo
        async with db.execute("SELECT user_id, username FROM queue WHERE chat_group_id = ?", (chat_group_id,)) as cursor:
            players = await cursor.fetchall()

        # 1. Crear la sala unificada en tu tabla relacional real
        await db.execute(
            "INSERT INTO rooms (room_id, status, current_level) VALUES (?, 'playing', 1)", 
            (room_id,)
        )
        
        # 2. Registrar a todos los miembros en la tabla secundaria apuntando a la misma sala
        for p_id, p_name in players:
            await db.execute("""
                INSERT INTO room_players (room_id, user_id, username, status) 
                VALUES (?, ?, ?, 'alive')
            """, (room_id, p_id, p_name))
        
        # 3. Vaciar la cola de espera de este grupo únicamente
        await db.execute("DELETE FROM queue WHERE chat_group_id = ?", (chat_group_id,))
        await db.commit()

    logger.info(f"🎮 Sala unificada {room_id} creada mediante disparador para el grupo {chat_group_id} con {len(players)} jugadores.")
    
    # Retorno unificado que main.py sabe procesar sin romperse
    return {
        "status": "room_created",
        "room": {
            "room_id": room_id,
            "players_count": len(players)
        }
    }