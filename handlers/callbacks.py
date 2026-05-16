import json
import logging
import random
import aiosqlite
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DB_PATH
from services.asset_service import EMOJIS
from core.round_engine import build_keyboard_layout

logger = logging.getLogger(__name__)

PLAYER_STATES = {}

def get_state_key(room_id: str, user_id: int) -> str:
    return f"{room_id}_{user_id}"

async def handle_animal_callback(bot, call):
    data_parts = call.data.split("_")
    if len(data_parts) < 5:
        await bot.answer_callback_query(call.id, text="⚠️ Error de sincronización de datos.")
        return

    _, room_id, animal_name, level_str, step_str = data_parts
    user_id = call.from_user.id
    current_level = int(level_str)
    state_key = get_state_key(room_id, user_id)

    if state_key not in PLAYER_STATES:
        await bot.answer_callback_query(call.id, text="❌ Esta ronda ha expirado o ya no estás activo.")
        try:
            await bot.edit_message_reply_markup(chat_id=user_id, message_id=call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    state = PLAYER_STATES[state_key]
    correct_sequence = state["sequence"]
    current_step = state["clicks"]
    chat_group_id = state["chat_group_id"]

    if int(step_str) != current_step:
        await bot.answer_callback_query(call.id)
        return

    # Sapo Impostor (Fase 7.2)
    if animal_name == "SAPO":
        await bot.answer_callback_query(call.id, text="🐸 ¡El Sapo Impostor te ha infectado la mente!")
        await process_elimination(bot, user_id, room_id, call.message.message_id, "Pulsó al Sapo Impostor 🐸", chat_group_id)
        return

    # Validación de Secuencia Visual (Fase 5.1)
    expected_animal = correct_sequence[current_step]
    state["history"].append(animal_name)
    state["clicks"] += 1

    if animal_name != expected_animal:
        await bot.answer_callback_query(call.id, text="💥 ¡Secuencia Incorrecta!")
        await process_elimination(bot, user_id, room_id, call.message.message_id, "Rompió la cadena de memoria", chat_group_id)
        return

    await bot.answer_callback_query(call.id, text=f"Correcto: {EMOJIS[animal_name]}")
    breadcrumbs = " → ".join([EMOJIS[anim] for anim in state["history"]])
    
    if state["clicks"] < len(correct_sequence):
        breadcrumbs += " → ❓"

    # Verificar si completó la ronda con éxito (Fase 5.3 / Fase 10)
    if state["clicks"] == len(correct_sequence):
        # Remover el job de timeout de APScheduler para que no lo mate en el último segundo
        try:
            from core.game_manager import scheduler
            job_id = f"timeout_{room_id}_{user_id}_{current_level}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        except Exception as e:
            logger.error(f"No se pudo remover el job de timeout: {e}")

        # Limpiar su memoria de interacción activa
        del PLAYER_STATES[state_key]

        await bot.edit_message_text(
            text=f"✨ <b>¡RONDA COMPLETADA!</b>\n\nTu registro: {breadcrumbs}\n\nSobreviviste a la presión del Nivel {current_level}. Esperando el dictamen del Narrador...",
            chat_id=user_id,
            message_id=call.message.message_id,
            reply_markup=None
        )
        
        # Evaluar estado de transiciones de sala
        from core.game_manager import check_room_transitions
        await check_room_transitions(bot, room_id, chat_group_id, current_level)
        return

    # Re-generación del Teclado Nivel 3 (Fase 3.2 / 4.2 - Randomización Dinámica)
    if current_level == 3:
        buttons_layout = build_keyboard_layout(level=current_level)
    else:
        buttons_layout = state["layout"]

    markup = InlineKeyboardMarkup(row_width=4)
    btn_objects = [
        InlineKeyboardButton(
            text=EMOJIS.get(name, name), 
            callback_data=f"game_{room_id}_{name}_{current_level}_{state['clicks']}"
        ) for name in buttons_layout
    ]
    markup.add(*btn_objects)

    await bot.edit_message_text(
        text=f"🧠 <b>PROGRESO DE MEMORIA - NIVEL {current_level}</b>\n\nReconstruye el patrón en orden:\n<code>{breadcrumbs}</code>",
        chat_id=user_id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

async def process_elimination(bot, user_id: int, room_id: str, message_id: int, reason: str, chat_group_id: int):
    """Ejecuta la purga visual e impacta la DB (Fase 5.2 y Fase 10)"""
    state_key = get_state_key(room_id, user_id)
    current_level = 1
    if state_key in PLAYER_STATES:
        current_level = PLAYER_STATES[state_key]["level"]
        del PLAYER_STATES[state_key]

    # Remover el job de timeout activo
    try:
        from core.game_manager import scheduler
        job_id = f"timeout_{room_id}_{user_id}_{current_level}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception:
        pass

    await bot.edit_message_text(
        text=f"❌ <b>¡ELIMINADO!</b>\n\nMotivo: <i>{reason}</i>.\nTu mente colapsó bajo la presión. Regresa al grupo para ver el destino de la partida. 💀",
        chat_id=user_id,
        message_id=message_id,
        reply_markup=None
    )
    
    # Restar de los supervivientes en SQLite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT players, alive FROM rooms WHERE room_id = ?", (room_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                players = json.loads(row[0])
                alive_ids = json.loads(row[1])
                
                if user_id in alive_ids:
                    alive_ids.remove(user_id)
                    
                await db.execute("UPDATE rooms SET alive = ? WHERE room_id = ?", (json.dumps(alive_ids), room_id))
                await db.commit()
                
                username_fallecido = next((p['username'] for p in players if p['user_id'] == user_id), "Jugador")
                
                # Reportar baja inmediata en el log de grupo
                await bot.send_message(
                    chat_group_id,
                    f"💀 <b>¡MALA DECISIÓN!</b>\n@{username_fallecido} cayó en el Nivel {current_level} ({reason}).\n"
                    f"Quedan {len(alive_ids)} jugadores en batalla."
                )
    
    # Validar transiciones por si era el último que faltaba por responder
    from core.game_manager import check_room_transitions
    await check_room_transitions(bot, room_id, chat_group_id, current_level)