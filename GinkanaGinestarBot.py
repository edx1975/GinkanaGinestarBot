import os
import csv
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ----------------------------
# Variables d'entorn de GinkanaGinestarBot
# ----------------------------
TELEGRAM_TOKEN = ("8327719051:AAEl9-TWDMCTaQ9qw73ujhiNQeLMdoq-YFM")
if not TELEGRAM_TOKEN:
    print("❌ Falta la variable d'entorn TELEGRAM_TOKEN")
    exit(1)

# ----------------------------
# Fitxers CSV
# ----------------------------
PROVES_CSV = os.getenv("GINKANA_PROVES_CSV", "./proves_ginkana.csv")
EQUIPS_CSV = os.getenv("GINKANA_EQUIPS_CSV", "./equips.csv")
PUNTS_CSV = os.getenv("GINKANA_PUNTS_CSV", "./punts_equips.csv")
AJUDA_TXT = os.getenv("GINKANA_AJUDA_TXT", "./ajuda.txt")

# ----------------------------
# Helpers
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
    """Retorna les respostes d'un equip com a dict {prova_id: estat}"""
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
    # Si han contestat totes les 1..10 -> bloc 2 o 3 segons total de proves
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

    # Cas especial: prova de cloenda
    if tipus == "final_joc":
        return punts, "VALIDADA"

    correct_answer = prova["resposta"]

    if correct_answer == "REVIEW_REQUIRED":
        return 0, "PENDENT"

    if tipus in ["trivia", "qr"]:
        # permet múltiples respostes correctes separades per |
        possibles = [r.strip().lower() for r in correct_answer.split("|")]
        if str(resposta).strip().lower() in possibles:
            return punts, "VALIDADA"
        else:
            return 0, "INCORRECTA"

    return 0, "PENDENT"


# ----------------------------
# Comandes
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
        "/ranking - veure puntuacions\n"
        "/manquen - veure proves pendents del teu bloc actual\n\n"
        "📣 Per respondre una prova envia:\n"
        "resposta <numero> <resposta>\n\n"
        "🐔 Una iniciativa de Lo Corral associació cultural amb la col·laboració de lo Grup de Natura lo Margalló \n"
    )

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(AJUDA_TXT):
        with open(AJUDA_TXT, encoding="utf-8") as f:
            msg = f.read()
    else:
        msg = "ℹ️ Encara no hi ha ajuda definida. Edita 'ajuda.txt'."
    await update.message.reply_text(msg)

async def inscriure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format: /inscriure NomEquip nom1,nom2,nom3")
        return

    equip = context.args[0]
    jugadors_text = " ".join(context.args[1:])
    jugadors_llista = [j.strip() for j in jugadors_text.split(",") if j.strip()]

    if not jugadors_llista:
        await update.message.reply_text("❌ Cal indicar com a mínim un jugador.")
        return

    portaveu = (update.message.from_user.username or update.message.from_user.first_name).lower()
    equips = carregar_equips()

    # comprovar si ja és portaveu d'un altre equip
    for info in equips.values():
        if info["portaveu"] == portaveu:
            await update.message.reply_text("❌ Ja ets portaveu d'un altre equip i no pots inscriure'n més.")
            return

    guardar_equip(equip, portaveu, jugadors_llista)
    await update.message.reply_text(
        f"✅ Equip '{equip}' registrat amb portaveu @{portaveu} i jugadors: {', '.join(jugadors_llista)}"
    )

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
        await update.message.reply_text("❌ Has d'estar inscrit i ser portaveu per veure les proves.")
        return

    bloc = bloc_actual(equip, proves)
    rang = {
        1: range(1, 11),
        2: range(11, 21),
        3: range(21, 31)
    }[bloc]

    msg = f"📋 Llista de proves (bloc {bloc}):\n\n"
    for pid in rang:
        if str(pid) in proves:
            prova = proves[str(pid)]
            msg += f"{pid}. {prova['titol']}\n ({prova['descripcio']}) - {prova['punts']} punts\n\n"
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
        await update.message.reply_text("❌ Has d'estar inscrit i ser portaveu per usar aquesta comanda.")
        return

    res = respostes_equip(equip)

    # Si ja han fet la prova 31, ginkana completada
    if "31" in res:
        await update.message.reply_text(
            "🏆 Heu completat la **Primera Gran Ginkana de la Fira del Raure** 🎉\n\n"
            "📊 Trobareu els resultats amb la comanda /ranking\n\n\n\n"
            "🙌 Moltes gràcies a tots per participar!\n\n"
            "🐔 Lo Corral associació cultural, Ginestar, 28 de setembre de 2025."
        )
        return

    bloc = bloc_actual(equip, proves)
    rang = {
        1: range(1, 11),
        2: range(11, 21),
        3: range(21, 31)
    }[bloc]

    mancants = [str(pid) for pid in rang if str(pid) in proves and str(pid) not in res]
    if mancants:
        await update.message.reply_text(f"❓ Proves pendents al bloc {bloc}: {', '.join(mancants)}")
    else:
        # Missatge general quan han completat el bloc però no la prova final
        await update.message.reply_text(f"🎉 Totes les proves del bloc {bloc} han estat contestades!")

        # Missatges i accions específiques per bloc
        if bloc == 1:
            await update.message.reply_text("🎺 Ta-xàn! Enhorabona, has completat el primer bloc, aquí tens el segon!")
            await llistar_proves(update, context)
        elif bloc == 2:
            await update.message.reply_text("🎉 Ta-xaaaaan! Gairebé ho teniu! Aquí teniu les últimes instruccions per al tercer bloc:")
            await llistar_proves(update, context)
        elif bloc == 3:
            # Missatge abans de la prova 31
            await update.message.reply_text(
                "🎆🎆🎆 TAA-TAA-TAA-XAAAAAN!!! 🎆🎆🎆\n\n"
                "🏁 FELICITATS!! Heu completat les 30 proves!\n\n"
                "🏔️ Però encara queda LA PROVA DEFINITIVA: envieu la resposta 31 per completar la ginkana."
            )


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    equips_data = {}
    if os.path.exists(PUNTS_CSV):
        with open(PUNTS_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                e = row["equip"]
                equips_data.setdefault(e, {"punts": 0, "contestades": 0, "correctes": 0})
                equips_data[e]["contestades"] += 1
                if row["estat"] == "VALIDADA":
                    equips_data[e]["punts"] += int(row["punts"])
                    equips_data[e]["correctes"] += 1

    if not equips_data:
        await update.message.reply_text("No hi ha punts registrats encara.")
        return

    sorted_equips = sorted(equips_data.items(), key=lambda x: x[1]["punts"], reverse=True)
    msg = "🏆 Classificació provisional:\n\n"
    for i, (equip, data) in enumerate(sorted_equips, start=1):
        msg += (
            f"{i}. {equip} - {data['punts']} punts "
            f"({data['correctes']} correctes de {data['contestades']} respostes)\n"
        )
    await update.message.reply_text(msg)

# ----------------------------
# Handler respostes (actualitzat)
# ----------------------------
async def resposta_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text.lower().startswith("resposta"):
        return

    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Format correcte: resposta <id> <text>")
        return

    prova_id = parts[1]
    resposta = parts[2]

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
        await update.message.reply_text("❌ Només el portaveu de l’equip pot enviar respostes.")
        return

    if ja_resposta(equip, prova_id):
        await update.message.reply_text(f"⚠️ L'equip '{equip}' ja ha respost la prova {prova_id}.")
        return

    # Bloc abans de registrar la nova resposta
    bloc_anterior = bloc_actual(equip, proves)

    prova = proves[prova_id]
    punts, estat = validate_answer(prova, resposta)
    guardar_submission(equip, prova_id, resposta, punts, estat)

    await update.message.reply_text(f"✅ Resposta registrada per l'equip '{equip}': {estat}. Punts: {punts}")

    # Bloc després d’afegir la resposta
    bloc_nou = bloc_actual(equip, proves)

    # Missatges especials de canvi de bloc
    if bloc_nou == 2 and bloc_anterior == 1:
        await update.message.reply_text("🎺 Ta-xàn! Enhorabona, has completat el primer bloc, aquí tens el segon!")
        await llistar_proves(update, context)
    elif bloc_nou == 3 and bloc_anterior == 2:
        await update.message.reply_text("🎉 Ta-xaaaaan! Gairebé ho teniu! Aquí teniu les últimes instruccions:")
        await llistar_proves(update, context)

    # Comprovació addicional per mostrar el missatge abans de la prova final
    res = respostes_equip(equip)
    if all(str(i) in res for i in range(21, 31)) and "31" not in res:
        await update.message.reply_text(
            "🎆🎆🎆 TAA-TAA-TAA-XAAAAAN!!! 🎆🎆🎆\n\n"
            "🏁 FELICITATS!! Heu completat les 30 proves!\n\n"
            "🏔️ Però encara queda LA PROVA DEFINITIVA: envieu la resposta 31 per completar la ginkana. La trobareu a la façana de l'Esgésia de 19:01 a 19:02. No feu tard!"
        )

    # Missatge especial si és la prova final (tipus final_joc)
    if prova["tipus"] == "final_joc":
        await update.message.reply_text(
            "🏆 Heu completat la **Primera Gran Ginkana de la Fira del Raure** 🎉\n\n"
            "📊 Trobareu els resultats amb la comanda /ranking\n\n\n\n"
            "🙌 Moltes gràcies a tots per participar!\n\n"
            "🐔 Lo Corral associació cultural, Ginestar, 28 de setembre de 2025."
        )

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

if __name__ == "__main__":
    main()
