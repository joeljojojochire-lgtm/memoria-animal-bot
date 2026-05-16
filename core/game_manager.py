async def start_game_session(bot, room_id: str, chat_group_id: int):
    """
    Orquestador definitivo adaptado a tu main.py.
    Obtiene los jugadores de la base de datos de forma segura e inicia la partida.
    """
    try:
        # 1. En la primera ronda siempre iniciamos en el Nivel 1
        level = 1
        
        # 2. Obtenemos los IDs de los jugadores vinculados a esta sala desde la DB
        import aiosqlite
        players = []
        async with aiosqlite.connect("database.db") as db: # Asegúrate de que use el nombre correcto de tu DB
            async with db.execute("SELECT user_id FROM room_players WHERE room_id = ?", (room_id,)) as cursor:
                async for row in cursor:
                    players.append(row[0])

        if not players:
            logger.error(f"❌ No se encontraron jugadores para la sala {room_id}")
            return

        # 3. Generamos una secuencia inicial con 3 animales aleatorios para el Nivel 1
        import random
        from services.asset_service import ASSETS
        lista_animales = list(ASSETS.keys())
        sequence = [random.choice(lista_animales) for _ in range(3)]
        
        logger.info(f"🎮 Iniciando juego en sala {room_id}. Enviando DMs a {len(players)} jugadores.")

        # 4. Le enviamos la secuencia visual con emojis a cada jugador participante
        for player_id in players:
            await send_visual_sequence_dm(bot, int(player_id), room_id, level, sequence, chat_group_id)
            
    except Exception as e:
        logger.error(f"Error al iniciar sesión de juego en sala {room_id}: {e}")