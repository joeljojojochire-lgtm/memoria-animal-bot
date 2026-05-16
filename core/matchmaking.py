import asyncio
import json
import logging
import uuid
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)

# La cola global en memoria
global_queue = []

# 🔐 CANDADO DE SEGURIDAD: Evita que dos personas que pulsen "join" a la vez pisen la cola o dupliquen salas
queue_lock = asyncio.Lock()

async def add_to_queue(user_id: int, username: str) -> dict:
    # Usamos el candado para procesar los registros en fila india
    async with queue_lock:
        # 1. Verificar si el jugador ya está en la cola
        if any(player['user_id'] == user_id for player in global_queue):
            return {"status": "already_in_queue", "current_count": len(global_queue)}
       
        # 2. Añadir al jugador a la lista
        global_queue.append({"user_id": user_id, "username": username})
        logger.info(f"👤 @{username} [{user_id}] entró a la cola. Total: {len(global_queue)}")
        
        # 3. Si se alcanza el límite de 5 jugadores, se crea la sala automáticamente
        if len(global_queue) >= 5:
            players_to_room = global_queue[:5]
            del global_queue[:5] # Limpiamos los 5 que ya entraron de la cola global
            
            room_data = await _create_room_in_db(players_to_room)
            return {"status": "room_created", "room": room_data}
            
        # Si aún no llega a 5, se queda esperando en la cola
        return {"status": "queued", "current_count": len(global_queue)}

async def force_start_queue() -> dict:
    """Fuerza el inicio de la partida con los jugadores que estén acumulados (mínimo 2)"""
    async with queue_lock:
        if len(global_queue) < 2:
            return {"status": "not_enough_players", "current_count": len(global_queue)}
            
        # Tomamos a todos los que estén actualmente esperando
        players_to_room = list(global_queue)
        global_queue.clear() # Vaciamos por completo la cola global
        
        room_data = await _create_room_in_db(players_to_room)
        return {"status": "room_created", "room": room_data}

async def remove_from_queue(user_id: int) -> dict:
    """Permite a un jugador salirse de la cola voluntariamente antes de empezar"""
    async with queue_lock:
        for player in global_queue:
            if player['user_id'] == user_id:
                global_queue.remove(player)
                return {"status": "removed", "current_count": len(global_queue)}
        return {"status": "not_in_queue", "current_count": len(global_queue)}

async def _create_room_in_db(players: list) -> dict:
    """Función interna que registra la sala de forma estructurada en la base de datos SQLite"""
    room_id = str(uuid.uuid4())[:8].upper()
    player_ids = [p['user_id'] for p in players]
    
    players_json = json.dumps(players)
    alive_json = json.dumps(player_ids)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rooms (room_id, state, players_count, players, alive) 
            VALUES (?, 'waiting', ?, ?, ?)
        """, (room_id, len(players), players_json, alive_json))
        await db.commit()
        
    logger.info(f"🎮 Sala {room_id} CREADA con {len(players)} jugadores en la Base de Datos.")
    return {
        "room_id": room_id,
        "players": players,
        "player_ids": player_ids
    }