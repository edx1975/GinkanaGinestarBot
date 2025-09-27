from dotenv import load_dotenv
import os
load_dotenv()
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")

# ----------------------------
# Variables d'entorn
# ----------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ Falta la variable d'entorn TELEGRAM_TOKEN")
    exit(1)

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
sheet_records = gc.open(GINKANA_PUNTS_SHEET).worksheet("punts_equips")

# ----------------------------
# Cache Google Sheets
# ----------------------------
_cache_records = None
_cache_time = None
_CACHE_TTL = 10  # segons

def get_records():
    global _cache_records, _cache_time
    now = datetime.datetime.now()
    if _cache_records is None or (now - _cache_time).total_seconds() > _CACHE_TTL:
        _cache_records = sheet_records.get_all_records()
        _cache_time = now
    return _cache_records

# ----------------------------
# Helpers Google Sheets
# ----------------------------
def carregar_proves():
    sheet_proves = gc.open(GINKANA_PUNTS_SHEET).worksheet("proves")
    rows = sheet_proves.get_all_records()
    proves = {str(int(row["id"])): row for row in rows}
    return proves

def carregar_equips():
    sheet_equips = gc.open(GINKANA_PUNTS_SHEET).worksheet("equips")
    rows = sheet_equips.get_all_records()
    equips = {}
    for row in rows:
        equips[row["equip"]] = {
            "portaveu": row["portaveu"].lstrip("@").lower(),
            "jugadors": [j.strip() for j in row["jugadors"].split(",") if j.strip()],
            "hora_inscripcio": row.get("hora_inscripcio", "")
        }
    return equips

def guardar_equip(equip, portaveu, jugadors_llista):
    hora = datetime.datetime.now(MADRID_TZ).strftime("%H:%M")
    sheet_equips = gc.open(GINKANA_PUNTS_SHEET).worksheet("equips")
    sheet_equips.append_row([equip, portaveu.lstrip("@"), ",".join(jugadors_llista), hora])

def guardar_submission(equip, prova_id, resposta, punts, estat):
    hora = datetime.datetime.now(MADRID_TZ).strftime("%H:%M:%S")
    sheet_records.append_row([equip, prova_id, resposta, punts, estat, hora])
    global _cache_records, _cache_time
    _cache_records = None
    _cache_time = None

def ja_resposta(equip, prova_id):
    records = get_records()
    return any(row["equip"] == equip and str(row["prova_id"]) == str(prova_id) for row in records)

def respostes_equip(equip):
    res = {}
    for row in get_records():
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

def validate_answer(prova, resposta):
    tipus = prova["tipus"]
    punts = int(prova["punts"])
    correct_answer = prova["resposta"]
    if correct_answer == "REVIEW_REQUIRED":
        return 0, "PENDENT"
    if tipus in ["trivia", "qr", "final_joc"]:
        possibles = [r.strip().lower() for r in correct_answer.split("|")]
        if str(resposta).strip().lower() in possibles:
            return punts, "VALIDADA"
        else:
            return 0, "INCORRECTA"
    return 0, "PENDENT"

def guardar_chat_id(username, chat_id):
    username = username.lower()
    sheet_usuaris = gc.open(GINKANA_PUNTS_SHEET).worksheet("usuaris")
    records = sheet_usuaris.get_all_records()
    exists = any(int(r["chat_id"]) == chat_id for r in records)
    if not exists:
        sheet_usuaris.append_row([username, chat_id])

def carregar_chat_ids():
    sheet_usuaris = gc.open(GINKANA_PUNTS_SHEET).worksheet("usuaris")
    chat_ids = set()
    for row in sheet_usuaris.get_all_records():
        try:
            chat_ids.add(int(row["chat_id"]))
        except ValueError:
            print(f"⚠️ Chat ID invàlid a usuaris sheet: {row['chat_id']}")
    return list(chat_ids)

def carregar_ajuda():
    sheet_ajuda = gc.open(GINKANA_PUNTS_SHEET).worksheet("ajuda")
    return sheet_ajuda.acell("A1").value or "ℹ️ Encara no hi ha ajuda definida."

def carregar_emergencia():
    sheet_emergencia = gc.open(GINKANA_PUNTS_SHEET).worksheet("emergencia")
    return sheet_emergencia.acell("A1").value or "ℹ️ No hi ha cap missatge d'emergència definit."

# ----------------------------
# Comandes Telegram
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benvingut a la Gran Ginkana de la Fira del Raure 2025 de Ginestar!\n\n"
        "La Ginkana ha començat a les 11h i acaba a les 19h. \n"
        "Contesta els 3 blocs de 10 proves. Per desbloquejar el següent bloc, primer has d'haver contestat l'actual.\n\n"
        "📖 Comandes útils:\n"
        "/ajuda - veure menú d'ajuda\n"
        "/inscriure NomEquip nom1,nom2,nom3 - registrar el teu equip\n"
        "/proves - veure llista de proves\n"
        "/ranking - veure puntuacions\n\n"
        "📣 Per respondre una prova envia:\n"
        "resposta <numero> <resposta>\n\n"
        "🐔 Una iniciativa de Lo Corral associació cultural amb la col·laboració de lo Grup de Natura lo Margalló \n"
    )

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = carregar_ajuda()
    await update.message.reply_text(msg)

async def inscriure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    guardar_chat_id((user.username or user.first_name).lower(), user.id)
    if len(context.args) < 2:
        await update.message.reply_text("Format: /inscriure NomEquip nom1,nom2,...")
        return
    equip = context.args[0]
    jugadors_text = " ".join(context.args[1:])
    jugadors_llista = [j.strip() for j in jugadors_text.split(",") if j.strip()]
    if not jugadors_llista:
        await update.message.reply_text("❌ Cal indicar almenys un jugador.")
        return
    portaveu = (user.username or user.first_name).lower()
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
    res = respostes_equip(equip)
    rang = {1: range(1,11),2:range(11,21),3:range(21,31)}[bloc]
    msg = f"📋 Llista de proves pendents (bloc {bloc}):\n\n"
    for pid in rang:
        if str(pid) in proves and str(pid) not in res:
            p = proves[str(pid)]
            msg += f"{pid}. {p['titol']}\n{p['descripcio']} - {p['punts']} punts\n\n"
    if msg.strip() == f"📋 Llista de proves pendents (bloc {bloc}):":
        msg += "🎉 Totes les proves del bloc actual han estat contestades!"
    await update.message.reply_text(msg)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = get_records()
    equips_data = {}
    for row in records:
        e = row["equip"]
        equips_data.setdefault(e, {"punts":0,"contestades":0,"correctes":0,"respostes":{}})
        equips_data[e]["contestades"] += 1
        equips_data[e]["respostes"][str(row["prova_id"])] = row.get("hora")
        if row["estat"] == "VALIDADA":
            equips_data[e]["punts"] += int(row["punts"])
            equips_data[e]["correctes"] += 1
    if not equips_data:
        await update.message.reply_text("No hi ha punts registrats encara.")
        return
    sorted_equips = sorted(equips_data.items(), key=lambda x: x[1]["punts"], reverse=True)
    msg = "🏆 Classificació:\n\n"
    for i,(equip,data) in enumerate(sorted_equips,start=1):
        base = f"{i}. {equip} - {data['punts']} punts ({data['correctes']}/{data['contestades']} ✅)"
        if all(str(pid) in data["respostes"] for pid in range(1,31)):
            hores = [
                datetime.datetime.strptime(data["respostes"][str(pid)], "%H:%M:%S")
                for pid in range(1,31)
                if data["respostes"].get(str(pid))
            ]
            if hores:
                hora_final = max(hores).strftime("%H:%M:%S")
                base += f" | Fi: {hora_final}h ⏰"
        msg += base + "\n"
    await update.message.reply_text(msg)

async def ekips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    equips = carregar_equips()
    records = get_records()
    equips_list = []
    for equip, info in equips.items():
        punts = sum(
            int(row["punts"])
            for row in records
            if row["equip"] == equip and row["estat"] == "VALIDADA"
        )
        equips_list.append({
            "equip": equip,
            "portaveu": info["portaveu"],
            "jugadors": ", ".join(info["jugadors"]),
            "hora": info.get("hora_inscripcio", ""),
            "punts": punts
        })
    equips_list.sort(key=lambda x: x["hora"])
    msg = "📋 Llista d'equips:\n\n"
    for e in equips_list:
        msg += f"{e['equip']} | @{e['portaveu']} | Jugadors: {e['jugadors']} | Hora insc: {e['hora']} | Punts: {e['punts']}\n"
    await update.message.reply_text(msg)

async def resposta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text.lower().startswith("resposta"):
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
    icon = {"VALIDADA": "✅","INCORRECTA": "❌","PENDENT": "⏳"}.get(estat, "ℹ️")
    await update.message.reply_text(f"{icon} Resposta registrada: {estat}. Punts: {punts}")

# ----------------------------
# Emergència ara llegeix de Google Sheets
# ----------------------------
async def emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    missatge = carregar_emergencia()
    chat_ids = carregar_chat_ids()
    if not chat_ids:
        await update.message.reply_text("⚠️ No hi ha cap usuari registrat per enviar el missatge d'emergència.")
        return
    enviats = 0
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=missatge)
            enviats += 1
        except Exception as e:
            print(f"❌ No s'ha pogut enviar a {chat_id}: {e}")
    await update.message.reply_text(f"📢 Missatge d'emergència enviat a {enviats} usuaris.")

# ----------------------------
# Main
# ----------------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("inscriure", inscriure))
    app.add_handler(CommandHandler("proves", llistar_proves))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("ekips", ekips))
    app.add_handler(CommandHandler("emergencia", emergencia))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, resposta_handler))
    app.add_handler(MessageHandler(filters.COMMAND, lambda u,c: u.message.reply_text("Comanda desconeguda")))
    print("✅ Bot Ginkana en marxa...")
    app.run_polling()

if __name__=="__main__":
    main()
