import logging
import asyncio
import os
from datetime import datetime as dt
from zoneinfo import ZoneInfo
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes

# ----------------------------
# CONFIGURACIÓ
# ----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN_RAURE")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ La variable d'entorn TELEGRAM_TOKEN_RAURE no està definida")

# Zona horària Madrid
MADRID_TZ = ZoneInfo("Europe/Madrid")
TARGET_DATE = dt(2025, 9, 28, 11, 0, 0, tzinfo=MADRID_TZ)

# Missatge fix
fixed_message_id = None
fixed_chat_id = None

# ----------------------------
# FUNCIONS COMPTE ENRERE
# ----------------------------
def generar_countdown():
    now = dt.now(MADRID_TZ)
    remaining = TARGET_DATE - now
    if remaining.total_seconds() > 0:
        days = remaining.days
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        countdown = (
            f"       ⏳ {days} dies\n"
            f"       ⏰ {hours} hores\n"
            f"       ⏱️ {minutes} minuts\n"
            f"       ⏲️ {seconds} segons"
        )
        return (
            f"🎉 <b>Ginkana de la Fira del Raure</b> 🎉\n\n"
            f"⏳ Compte enrere fins diumenge 28 de setembre de 2025 a les 11h (hora Madrid):\n"
            f"{countdown}\n\n"
            f"🔗 El Bot de la Ginkana serà accessible aquí: <b>@Gi*************Bot</b>\n"
            "ℹ️ L'enllaç al JOC es mostrarà el diumenge 28 de setembre de 2025 a les 11h."
        )
    else:
        return generar_final()

def generar_final():
    return (
        "🎉 <b>Ginkana de la Fira del Raure</b> 🎉\n\n"
        "⏳ El compte enrere ha finalitzat!\n\n"
        "🔗 El JOC de la Ginkana és: <b>@GinkanaGinestarBot</b>\n"
        "Accediu-hi per inscriure-us i començar la Ginkana!"
    )

async def countdown_task(context: ContextTypes.DEFAULT_TYPE):
    global fixed_message_id, fixed_chat_id
    if not fixed_message_id or not fixed_chat_id:
        logging.warning("❌ Missatge fix no inicialitzat")
        return

    while True:
        now = dt.now(MADRID_TZ)
        remaining_seconds = (TARGET_DATE - now).total_seconds()
        message = generar_countdown()

        try:
            await context.bot.edit_message_text(
                chat_id=fixed_chat_id,
                message_id=fixed_message_id,
                text=message,
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logging.warning(f"No s'ha pogut actualitzar el missatge: {e}")

        await asyncio.sleep(60)  # Actualitza cada minut

# ----------------------------
# Comandes
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global fixed_message_id, fixed_chat_id
    await update.message.reply_text(
        "👋 Hola! Benvingut/da al Bot de la Ginkana de la Fira del Raure 2025!\n"
        "Aquí tens el compte enrere 👇",
        parse_mode=constants.ParseMode.HTML
    )
    if fixed_message_id is None:
        sent_message = await update.message.reply_text(
            generar_countdown(),
            parse_mode=constants.ParseMode.HTML
        )
        fixed_message_id = sent_message.message_id
        fixed_chat_id = sent_message.chat_id
        # Llança la tasca de countdown en background
        context.application.create_task(countdown_task(context))

async def rebooom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra el missatge final temporalment sense aturar el compte enrera"""
    await update.message.reply_text(
        generar_final(),
        parse_mode=constants.ParseMode.HTML
    )

# ----------------------------
# Main
# ----------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rebooom", rebooom))

    logging.info("🚀 Bot de compte enrere en marxa...")
    app.run_polling()

if __name__ == "__main__":
    main()
