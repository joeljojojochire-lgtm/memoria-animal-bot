import asyncio
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN
from db.database import init_db, create_user
from core.matchmaking import add_to_queue, force_start_queue  # ← Importamos la función de forzado
from core.game_manager import start_game_session  # ← Importamos el orquestador temporal
from handlers.callbacks import handle_animal_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = AsyncTeleBot(BOT_TOKEN, parse_mode="HTML")

@bot.message_handler(commands=['start'])
async def command_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await create_user(user_id, username)
    await bot.reply_to(
        message, 
        "🧠 <b>¡Bienvenido a Memoria Animal!</b>\n\n"
        "👥 Este juego está diseñado para jugarse en grupos.\n"
        "Añádeme a un grupo de Telegram y envía <b>/join</b> allí para empezar a competir."
    )

@bot.message_handler(commands=['join'])
async def command_join(message):
    # 🚫 RESTRICCIÓN: Impedir que se unan desde chats privados
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(
            message, 
            "❌ <b>¡Acceso denegado!</b> Este comando solo funciona dentro de grupos.\n"
            "Por favor, agrégame a un grupo para jugar con tus amigos."
        )
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    chat_group_id = message.chat.id  # Capturar el ID del grupo emisor

    await create_user(user_id, username)
    result = await add_to_queue(user_id, username)
    
    if result["status"] == "already_in_queue":
        await bot.reply_to(message, f"⚠️ Ya estás en la cola de espera, @{username}.")
        return

    # Generamos el enlace directo dinámico hacia el DM del propio bot
    bot_info = await bot.get_me()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="📥 Ir a mis DMs", url=f"t.me/{bot_info.username}"))

    if result["status"] == "queued":
        await bot.send_message(
            chat_group_id,
            f"✅ @{username} se ha unido a la partida.\n"
            f"⏳ Buscando rivales... [<b>{result['current_count']}/5</b>]\n\n"
            f"<i>💡 Si no quieren esperar a los 5, alguien puede enviar <b>/go</b> (Mínimo 2).</i>\n"
            f"👇 ¡Asegúrate de iniciar el chat privado del bot abajo!",
            reply_markup=markup
        )
        
    elif result["status"] == "room_created":
        room = result["room"]
        await bot.send_message(
            chat_group_id,
            f"🔥 <b>¡SALA COMPLETADA! (5/5)</b>\nIniciando la sesión de juego automáticamente...\n\n"
            f"👉 ¡Vayan todos corriendo a sus DMs!",
            reply_markup=markup
        )
        
        # Disparar de inmediato la sesión del juego en segundo plano sin congelar el bot
        asyncio.create_task(
            start_game_session(bot, room["room_id"], chat_group_id)
        )

# =========================================================
# NUEVO COMANDO /GO: FORZAR INICIO DE PARTIDA (MÍNIMO 2)
# =========================================================
@bot.message_handler(commands=['go'])
async def command_go(message):
    # 🚫 RESTRICCIÓN: Solo permitir en grupos
    if message.chat.type not in ['group', 'supergroup']:
        return

    chat_group_id = message.chat.id

    # Forzamos la inicialización de la cola acumulada actual
    result = await force_start_queue()

    if result["status"] == "not_enough_players":
        await bot.reply_to(
            message, 
            f"⚠️ No hay suficientes jugadores para forzar el inicio.\n"
            f"Se necesita un mínimo de <b>2 personas</b> (actualmente hay {result['current_count']})."
        )
        return

    if result["status"] == "room_created":
        room = result["room"]
        bot_info = await bot.get_me()
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="📥 Ir a mis DMs", url=f"t.me/{bot_info.username}"))

        await bot.send_message(
            chat_group_id,
            f"⚡ <b>¡Partida iniciada con /go!</b>\nCreando sala con los jugadores en espera.\n\n"
            f"👉 Corran a sus DMs para empezar a memorizar.",
            reply_markup=markup
        )
        
        # Ejecutamos la sesión de juego en segundo plano de inmediato
        asyncio.create_task(
            start_game_session(bot, room["room_id"], chat_group_id)
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
async def callback_game_router(call):
    await handle_animal_callback(bot, call)

# =========================================================
# FUNCIÓN EXTRACTORA DE FILE_ID
# =========================================================
@bot.message_handler(content_types=['photo'])
async def capturar_id_imagen(message):
    """Detecta imágenes enviadas al bot y extrae su ID único de Telegram."""
    file_id = message.photo[-1].file_id
    
    mensaje_respuesta = (
        "🖼️ <b>¡Imagen recibida!</b>\n\n"
        "Aquí tienes el ID de Telegram para usar en tu código:\n"
        f"<code>{file_id}</code>"
    )
    await bot.reply_to(message, mensaje_respuesta, parse_mode="HTML")

async def main():
    logger.info("Inicializando Base de Datos SQLite...")
    await init_db()
    
    # Arrancar APScheduler compartiendo de forma segura el bucle asíncrono del bot
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import core.game_manager as gm
    
    gm.scheduler = AsyncIOScheduler()
    gm.scheduler.start()
    logger.info("Planificador APScheduler iniciado con éxito.")
    
    logger.info("Iniciando bucle de escucha asíncrono del bot...")
    await bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    asyncio.run(main())