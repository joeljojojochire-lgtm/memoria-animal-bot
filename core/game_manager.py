async def send_visual_sequence_dm(bot, user_id: int, room_id: str, level: int, sequence: list, chat_group_id: int):
    try:
        # ⏱️ Preparación rápida original (1 segundo por número)
        init_msg = await bot.send_message(user_id, f"🚀 <b>NIVEL {level}</b>\nPrepárate para memorizar...")
        for i in range(5, 0, -1):
            await asyncio.sleep(1.0)
            try: 
                await bot.edit_message_text(f"🚀 Apareciendo en: <b>{i}</b>...", chat_id=user_id, message_id=init_msg.message_id)
            except Exception:
                pass
        await asyncio.sleep(0.5)
        await bot.delete_message(user_id, init_msg.message_id)

        # --- 🖼️ ENVÍO DE IMÁGENES CON EMOJI DE RESPALDO (MALA CONEXIÓN) ---
        for idx, animal in enumerate(sequence):
            # 🔍 Buscamos el emoji en tu diccionario EMOJIS (si no existe, ponemos una huella 🐾)
            animal_emoji = EMOJIS.get(animal, "🐾")
            
            photo_msg = await bot.send_photo(
                user_id, 
                photo=random.choice(ASSETS[animal]), 
                # El texto que salva la partida si la imagen no carga por mal internet
                caption=f"🖼️ Imagen {idx+1}/{len(sequence)}\n\n"
                        f"👉 <b>{animal_emoji} {animal}</b>"
            )
            
            # ⚡ Tiempos rápidos originales intactos para no ralentizar el juego
            if idx == 0:
                exposure = 5.0  # 5 segundos completos para la primera foto
            else:
                exposure = 3.5  # 3.5 segundos para las siguientes
                
            await asyncio.sleep(exposure)
            await bot.delete_message(user_id, photo_msg.message_id)
            await asyncio.sleep(0.1) # Micro-pausa técnica de red rápida

        # Lógica de teclado
        layout = build_keyboard_layout(level)
        state_key = get_state_key(room_id, user_id)
        PLAYER_STATES[state_key] = {"clicks": 0, "history": [], "sequence": sequence, "layout": layout, "level": level, "chat_group_id": chat_group_id}

        markup = InlineKeyboardMarkup(row_width=4)
        markup.add(*[InlineKeyboardButton(text=EMOJIS.get(n, n), callback_data=f"game_{room_id}_{n}_{level}_0") for n in layout])
        
        await bot.send_message(user_id, f"🧠 <b>NIVEL {level}</b>\n¿Cuál era el patrón?", reply_markup=markup)

        # Calculamos la cantidad de imágenes para este nivel específico
        if level <= 3:
            num_items = 3
        else:
            num_items = 3 + (level - 3)
            
        # Timeout dinámico basado en la cantidad de imágenes
        duration = get_level_duration(level) + num_items
        
        # 🔧 CORRECCIÓN CRÍTICA: Cambiado 'date' por 'interval' para aceptar los segundos sin reventar
        job_id = f"timeout_{room_id}_{user_id}_{level}"
        scheduler.add_job(
            process_timeout_elimination, 
            'interval', 
            seconds=duration, 
            args=[bot, user_id, room_id, 0, job_id], 
            id=job_id
        )
        
    except Exception as e:
        logger.error(f"Error DM {user_id}: {e}")