import logging
import asyncio
from datetime import datetime
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes

# ----------------------------
# Configuració del log
# ----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ----------------------------
# Variables del bot
# ----------------------------
TELEGRAM_TOKEN = "7914578668:AAGeqije0MbzGrdj4PGxsucRyn2hc-WcXUM"  # Substitueix pel teu token
TARGET_DATE = datetime(2025, 9, 28, 11, 0, 0)  # Data i hora de la ginkana

# Variable global per guardar el missatge fix
fixed_message_id = None
fixed_chat_id = None

# ----------------------------
# Tasca de compte enrere
# ----------------------------
async def countdown_task(context: ContextTypes.DEFAULT_TYPE):
    """
    Actualitza el missatge fix amb el compte enrere cada minut.
    """
    global fixed_message_id, fixed_chat_id
    if not fixed_message_id or not fixed_chat_id:
        logging.warning("❌ Missatge fix no inicialitzat")
        return

    while True:
        now = datetime.now()
        remaining = TARGET_DATE - now

        if remaining.total_seconds() > 0:
            days = remaining.days
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            countdown = (
                f"<b>{days} dies</b>\n"
                f"<b>{hours} hores</b>\n"
                f"<b>{minutes} minuts</b>\n"
                f"<b>{seconds} segons</b>"
            )
        else:
            countdown = "🎉 Ja ha començat la Ginkana!"

        message = (
            "<b>🎉 Ginkana de la Fira del Raure 🎉</b>\n\n"
            "⏳ Compte enrere fins diumenge 28 de setembre de 2025 a les 11h:\n"
            f"{countdown}\n\n"
            "🔗 El Bot de la Ginkana serà accessible aquí: <b>@Gi*************Bot</b>\n"
            "ℹ️ L'enllaç al bot es mostrarà el diumenge 28 de setembre de 2025 a les 11h."
        )

        try:
            await context.bot.edit_message_text(
                chat_id=fixed_chat_id,
                message_id=fixed_message_id,
                text=message,
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logging.warning(f"No s'ha pogut actualitzar el missatge: {e}")

        if remaining.total_seconds() <= 0:
            logging.info("✅ Compte enrere completat.")
            break

        await asyncio.sleep(60)  # Actualitza cada minut

# ----------------------------
# Comanda /start
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Envia el missatge fix si no existeix, o indica als usuaris que ja està actiu.
    """
    global fixed_message_id, fixed_chat_id

    # Si no hi ha missatge fix, en crear un
    if fixed_message_id is None:
        sent_message = await update.message.reply_text(
            "⌛ Iniciant compte enrere...",
            parse_mode=constants.ParseMode.HTML
        )
        fixed_message_id = sent_message.message_id
        fixed_chat_id = sent_message.chat_id
        logging.info(f"Missatge fix creat per @{update.effective_user.username}")

        # Llança la tasca de compte enrere en segon pla
        context.application.create_task(countdown_task(context))
    else:
        # Ja hi ha un missatge fix
        await update.message.reply_text(
            "⏳ El compte enrere ja està actiu al xat!",
            parse_mode=constants.ParseMode.HTML
        )
        logging.info(f"Usuari @{update.effective_user.username} ha comprovat el compte enrere")

# ----------------------------
# Main
# ----------------------------
def main():
    if not TELEGRAM_TOKEN:
        print("❌ Falta el token del bot!")
        return

    # Crear aplicació
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Afegir handler per la comanda /start
    app.add_handler(CommandHandler("start", start))

    logging.info("🚀 Bot de compte enrere amb missatge fix en marxa...")
    app.run_polling()

if __name__ == "__main__":
    main()
