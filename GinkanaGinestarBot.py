from dotenv import load_dotenvfrom dotenv import load_dotenv
import os
load_dotenv()
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
from zoneinfo import ZoneInfo
from typing import Callable, Any, Dict, Tuple, Optional

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
# Google Sheets - credencials
# ----------------------------
creds_dict = {
    "type": "service_account",
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
}

gc = gspread.service_account_from_dict(creds_dict)

# ----------------------------
# Worksheets
# ----------------------------
sheet_records = None
sheet_proves = None
sheet_equips = None
sheet_usuaris = None
sheet_ajuda = None
sheet_emergencia = None

def init_worksheets():
    global sheet_records, sheet_proves, sheet_equips, sheet_usuaris, sheet_ajuda, sheet_emergencia
    sh = gc.open(GINKANA_PUNTS_SHEET)
    sheet_records = sh.worksheet("punts_equips")
    sheet_proves = sh.worksheet("proves")
    sheet_equips = sh.worksheet("equips")
    sheet_usuaris = sh.worksheet("usuaris")
    sheet_ajuda = sh.worksheet("ajuda")
    sheet_emergencia = sh.worksheet("emergencia")

# ----------------------------
# Cache
# ----------------------------
_CACHE: Dict[str, Tuple[Any, datetime.datetime, int]] = {}
_CACHE_TTLS = {
    "proves": 3600,
    "equips": 60,
    "records": 5,
    "usuaris": 300,
    "ajuda": 30,
    "emergencia": 30
}

def _now():
    return datetime.datetime.now(MADRID_TZ)

def cache_get(name: str, loader: Callable[[], Any], ttl_override: Optional[int] = None):
    ttl = ttl_override if ttl_override is not None else _CACHE_TTLS.get(name, 10)
    entry = _CACHE.get(name)
    if entry:
        value, ts, entry_ttl = entry
        age = (_now() - ts).total_seconds()
        if age <= entry_ttl:
            return value
    value = loader()
    _CACHE[name] = (value, _now(), ttl)
    return value

def cache_invalidate(name: str):
    if name in _CACHE:
        del _CACHE[name]

# ----------------------------
# Helpers Google Sheets
# ----------------------------
def carregar_proves():
    def loader():
        rows = sheet_proves.get_all_records()
        proves = {str(int(row["id"])): row for row in rows}
        return proves
    return cache_get("proves", loader)

def carregar_equips():
    def loader():
        rows = sheet_equips.get_all_records()
        equips = {}
        for row in rows:
            equips[row["equip"]] = {
                "portaveu": row["portaveu"].lstrip("@").lower(),
                "jugadors": [j.strip() for j in row["jugadors"].split(",") if j.strip()],
                "hora_inscripcio": row.get("hora_inscripcio", "")
            }
        return equips
    return cache_get("equips", loader)

def get_records():
    def loader():
        return sheet_records.get_all_records()
    return cache_get("records", loader)

def carregar_ajuda():
    def loader():
        try:
            return sheet_ajuda.acell("A1").value or "ℹ️ Encara no hi ha ajuda definida."
        except Exception:
            return "ℹ️ Encara no hi ha ajuda definida."
    return cache_get("ajuda", loader)

def carregar_emergencia():
    def loader():
        try:
            return sheet_emergencia.acell("A1").value or "ℹ️ No hi ha cap missatge d'emergència definit."
        except Exception:
            return "ℹ️ No hi ha cap missatge d'emergència definit."
    return cache_get("emergencia", loader)

def carregar_chat_ids():
    def loader():
        chat_ids = set()
        rows = sheet_usuaris.get_all_records()
        for row in rows:
            try:
                chat_ids.add(int(row["chat_id"]))
            except Exception:
                print(f"⚠️ Chat ID invàlid a usuaris sheet: {row.get('chat_id')}")
        return list(chat_ids)
    return cache_get("usuaris", loader)

# ----------------------------
# Funcions de guardat
# ----------------------------
def guardar_equip(equip, portaveu, jugadors_llista):
    hora = datetime.datetime.now(MADRID_TZ).strftime("%H:%M")
    sheet_equips.append_row([equip, portaveu.lstrip("@"), ",".join(jugadors_llista), hora])
    cache_invalidate("equips")

def guardar_submission(equip, prova_id, resposta, punts, estat):
    hora = datetime.datetime.now(MADRID_TZ).strftime("%H:%M:%S")
    sheet_records.append_row([equip, prova_id, resposta, punts, estat, hora])
    cache_invalidate("records")

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
    if all(str(i) in res for i in range(1, 11)):
        if all(str(i) in res for i in range(11, 21)):
            if all(str(i) in res for i in range(21, 30)):
                return 4
            return 3
        return 2
    return 1

def validate_answer(prova, resposta):
    tipus = prova["tipus"]
    punts = int(prova["punts"])
    correct_answer = str(prova["resposta"])
    if correct_answer == "REVIEW_REQUIRED":
        return 0, "PENDENT"
    if tipus in ["trivia", "qr", "final_joc", "pregunta_secreta"]:
        possibles = [r.strip().lower() for r in correct_answer.split("|")]
        if str(resposta).strip().lower() in possibles:
            return punts, "VALIDADA"
        else:
            return 0, "INCORRECTA"
    return 0, "PENDENT"

def guardar_chat_id(username, chat_id):
    username = username.lower()
    rows = sheet_usuaris.get_all_records()
    exists = any(int(r["chat_id"]) == chat_id for r in rows)
    if not exists:
        sheet_usuaris.append_row([username, chat_id])
        cache_invalidate("usuaris")

# ----------------------------
# Missatges i icones globals
# ----------------------------
ICONS = {"VALIDADA": "✅", "INCORRECTA": "❌", "PENDENT": "⌛"}

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

# Funció per comandes desconegudes
async def comanda_desconeguda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comanda desconeguda")

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

    rangs_blocs = {
        1: range(1, 11),
        2: range(11, 21),
        3: range(21, 31),
        4: range(31, 33)
    }
    rang = rangs_blocs[bloc]

    msg = f"📋 Llista de proves pendents (bloc {bloc}):\n\n"
    for pid in rang:
        if str(pid) in proves and str(pid) not in res:
            p = proves[str(pid)]
            msg += f"{pid}. {p['titol']}\n{p['descripcio']} - {p['punts']} punts\n\n"

    if bloc == 4 and all(str(i) in res for i in range(21, 31)) and "31" not in res:
        msg += "🔐 Pregunta secreta disponible! 🤫"
    elif bloc == 4 and "32" not in res:
        msg += "🏁 Prova final de joc disponible!"
    elif msg.strip() == f"📋 Llista de proves pendents (bloc {bloc}):":
        msg += "🎉 Totes les proves del bloc actual han estat contestades!"

    await update.message.reply_text(msg)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = get_records()
    equips_data = {}
    for row in records:
        e = row["equip"]
        equips_data.setdefault(e, {"punts": 0, "contestades": 0, "correctes": 0, "respostes": {}})
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
    for i, (equip, data) in enumerate(sorted_equips, start=1):
        base = f"{i}. {equip} - {data['punts']} punts ({data['correctes']}/{data['contestades']} ✅)"
        if all(str(pid) in data["respostes"] for pid in range(1, 33)):
            hores = [
                datetime.datetime.strptime(data["respostes"][str(pid)], "%H:%M:%S")
                for pid in range(1, 33)
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

    hora_submissio = datetime.datetime.now(MADRID_TZ).strftime("%H:%M:%S")
    guardar_submission(equip, prova_id, resposta, punts, estat)

    ICONS = {"VALIDADA":"✅", "INCORRECTA":"❌", "PENDENT":"⌛"}
    icon = ICONS.get(estat, "ℹ️")
    await update.message.reply_text(f"{icon} Resposta registrada: {estat}. Punts: {punts}")

    res_despres = respostes_equip(equip)
    bloc_nou = bloc_actual(equip, proves)

    if bloc_nou == 2 and bloc_anterior == 1:
        await update.message.reply_text(
            "🎺 Ta-xàn! Enhorabona, has completat el primer bloc, aquí tens el segon!"
        )
        await llistar_proves(update, context)
    elif bloc_nou == 3 and bloc_anterior == 2:
        await update.message.reply_text(
            "🎉 Ta-ta-ta-xaaaaàn! Gairebé ho teniu! Aquí teniu les últimes instruccions per al tercer bloc:"
        )
        await llistar_proves(update, context)

    if all(str(i) in res_despres for i in range(21, 31)) and "31" not in res_despres:
        await update.message.reply_text(
            "🎆🎆🎆 TAA-TAA-TAA-XAAAAAN!!! 🎆🎆🎆\n\n"
            "🏁 FELICITATS!! Heu completat les 30 proves!\n\n"
            "🏔️ Però encara queda LA PROVA SECRETA: envieu la resposta 31 per completar la Ginkana. La trobareu de 19:01 a 19:02 a la façana principal de l'Església. No feu tard."
        )

    await ranking(update, context)

    if prova["tipus"] == "final_joc":
        await update.message.reply_text(
            "🏆 Heu completat la **Primera Gran Ginkana de la Fira del Raure** 🎉\n\n"
            "📊 Trobareu els resultats definitius a la parada de lo Margalló.\n\n\n\n"
            "🙌 Moltes gràcies a tots per participar!\n\n"
            "🐔 Lo Corral AC | Ginestar | 28-09-2025."
        )

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
    init_worksheets()
    try:
        carregar_proves()
    except Exception as e:
        print(f"⚠️ Error carregant proves a l'inici: {e}")
    try:
        carregar_equips()
    except Exception as e:
        print(f"⚠️ Error carregant equips a l'inici: {e}")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    # ... afegeix la resta de CommandHandlers
    app.add_handler(MessageHandler(filters.COMMAND, comanda_desconeguda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, resposta_handler))

    print("✅ Bot Ginkana en marxa...")
    app.run_polling()

if __name__ == "__main__":
    main()
