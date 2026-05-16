import os
from dotenv import load_dotenv

# 1. Cargar las variables del archivo .env local
load_dotenv()

# 2. Extraer las variables de forma directa sin llamarse a sí mismo
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "memoria_animal.db")

# 3. Control de seguridad
if not BOT_TOKEN:
    raise ValueError("❌ ERROR CRÍTICO: No se encontró 'BOT_TOKEN' en el archivo .env o en las variables de entorno.")