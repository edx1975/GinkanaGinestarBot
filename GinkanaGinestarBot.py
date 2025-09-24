from dotenv import load_dotenv
import os
load_dotenv()  # Això llegeix el .env i posa les variables a os.environ
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
import json
import csv

# ----------------------------
# Variables d'entorn
# ----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Falta la variable d'entorn TELEGRAM_TOKEN")
    exit(1)

GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
if not GOOGLE_CREDS_JSON:
    print("❌ Falta la variable d'entorn GOOGLE_CREDS_JSON")
    exit(1)

PROVES_CSV = os.getenv("GINKANA_PROVES_CSV", "./proves_ginkana.csv")
EQUIPS_CSV = os.getenv("GINKANA_EQUIPS_CSV", "./equips.csv")
AJUDA_TXT = os.getenv("GINKANA_AJUDA_TXT", "./ajuda.txt")
GINKANA_PUNTS_SHEET = os.getenv("GINKANA_PUNTS_SHEET", "punts_equips")

# ----------------------------
# Google Sheets
# ----------------------------
creds_dict = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
}

gc = gspread.service_account_from_dict(creds_dict)
sheet = gc.open(os.getenv("GINKANA_PUNTS_SHEET")).sheet1
print(sheet.get_all_records())

# ----------------------------
# Helpers CSV
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

# ----------------------------
# Helpers Google Sheets
# ----------------------------
def guardar_submission(equip, prova_id, resposta, punts, estat):
    sheet.append_row([equip, prova_id, resposta, punts, estat])

def ja_resposta(equip, prova_id):
    records = sheet.get_all_records()
    for row in records:
        if row["equip"] == equip and str(row["prova_id"]) == str(prova_id):
            return True
    return False

def respostes_equip(equip):
    res = {}
    records = sheet.get_all_records()
    for row in records:
        if row["equip"] == equip:
            res[str(row["prova_id"])] = row["estat"]
    return res

def bloc_actual(equip, proves):
    res = respostes_equip(equip)
    total = len(proves)
    if all(str(i) in res for i in range(1, 11)):
        if all(str(i) in res for i in range(11, 21)):
            return 3 if total >= 21 else 2
        return 2
    return 1

# ----------------------------
# Validació de respostes
# ----------------------------
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
# Comandes Telegram
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benvingut a la Gran Ginkana de Ginestar 2025!\n"
        "Contesta els 3 blocs de proves.\n"
        "Comandes: /ajuda /inscriure /proves /ranking /manquen\n"
        "Per respondre: resposta <numero> <resposta>"
    )

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(AJUDA_TXT):
        with open(AJUDA_TXT, encoding="utf-8") as f:
            msg = f.read()
    else:
        msg = "ℹ️ Encara no hi ha ajuda definida."
    await update.message.reply_text(msg)

async def inscriure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format: /inscriure NomEquip nom1,nom2,...")
        return
    equip = context.args[0]
    jugadors_text = " ".join(context.args[1:])
    jugadors_llista = [j.strip() for j in jugadors_text.split(",") if j.strip()]
    if not jugadors_llista:
        await update.message.reply_text("❌ Cal indicar almenys un jugador.")
        return
    portaveu = (update.message.from_user.username or update.message.from_user.first_name).lower()
    equips = carregar_equips()
    for info in equips.values():
        if info["portaveu"] == portaveu:
            await update.message.reply_text("❌ Ja ets portaveu d'un altre equip.")
            return
    guardar_equip(equip, portaveu, jugadors_llista)
    await update.message.reply_text(f"✅ Equip '{equip}' registrat amb portaveu @{portaveu}.")

async def llistar_proves(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proves = carregar_proves()
    user = update.message.from_user
    username = (user.username or "").lstrip("@").lower()
    firstname = (user.first_name or "").lower()
    equips = carregar_equips()
    equip = None
    for e, info in equips.items():
        if info["portaveu"] in [username, firstname]:
            equip = e
            break
    if not equip:
        await update.message.reply_text("❌ Has d'estar inscrit per veure les proves.")
        return
    bloc = bloc_actual(equip, proves)
    rang = {1: range(1,11),2:range(11,21),3:range(21,31)}[bloc]
    msg = f"📋 Llista de proves (bloc {bloc}):\n\n"
    for pid in rang:
        if str(pid) in proves:
            p = proves[str(pid)]
            msg += f"{pid}. {p['titol']}\n{p['descripcio']} - {p['punts']} punts\n\n"
    await update.message.reply_text(msg)

async def manquen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proves = carregar_proves()
    user = update.message.from_user
    username = (user.username or "").lstrip("@").lower()
    firstname = (user.first_name or "").lower()
    equips = carregar_equips()
    equip = None
    for e, info in equips.items():
        if info["portaveu"] in [username, firstname]:
            equip = e
            break
    if not equip:
        await update.message.reply_text("❌ Has d'estar inscrit.")
        return
    res = respostes_equip(equip)
    if "31" in res:
        await update.message.reply_text("🏆 Heu completat la ginkana! /ranking per veure resultats.")
        return
    bloc = bloc_actual(equip, proves)
    rang = {1: range(1,11),2:range(11,21),3:range(21,31)}[bloc]
    mancants = [str(pid) for pid in rang if str(pid) not in res and str(pid) in proves]
    if mancants:
        await update.message.reply_text(f"❓ Proves pendents al bloc {bloc}: {', '.join(mancants)}")
    else:
        await update.message.reply_text(f"🎉 Totes les proves del bloc {bloc} han estat contestades!")
        await llistar_proves(update, context)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = sheet.get_all_records()
    equips_data = {}
    for row in records:
        e = row["equip"]
        equips_data.setdefault(e, {"punts":0,"contestades":0,"correctes":0})
        equips_data[e]["contestades"] += 1
        if row["estat"] == "VALIDADA":
            equips_data[e]["punts"] += int(row["punts"])
            equips_data[e]["correctes"] += 1
    if not equips_data:
        await update.message.reply_text("No hi ha punts registrats encara.")
        return
    sorted_equips = sorted(equips_data.items(), key=lambda x: x[1]["punts"], reverse=True)
    msg = "🏆 Classificació provisional:\n\n"
    for i,(equip,data) in enumerate(sorted_equips,start=1):
        msg += f"{i}. {equip} - {data['punts']} punts ({data['correctes']}/{data['contestades']} correctes)\n"
    await update.message.reply_text(msg)

async def resposta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text.lower().startswith("resposta"):
        # Aquí entrem si NO és una resposta vàlida
        await update.message.reply_text("Resposta no entesa. Revisa l' /ajuda")
        return

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Format: resposta <id> <text>")
        return

    prova_id, resposta = parts[1], parts[2]
    proves = carregar_proves()
    if prova_id not in proves:
        await update.message.reply_text("❌ Prova no trobada.")
        return

    user = update.message.from_user
    username = (user.username or "").lstrip("@").lower()
    firstname = (user.first_name or "").lower()
    equips = carregar_equips()
    equip = None
    for e, info in equips.items():
        if info["portaveu"] in [username, firstname]:
            equip = e
            break

    if not equip:
        await update.message.reply_text("❌ Només el portaveu pot enviar respostes.")
        return
    if ja_resposta(equip, prova_id):
        await update.message.reply_text(f"⚠️ L'equip '{equip}' ja ha respost la prova {prova_id}.")
        return

    bloc_anterior = bloc_actual(equip, proves)
    prova = proves[prova_id]
    punts, estat = validate_answer(prova, resposta)
    guardar_submission(equip, prova_id, resposta, punts, estat)
    await update.message.reply_text(f"✅ Resposta registrada: {estat}. Punts: {punts}")

    bloc_nou = bloc_actual(equip, proves)
    if bloc_nou == 2 and bloc_anterior == 1:
        await update.message.reply_text("🎺 Bloc 1 completat, aquí tens el 2!")
        await llistar_proves(update, context)
    elif bloc_nou == 3 and bloc_anterior == 2:
        await update.message.reply_text("🎉 Bloc 2 completat, aquí tens el 3!")
        await llistar_proves(update, context)

    res = respostes_equip(equip)
    if all(str(i) in res for i in range(21,31)) and "31" not in res:
        await update.message.reply_text("🎆 Queden les últimes proves! Resposta 31 per completar la ginkana.")
    if prova["tipus"] == "final_joc":
        await update.message.reply_text("🏆 Ginkana completada! /ranking per veure resultats.")

# ----------------------------
# Main
# ----------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("inscriure", inscriure))
    app.add_handler(CommandHandler("proves", llistar_proves))
    app.add_handler(CommandHandler("manquen", manquen))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, resposta_handler))
    print("✅ Bot Ginkana en marxa...")
    app.run_polling()

if __name__=="__main__":
    main()
