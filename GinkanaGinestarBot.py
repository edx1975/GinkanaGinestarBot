import datetime
import json
import gspread
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from oauth2client.service_account import ServiceAccountCredentials

# ----------------------------
# CONFIGURACIÓ
# ----------------------------
TELEGRAM_TOKEN = "EL_TEU_TOKEN"
SHEET_NAME = "Ginkana"

# ----------------------------
# GOOGLE SHEETS
# ----------------------------
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# ----------------------------
# Helpers Google Sheets
# ----------------------------
def guardar_submission(equip, prova_id, resposta, punts, estat):
    hora = datetime.datetime.now().strftime("%H:%M:%S")
    sheet.append_row([equip, prova_id, resposta, punts, estat, hora])

def carregar_proves():
    with open("proves.json", "r", encoding="utf-8") as f:
        return json.load(f)

def carregar_equips():
    with open("equips.json", "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_equips(equips):
    with open("equips.json", "w", encoding="utf-8") as f:
        json.dump(equips, f, indent=4, ensure_ascii=False)

# ----------------------------
# BOT COMMANDS
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benvingut a la Ginkana!\n\n"
        "Fes servir /ajuda per veure les instruccions."
    )

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 Instruccions:\n"
        "/inscriure nom_equip -> Inscriure un equip\n"
        "/proves -> Veure la llista de proves\n"
        "/manquen -> Proves que et falten\n"
        "/ranking -> Veure classificació\n"
        "/ekips -> Llistar equips"
    )

async def inscriure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usa: /inscriure NOM_EQUIP")
        return

    nom_equip = context.args[0]
    equips = carregar_equips()
    usuari = update.effective_user.username

    if nom_equip in equips:
        await update.message.reply_text("❌ Aquest equip ja està registrat.")
        return

    equips[nom_equip] = {
        "portaveu": usuari,
        "jugadors": [usuari],
        "hora_inscripcio": datetime.datetime.now().strftime("%H:%M:%S")
    }
    guardar_equips(equips)

    await update.message.reply_text(f"✅ Equip {nom_equip} inscrit correctament!")

async def llistar_proves(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proves = carregar_proves()
    msg = "📚 Llista de proves:\n\n"
    for prova in proves:
        msg += f"{prova['id']}: {prova['pregunta']}\n"
    await update.message.reply_text(msg)

async def manquen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    equips = carregar_equips()
    usuari = update.effective_user.username
    equip = next((e for e, d in equips.items() if usuari in d["jugadors"]), None)

    if not equip:
        await update.message.reply_text("⚠️ No estàs inscrit a cap equip.")
        return

    proves = carregar_proves()
    submissions = sheet.get_all_records()

    fets = [s["prova_id"] for s in submissions if s["equip"] == equip]
    pendents = [p for p in proves if str(p["id"]) not in fets]

    msg = "📌 Proves pendents:\n"
    for p in pendents:
        msg += f"{p['id']}: {p['pregunta']}\n"

    await update.message.reply_text(msg)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    submissions = sheet.get_all_records()
    equips = {}

    for s in submissions:
        equips[s["equip"]] = equips.get(s["equip"], 0) + int(s["punts"])

    ranking = sorted(equips.items(), key=lambda x: x[1], reverse=True)

    msg = "🏆 Rànquing:\n"
    for i, (equip, punts) in enumerate(ranking, 1):
        msg += f"{i}. {equip} - {punts} punts\n"

    await update.message.reply_text(msg)

async def llistar_equips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    equips = carregar_equips()
    records = sheet.get_all_records()

    msg = "📋 Llista d'equips:\n\n"
    for equip, info in equips.items():
        # Buscar hora resposta de la prova 30
        hora_prova_30 = "pendent"
        for row in records:
            if row["equip"] == equip and str(row["prova_id"]) == "30":
                hora_prova_30 = row.get("hora", "pendent")
                break

        msg += (
            f"{equip} | Portaveu: @{info['portaveu']} | "
            f"Jugadors: {', '.join(info['jugadors'])} | "
            f"Inscripció: {info.get('hora_inscripcio','?')} | "
            f"Prova 30: {hora_prova_30}\n"
        )

    await update.message.reply_text(msg)

# ----------------------------
# RESPOSTES
# ----------------------------
def validate_answer(prova, resposta):
    return (10, "correcte") if resposta.strip().lower() == prova["resposta"].strip().lower() else (0, "incorrecte")

async def resposta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split(" ", 1)

    if len(parts) < 2:
        await update.message.reply_text("⚠️ Usa: ID_RESPOSTA TEXT")
        return

    prova_id, resposta = parts
    proves = carregar_proves()
    prova = next((p for p in proves if str(p["id"]) == prova_id), None)

    if not prova:
        await update.message.reply_text("❌ Prova no trobada.")
        return

    equips = carregar_equips()
    usuari = update.effective_user.username
    equip = next((e for e, d in equips.items() if usuari in d["jugadors"]), None)

    if not equip:
        await update.message.reply_text("⚠️ No estàs inscrit a cap equip.")
        return

    punts, estat = validate_answer(prova, resposta)
    guardar_submission(equip, prova_id, resposta, punts, estat)

    await update.message.reply_text(f"📥 Resposta registrada ({estat})")

# ----------------------------
# MAIN
# ----------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("inscriure", inscriure))
    app.add_handler(CommandHandler("proves", llistar_proves))
    app.add_handler(CommandHandler("manquen", manquen))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("ekips", llistar_equips))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, resposta_handler))
    print("✅ Bot Ginkana en marxa...")
    app.run_polling()

if __name__ == "__main__":
    main()
