import logging
import asyncio
import os
import csv
import datetime
from datetime import datetime as dt
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# CONFIGURACIÓ
# ----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Tokens i data objectiu
TELEGRAM_TOKEN = "8327719051:AAEl9-TWDMCTaQ9qw73ujhiNQeLMdoq-YFM"  # Canvia pel teu token
TARGET_DATE = dt(2025, 9, 28, 11, 0, 0)

# Missatge fix del compte enrere
fixed_message_id = None
fixed_chat_id = None

# ----------------------------
# Fitxers CSV
# ----------------------------
PROVES_CSV = os.getenv("GINKANA_PROVES_CSV", "./proves_ginkana.csv")
EQUIPS_CSV = os.getenv("GINKANA_EQUIPS_CSV", "./equips.csv")
PUNTS_CSV = os.getenv("GINKANA_PUNTS_CSV", "./punts_equips.csv")
AJUDA_TXT = os.getenv("GINKANA_AJUDA_TXT", "./ajuda.txt")

# ----------------------------
# HELPERS GINKANA
# ----------------------------
def carregar_proves():
    proves = {}
    if os.path.exists(PROVES_CSV):
        with open(PROVES_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                proves[str(int(row["id"]))] = row
    return proves

def carregar_equips():
    equips = {}
    if os.path.exists(EQUIPS_CSV):
        with open(EQUIPS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                equips[row["equip"]] = {
                    "portaveu": row["portaveu"].lstrip("@").lower(),
                    "jugadors": [j.strip() for j in row["jugadors"].split(",") if j.strip()]
                }
    return equips

def guardar_equip(equip, portaveu, jugadors_llista):
    hora = datetime.datetime.now().strftime("%H:%M")
    exists = os.path.exists(EQUIPS_CSV)
    with open(EQUIPS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["equip","portaveu","jugadors","hora_inscripcio"])
        writer.writerow([equip, portaveu.lstrip("@"), ",".join(jugadors_llista), hora])

def guardar_submission(equip, prova_id, resposta, punts, estat):
    exists = os.path.exists(PUNTS_CSV)
    with open(PUNTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["equip","prova_id","resposta","punts","estat"])
        writer.writerow([equip, prova_id, resposta, punts, estat])

def ja_resposta(equip, prova_id):
    if not os.path.exists(PUNTS_CSV):
        return False
    with open(PUNTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["equip"] == equip and row["prova_id"] == prova_id:
                return True
    return False

def respostes_equip(equip):
    res = {}
    if os.path.exists(PUNTS_CSV):
        with open(PUNTS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["equip"] == equip:
                    res[row["prova_id"]] = row["estat"]
    return res

def bloc_actual(equip, proves):
    res = respostes_equip(equip)
    total = len(proves)
    if all(str(i) in res for i in range(1, 11)):
        if all(str(i) in res for i in range(11, 21)):
            return 3 if total >= 21 else 2
        return 2
    return 1

def validate_answer(prova, resposta):
    tipus = prova["tipus"]
    punts = int(prova["punts"])
    if tipus == "final_joc":
        return punts, "VALIDADA"
    correct_answer = prova["resposta"]
    if correct_answer == "REVIEW_REQUIRED":
        return 0, "PENDENT"
    if tipus in ["trivia", "qr"]:
        possibles = [r.strip().lower() for r in correct_answer.split("|")]
        if str(resposta).strip().lower() in possibles:
            return punts, "VALIDADA"
        else:
            return 0, "INCORRECTA"
    return 0, "PENDENT"

# ----------------------------
# FUNCIONS COMPTE ENRERE
# ----------------------------
def generar_countdown():
    now = dt.now()
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
    else:
        countdown = "🎉 Ja ha començat la Ginkana!"
    message = (
        f"🎉 <b>Ginkana de la Fira del Raure</b> 🎉\n\n"
        f"⏳ Compte enrere fins diumenge 28 de setembre de 2025 a les 11h:\n"
        f"{countdown}\n\n"
        f"🔗 El Bot de la Ginkana serà accessible aquí: <b>@Gi*************Bot</b>\n"
        "ℹ️ L'enllaç al bot es mostrarà el diumenge 28 de setembre de 2025 a les 11h."
    )
    return message

async def countdown_task(context: ContextTypes.DEFAULT_TYPE):
    global fixed_message_id, fixed_chat_id
    if not fixed_message_id or not fixed_chat_id:
        logging.warning("❌ Missatge fix no inicialitzat")
        return

    while True:
        remaining_seconds = (TARGET_DATE - dt.now()).total_seconds()
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

        # Quan finalitza el compte enrere, inicialitza automàticament la Ginkana
        if remaining_seconds <= 0:
            logging.info("✅ Compte enrere finalitzat, inicialitzant Ginkana...")
            # Crida la funció de start de la Ginkana
            from functools import partial
            await start_ginkana(context.application, fixed_chat_id)
            break

        await asyncio.sleep(60)  # Actualitza cada minut

# ----------------------------
# FUNCIONS GINKANA
# ----------------------------
async def start_ginkana(app, chat_id):
    """
    Envia el missatge inicial de la Ginkana al xat indicat.
    """
    await app.bot.send_message(
        chat_id=chat_id,
        text=(
            "👋 Benvingut a la Gran Ginkana de la Fira del Raure 2025 de Ginestar!\n\n"
            "La Ginkana comença a les 11h i acaba a les 19h. \n"
            "Contesta els 3 blocs de 10 proves. Per desbloquejar el següent bloc, primer has d'haver contestat l'actual.\n\n"
            "📖 Comandes útils:\n"
            "/ajuda - veure menú d'ajuda\n"
            "/inscriure NomEquip nom1,nom2,nom3 - registrar el teu equip\n"
            "/proves - veure llista de proves\n"
            "/ranking - veure puntuacions\n"
            "/manquen - veure proves pendents del teu bloc actual\n\n"
            "📣 Per respondre una prova envia:\n"
            "resposta <numero> <resposta>\n\n"
            "🐔 Una iniciativa de Lo Corral associació cultural amb la col·laboració de lo Grup de Natura lo Margalló"
        ),
        parse_mode=constants.ParseMode.HTML
    )

# ----------------------------
# Comandes /start
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global fixed_message_id, fixed_chat_id
    if fixed_message_id is None:
        sent_message = await update.message.reply_text(
            "⌛ Iniciant compte enrere...",
            parse_mode=constants.ParseMode.HTML
        )
        fixed_message_id = sent_message.message_id
        fixed_chat_id = sent_message.chat_id
        context.application.create_task(countdown_task(context))
    else:
        await update.message.reply_text(
            "⏳ El compte enrere ja està actiu al xat!",
            parse_mode=constants.ParseMode.HTML
        )

# ----------------------------
# Main
# ----------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers del bot
    app.add_handler(CommandHandler("start", start))
    # Aquí es poden afegir handlers de la Ginkana (ajuda, inscriure, proves, etc.)
    # Els handlers complets de la Ginkana es poden afegir aquí com al codi original

    logging.info("🚀 Bot de compte enrere i Ginkana en marxa...")
    app.run_polling()

if __name__ == "__main__":
    main()

