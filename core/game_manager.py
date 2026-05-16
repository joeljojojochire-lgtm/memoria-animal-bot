import asyncio
import json
import logging
import random
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

from config import DB_PATH
from services.asset_service import ASSETS, EMOJIS
from core.round_engine import generate_round_sequence, build_keyboard_layout, get_level_duration
from handlers.callbacks import PLAYER_STATES, get_state_key

logger = logging.getLogger(__name__)
scheduler = None

async def start_game_session(bot, room_id: str, chat_group_id: int):
    # Espera corta de cortesía para el lobby
    await asyncio.sleep(3) 

    players = []
    async with aiosqlite.connect(DB_PATH) as db:
        # 🔧 CORRECCIÓN: Usamos 'status' en lugar de 'state' para que coincida con tu DB
        await db.execute("UPDATE rooms SET status = 'playing' WHERE room_id = ?", (room_id,))
        await db.commit()
        
        # Obtenemos los jugadores reales de la tabla secundaria que tú creaste
        async with db.execute("SELECT user_id, username FROM room_players WHERE room_id = ?", (room_id,)) as cursor:
            async for row in cursor:
                players.append({"user_id": row[0], "username": row[1]})

    if not players:
        logger.error(f"❌ No se encontraron jugadores en room_players para la sala {room_id}")
        return

    menciones = ", ".join([f"@{p['username']}" for p in players])
    alive_ids = [p["user_id"] for p in players]
    
    try:
        await bot.send_photo(
            chat_group_id,
            photo=ASSETS["SAPO_LOBBY"],
            caption=f"🏁 <b>SALA #{room_id} INICIADA</b>\nJugadores: {menciones}\n\n¡Corran a sus DMs! 🛡️"
        )
    except Exception as e:
        logger.error(f"Error al enviar foto de lobby al grupo: {e}")
        await bot.send_message(chat_group_id, f"🏁 <b>SALA #{room_id} INICIADA</b>\nJugadores: {menciones}\n\n¡Corran a sus DMs! 🛡️")

    await execute_round(bot, room_id, 1, alive_ids, chat_group_id)

async def execute_round(bot, room_id: str, level: int, alive_ids: list, chat_group_id: int):
    num_items = 3 if level <= 3 else 3 + (level - 3)
    sequence = generate_round_sequence(level)[:num_items]
    
    await bot.send_message(
        chat_group_id, 
        f"📢 <b>RONDA {level}</b> ⏱️\nSecuencia de <b>{num_items} imágenes</b>. ¡Atentos!"
    )

    tasks = [send_visual_sequence_dm(bot, uid, room_id, level, sequence, chat_group_id) for uid in alive_ids]
    await asyncio.gather(*tasks)

async def send_visual_sequence_dm(bot, user_id: int, room_id: str, level: int, sequence: list, chat_group_id: int):
    try:
        init_msg = await bot.send_message(user_id, f"🚀 <b>NIVEL {level}</b>\nPrepárate para memorizar...")
        for i in range(5, 0, -1):
            await asyncio.sleep(1.8)
            try: await bot.edit_message_text(f"🚀 Apareciendo en: <b>{i}</b>...", chat_id=user_id, message_id=init_msg.message_id)
            except: pass
        await asyncio.sleep(1)
        await bot.delete_message(user_id, init_msg.message_id)

        # 🖼️ Envío de imágenes con respaldo de emoji en el texto
        for idx, animal in enumerate(sequence):
            emoji_respaldo = EMOJIS.get(animal, "❓")
            photo_msg = await bot.send_photo(
                user_id, 
                photo=random.choice(ASSETS[animal]), 
                caption=f"🖼️ Imagen {idx+1}/{len(sequence)}\nPista visual: {emoji_respaldo}"
            )
            exposure = 5.0 if idx == 0 else 3.5
            await asyncio.sleep(exposure)
            await bot.delete_message(user_id, photo_msg.message_id)
            await asyncio.sleep(0.5)

        layout = build_keyboard_layout(level)
        state_key = get_state_key(room_id, user_id)
        PLAYER_STATES[state_key] = {"clicks": 0, "history": [], "sequence": sequence, "layout": layout, "level": level, "chat_group_id": chat_group_id}

        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(text=EMOJIS.get(n, n), callback_data=f"game_{room_id}_{n}_{level}_0") for n in layout])
        
        await bot.send_message(user_id, f"🧠 <b>NIVEL {level}</b>\n¿Cuál era el patrón?", reply_markup=markup)

        duration = get_level_duration(level) + len(sequence)
        job_id = f"timeout_{room_id}_{user_id}_{level}"
        scheduler.add_job(process_timeout_elimination, 'date', run_date=None, args=[bot, user_id, room_id, job_id], id=job_id, seconds=duration)
        
    except Exception as e:
        logger.error(f"Error enviando secuencia al DM del usuario {user_id}: {e}")

async def process_timeout_elimination(bot, user_id: int, room_id: str, job_id: str):
    state_key = get_state_key(room_id, user_id)
    if state_key not in PLAYER_STATES: return
    state = PLAYER_STATES[state_key]
    chat_group_id, level = state["chat_group_id"], state["level"]
    del PLAYER_STATES[state_key]
    
    try: await bot.send_photo(user_id, photo=ASSETS["SAPO_DERROTA"], caption="⏱️ <b>¡TIEMPO AGOTADO!</b>")
    except: pass
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE room_players SET status = 'dead' WHERE room_id = ? AND user_id = ?", (room_id, user_id))
        await db.commit()
        
        async with db.execute("SELECT username FROM room_players WHERE room_id = ? AND user_id = ?", (room_id, user_id)) as cursor:
            row = await cursor.fetchone()
            user_nick = row[0] if row else "Jugador"
            await bot.send_message(chat_group_id, f"💀 @{user_nick} eliminado por tiempo.")

    await check_room_transitions(bot, room_id, chat_group_id, level)

async def check_room_transitions(bot, room_id: str, chat_group_id: int, current_level: int):
    alive_players = []
    all_players = []
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, status FROM room_players WHERE room_id = ?", (room_id,)) as cursor:
            async for row in cursor:
                all_players.append({"user_id": row[0], "username": row[1]})
                if row[2] == 'alive':
                    alive_players.append(row[0])

    if any(get_state_key(room_id, uid) in PLAYER_STATES for uid in alive_players): return

    if len(alive_players) == 0:
        await bot.send_photo(chat_group_id, photo=ASSETS["SAPO_DERROTA"], caption="☠️ <b>PARTIDA TERMINADA</b>\nNadie sobrevivió.")
        await finalizar_db(room_id, all_players)
    elif len(alive_players) == 1:
        ganador_id = alive_players[0]
        user_ganador = next((p['username'] for p in all_players if p['user_id'] == ganador_id), "Héroe")
        await bot.send_photo(chat_group_id, photo=ASSETS["SAPO_VICTORIA"], caption=f"👑 ¡@{user_ganador} GANA LA PARTIDA!")
        try: await bot.send_photo(ganador_id, photo=ASSETS["SAPO_VICTORIA"], caption="🏆 ¡ERES EL CAMPEÓN!")
        except: pass
        await finalizar_db(room_id, all_players, ganador_id)
    else:
        await bot.send_message(chat_group_id, f"🔄 Siguiente nivel en 5 seg...")
        await asyncio.sleep(5)
        # 🔧 CORRECCIÓN: Actualizamos el nivel actual en la tabla 'rooms' usando su columna real 'current_level'
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE rooms SET current_level = ? WHERE room_id = ?", (current_level + 1, room_id))
            await db.commit()
        await execute_round(bot, room_id, current_level + 1, alive_players, chat_group_id)

async def finalizar_db(room_id, players, ganador_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE rooms SET status = 'finished' WHERE room_id = ?", (room_id,))
        for p in players:
            stat = "wins = wins + 1, games_played = games_played + 1" if p['user_id'] == ganador_id else "games_played = games_played + 1"
            await db.execute(f"UPDATE users SET {stat} WHERE user_id = ?", (p['user_id'],))
        await db.commit()