import aiosqlite
import uuid
import logging

logger = logging.getLogger(__name__)

async def add_to_queue(user_id: int, username: str, chat_group_id: int):
    """Añade un jugador a la cola de un grupo específico."""
    async with aiosqlite.connect("database.db") as db:
        # Verificar si ya está en la cola DE ESTE GRUPO
        async with db.execute(
            "SELECT 1 FROM queue WHERE user_id = ? AND chat_group_id = ?", 
            (user_id, chat_group_id)
        ) as cursor:
            if await cursor.fetchone():
                return {"status": "already_in_queue"}

        # Insertar con el ID del grupo
        await db.execute(
            "INSERT INTO queue (user_id, username, chat_group_id) VALUES (?, ?, ?)",
            (user_id, username, chat_group_id)
        )
        await db.commit()

        # Contar cuántos van EN ESTE GRUPO
        async with db.execute(
            "SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", 
            (chat_group_id,)
        ) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

        # Si se llenó (5 jugadores del mismo grupo)
        if current_count >= 5:
            return await _create_room_from_group_queue(chat_group_id, current_count)

        return {"status": "queued", "current_count": current_count}


async def force_start_queue(chat_group_id: int):
    """Fuerza el inicio de la partida SOLO con los jugadores en espera de ESTE grupo."""
    async with aiosqlite.connect("database.db") as db:
        async with db.execute(
            "SELECT COUNT(*) FROM queue WHERE chat_group_id = ?", 
            (chat_group_id,)
        ) as cursor:
            row = await cursor.fetchone()
            current_count = row[0]

        if current_count < 2:
            return {"status": "not_enough_players", "current_count": current_count}

        return await _create_room_from_group_queue(chat_group_id, current_count)


async def _create_room_from_group_queue(chat_group_id: int, current_count: int):
    """Función interna para pasar los jugadores de la cola del grupo a la sala."""
    room_id = str(uuid.uuid4())[:8].upper()
    
    async with aiosqlite.connect("database.db") as db:
        # Crear la sala
        await db.execute(
            "INSERT INTO rooms (room_id, status, current_level) VALUES (?, 'playing', 1)",
            (room_id,)
        )
        
        # Obtener los jugadores de este grupo
        async with db.execute(
            "SELECT user_id, username FROM queue WHERE chat_group_id = ?", 
            (chat_group_id,)
        ) as cursor:
            players = await cursor.fetchall()
            
        # Pasarlos a la sala
        for player in players:
            p_id, p_name = player
            await db.execute(
                "INSERT INTO room_players (room_id, user_id, username, status) VALUES (?, ?, ?, 'alive')",
                (room_id, p_id, p_name)
            )
            
        # Borrar solo a los de este grupo de la cola
        await db.execute("DELETE FROM queue WHERE chat_group_id = ?", (chat_group_id,))
        await db.commit()
        
    logger.info(f"🎮 Sala {room_id} creada exclusivamente para el grupo {chat_group_id} con {current_count} jugadores.")
    return {
        "status": "room_created",
        "room": {"room_id": room_id, "players_count": current_count}
    }