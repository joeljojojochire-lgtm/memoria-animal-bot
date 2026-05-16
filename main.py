import asyncio
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN
from db.database import init_db, create_user
from core.matchmaking import add_to_queue, force_start_queue  # ← Importamos ambas funciones
from core.game_manager import start_game_session  
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
        "Añádeme a un grupo de Telegram y envía <b>/join</b> allí para empezar."
    )

@bot.message_handler(commands=['join'])
async def command_join(message):
    # 🚫 Restricción: Impedir el juego en la cola global de DMs privados si buscas separar por grupos
    if message.chat.type not in ['group', 'supergroup']:
        await bot.reply_to(message, "❌ Este comando solo funciona dentro de grupos de Telegram.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    chat_group_id = message.chat.id  

    await create_user(user_id, username)
    
    # Pasamos el chat_group_id para que no se mezclen los grupos
    result = await add_to_queue(user_id, username, chat_group_id)
    
    if result["status"] == "already_in_queue":
        await bot.reply_to(message, f"⚠️ Ya estás en la lista de espera de este grupo, @{username}.")
        return

    bot_info = await bot.get_me()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="📥 Ir a mis DMs", url=f"t.me/{bot_info.username}"))

    if result["status"] == "queued":
        await bot.send_message(
            chat_group_id,
            f"✅ @{username} se ha unido a la partida.\n"
            f"⏳ Buscando rivales... [<b>{result['current_count']}/5</b>]\n\n"
            f"<i>💡 Si no quieren esperar, envíen <b>/go</b> para iniciar (Mínimo 2 jugadores).</i>",
            reply_markup=markup
        )
    elif result["status"] == "room_created":
        room = result["room"]
        await bot.send_message(
            chat_group_id,
            f"🔥 <b>¡SALA COMPLETADA! (5/5)</b>\nIniciando juego automáticamente...\n\n👉 ¡Revisen sus DMs!",
            reply_markup=markup
        )
        asyncio.create_task(start_game_session(bot, room["room_id"], chat_group_id))

# =========================================================
# COMANDO /GO: INICIAR CON LOS QUE ESTÉN (MÍNIMO 2)
# =========================================================
@bot.message_handler(commands=['go'])
async def command_go(message):
    if message.chat.type not in ['group', 'supergroup']:
        return

    chat_group_id = message.chat.id
    result = await force_start_queue(chat_group_id)

    if result["status"] == "not_enough_players":
        await bot.reply_to(
            message, 
            f"⚠️ No hay suficientes jugadores en este grupo para iniciar.\n"
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
            f"⚡ <b>¡Partida forzada con /go!</b>\nCreando sala con los {room['players_count']} jugadores en espera.\n\n"
            f"👉 ¡Vayan corriendo a sus DMs!",
            reply_markup=markup
        )
        asyncio.create_task(start_game_session(bot, room["room_id"], chat_group_id))

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
async def callback_game_router(call):
    await handle_animal_callback(bot, call)

@bot.message_handler(content_types=['photo'])
async def capturar_id_imagen(message):
    file_id = message.photo[-1].file_id
    await bot.reply_to(message, f"🖼️ <b>ID de Imagen:</b>\n<code>{file_id}</code>", parse_mode="HTML")

async def main():
    await init_db()
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import core.game_manager as gm
    gm.scheduler = AsyncIOScheduler()
    gm.scheduler.start()
    
    # 🌍 Servidor HTTP simulado para Render Gratis
    import os
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class FakeWebhookServer(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot OK")
        def log_message(self, format, *args): return

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), FakeWebhookServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    logger.info("Bot escuchando de forma segura...")
    await bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    asyncio.run(main())