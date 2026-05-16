import asyncio
import logging
from telebot.async_telebot import AsyncTeleBot
from config import BOT_TOKEN
from db.database import init_db, create_user
from core.matchmaking import add_to_queue
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
        "🧠 <b>¡Bienvenido a Memoria Animal!</b>\nEnvía /join para buscar una partida en tiempo real."
    )

@bot.message_handler(commands=['join'])
async def command_join(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    chat_group_id = message.chat.id  
    
    await create_user(user_id, username)
    result = await add_to_queue(user_id, username)
    
    if result["status"] == "already_in_queue":
        await bot.reply_to(message, f"⚠️ Ya estás en la cola de espera, @{username}. (Buscando: {result['current_count']}/2)")
    elif result["status"] == "queued":
        await bot.reply_to(message, f"⏳ Buscando rivales... [{result['current_count']}/2]\n¡Te avisaré cuando empiece la acción!")
    elif result["status"] == "room_created":
        room = result["room"]
        
        asyncio.create_task(
            start_game_session(bot, room["room_id"], chat_group_id)
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
async def callback_game_router(call):
    await handle_animal_callback(bot, call)

@bot.message_handler(content_types=['photo'])
async def capturar_id_imagen(message):
    file_id = message.photo[-1].file_id
    mensaje_respuesta = (
        "🖼️ <b>¡Imagen recibida!</b>\n\n"
        "Aquí tienes el ID de Telegram para usar in-code:\n"
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
    
    # 🌍 TRUCO PARA RENDER GRATIS: Servidor HTTP simulado en segundo plano
    import os
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class FakeWebhookServer(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Servidor de Bot en ejecucion activa")
        def log_message(self, format, *args): return

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), FakeWebhookServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"🌍 Puerto falso activo en el {port} para Render Free.")

    logger.info("Iniciando bucle de escucha asíncrono del bot...")
    await bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    asyncio.run(main())