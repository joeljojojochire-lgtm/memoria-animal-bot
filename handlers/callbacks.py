import logging
import aiosqlite
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_PATH
from services.asset_service import ASSETS, EMOJIS

logger = logging.getLogger(__name__)

# Diccionario global para controlar los estados en memoria de los jugadores activos
PLAYER_STATES = {}

def get_state_key(room_id: str, user_id: int) -> str:
    return f"{room_id}_{user_id}"

async def handle_animal_callback(bot, call):
    # Formato de data esperado: game_ROOMID_ANIMAL_LEVEL_CLICKINDEX
    data_parts = call.data.split("_")
    if len(data_parts) < 5:
        return

    room_id = data_parts[1]
    animal_pulsado = data_parts[2]
    level = int(data_parts[3])
    
    user_id = call.from_user.id
    state_key = get_state_key(room_id, user_id)

    # 🚫 Si el jugador ya no está en el estado activo (porque ya perdió o se acabó el tiempo)
    if state_key not in PLAYER_STATES:
        await bot.answer_callback_query(call.id, "⚠️ Ya no estás activo en esta ronda o tu tiempo expiró.")
        try:
            await bot.edit_message_reply_markup(chat_id=user_id, message_id=call.message.message_id, reply_markup=None)
        except: pass
        return

    state = PLAYER_STATES[state_key]
    sequence = state["sequence"]
    current_click = state["clicks"]

    # 🛑 VERIFICACIÓN: ¿El animal que pulsó coincide con la secuencia correcta en esa posición?
    if animal_pulsado != sequence[current_click]:
        # ❌ ¡FALLÓ EL PATRÓN! Proceso de eliminación inmediata
        del PLAYER_STATES[state_key]  # Lo sacamos de la memoria para que no pueda interactuar más
        
        await bot.answer_callback_query(call.id, "❌ ¡Te has equivocado de animal!", show_alert=True)
        
        # Le quitamos los botones del DM y le mostramos que perdió
        try:
            await bot.edit_message_text(
                f"☠️ <b>¡Patrón Incorrecto!</b>\nTe equivocaste en el paso {current_click + 1}.\nHas sido eliminado de la partida.",
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=None
            )
            await bot.send_photo(user_id, photo=ASSETS["SAPO_DERROTA"], caption="Has sido eliminado.")
        except Exception as e:
            logger.error(f"Error modificando DM por fallo: {e}")

        # Actualizamos su estado a 'dead' en la base de datos
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE room_players SET status = 'dead' WHERE room_id = ? AND user_id = ?", (room_id, user_id))
            await db.commit()
            
            # Avisamos al grupo que este jugador mordió el polvo
            username = call.from_user.username or call.from_user.first_name
            await bot.send_message(state["chat_group_id"], f"💀 @{username} se equivocó en el patrón y fue eliminado.")

        # Importamos el game_manager localmente para evitar dependencias circulares y checar transiciones
        import core.game_manager as gm
        await gm.check_room_transitions(bot, room_id, state["chat_group_id"], level)
        return

    # 🪙 Si el clic fue correcto, avanzamos en la secuencia
    state["clicks"] += 1
    await bot.answer_callback_query(call.id, f"✅ ¡Correcto! ({state['clicks']}/{len(sequence)})")

    # Si completó todos los clics de la secuencia con éxito
    if state["clicks"] == len(sequence):
        del PLAYER_STATES[state_key]  # Quitamos su estado de juego porque ya terminó este nivel con éxito
        
        try:
            await bot.edit_message_text(
                f"🎉 <b>¡Nivel Completado!</b>\nHas recordado la secuencia a la perfección. Esperando a los demás jugadores...",
                chat_id=user_id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except: pass

        # Verificamos si todos terminaron para pasar de nivel o declarar ganador
        import core.game_manager as gm
        await gm.check_room_transitions(bot, room_id, state["chat_group_id"], level)