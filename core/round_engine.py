import random
import logging
from services.asset_service import ASSETS

logger = logging.getLogger(__name__)

# Lista base de animales reales disponibles en los activos estáticos
ANIMALES_VALIDOS = ["POLLO", "PERRO", "GATO", "VACA", "CERDO", "LEON", "MONO"]

def generate_round_sequence(level: int) -> list:
    """
    Genera la secuencia limpia de strings de animales que el usuario deberá memorizar.
    Permite elementos repetidos para potenciar el reto de memoria visual pura. (Fase 3.1)
    """
    if level == 1:
        length = 5   # Nivel 1: 5 imágenes (Fase 3.1)
    elif level == 2:
        length = 7   # Nivel 2: 7 imágenes
    else:
        length = 10  # Nivel 3: 10 imágenes (Colapso Mental)

    # Generamos una lista aleatoria permitiendo duplicados en la secuencia
    sequence = [random.choice(ANIMALES_VALIDOS) for _ in range(length)]
    logger.info(f"⚙️ Secuencia generada para Nivel {level}: {', '.join(sequence)}")
    return sequence

def build_keyboard_layout(level: int) -> list:
    """
    Diseña la estructura del teclado de respuestas.
    A partir del Nivel 2 inyecta al 'SAPO IMPOSTOR' como botón trampa. (Fase 7.1)
    """
    # Clonamos la lista base para no mutar la original global
    buttons = ANIMALES_VALIDOS.copy()
    
    # Regla del Sapo Impostor (Fase 7.1): Aparece desde nivel 2 en adelante
    if level >= 2:
        buttons.append("SAPO")
        
    # Barajado inicial (Fase 3.2 / 4.2)
    # En el nivel 2 cambia una vez al inicio. En el nivel 3 cambiará por cada click.
    random.shuffle(buttons)
    return buttons

def get_level_duration(level: int) -> int:
    """Retorna los límites de tiempo estrictos por nivel para responder (Fase 8.1)"""
    if level == 1:
        return 10  # 10 segundos en el nivel de introducción
    return 7       # 7 segundos bajo presión extrema en niveles 2 y 3