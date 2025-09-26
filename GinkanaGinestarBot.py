from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# ----------------------------
# Funcions auxiliars (definides com a placeholders)
# ----------------------------
def carregar_proves():
    # Retorna un diccionari amb totes les proves
    pass

def carregar_equips():
    # Retorna un diccionari amb equips i info: portaveu, jugadors, hora_inscripcio
    pass

def ja_resposta(equip, prova_id):
    # Retorna True si l'equip ja ha respost aquesta prova
    pass

def bloc_actual(equip, proves):
    # Retorna l'actual bloc de l'equip segons les proves completades
    pass

def validate_answer(prova, resposta):
    # Retorna (punts, estat) segons si la resposta és correcta
    pass

def guardar_submission(equip, prova_id, resposta, punts, estat):
    # Guarda la resposta al sistema
    pass

def respostes_equip(equip):
    # Retorna un diccionari amb les respostes de l'equip
    pass

async def llistar_proves(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mostra les proves disponibles
    await update.message.reply_text("📋 Llistat de proves...")

# ----------------------------
# Handler per a respostes
# ----------------------------
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

    equip = next(
        (e for e, info in equips.items() if info["portaveu"] in [username, firstname]),
        None
    )

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
    if bloc_nou > bloc_anterior:
        if bloc_nou == 2:
            await update.message.reply_text(
                "🎺 Ta-xàn! Enhorabona, has completat el primer bloc, aquí tens el segon!")
        elif bloc_nou == 3:
            await update.message.reply_text(
                "🎉 Ta-ta-ta-xaaaaàn! Gairebé ho teniu! Aquí teniu les últimes instruccions per al tercer bloc:")
        await llistar_proves(update, context)

    res = respostes_equip(equip)
    if all(str(i) in res.keys() for i in range(21,31)) and "31" not in res:
        await update.message.reply_text(
            "🎆🎆🎆 TAA-TAA-TAA-XAAAAAN!!! 🎆🎆🎆\n\n"
            "🏁 FELICITATS!! Heu completat les 30 proves!\n\n"
            "🏔️ Però encara queda LA PROVA DEFINITIVA: envieu la resposta 31 per completar la ginkana.")
    if prova.get("tipus") == "final_joc":
        await update.message.reply_text(
            "🏆 Heu completat la **Primera Gran Ginkana de la Fira del Raure** 🎉\n\n"
            "📊 Trobareu els resultats amb la comanda /ranking\n\n\n\n"
            "🙌 Moltes gràcies a tots per participar!\n\n"
            "🐔 Lo Corral associació cultural, Ginestar, 28 de setembre de 2025.")

# ----------------------------
# Comanda /r30
# ----------------------------
async def mostrar_equips_resum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    equips = carregar_equips()
    proves = carregar_proves()
    records_sheet = sheet.get_all_records()  # Assumim que ja està inicialitzat

    if not equips:
        await update.message.reply_text("❌ No hi ha equips registrats encara.")
        return

    msg = "📋 Llistat d'equips (resum):\n\n"
    for e, info in equips.items():
        hora_inscripcio = info.get("hora_inscripcio", "Desconeguda")

        # Bloc 3
        respostes = respostes_equip(e)
        bloc3_ids = range(21, 31)
        bloc3_existents = [pid for pid in bloc3_ids if str(pid) in proves]

        temps_bloc3 = []
        for row in records_sheet:
            if row["equip"] == e and int(row["prova_id"]) in bloc3_existents:
                try:
                    temps_bloc3.append(datetime.strptime(row["hora"], "%Y-%m-%d %H:%M:%S"))
                except:
                    pass

        if all(str(pid) in respostes for pid in bloc3_existents):
            complet_bloc3 = max(temps_bloc3).strftime("%H:%M:%S") if temps_bloc3 else "Desconeguda"
        else:
            complet_bloc3 = "No completat"

        msg += f"{e} | @{info['portaveu']} | {', '.join(info['jugadors'])} | Inscripció: {hora_inscripcio} | Bloc3: {complet_bloc3}\n"

    await update.message.reply_text(msg)

# ----------------------------
# Comandes /start i /ajuda
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Benvingut a la Ginkana!")

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start - Inici\n/ajuda - Comandes\n/inscriure - Inscripció\n/proves - Llistar proves\n/ranking - Classificació\n/r30 - Resum equips")

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
    app.add_handler(CommandHandler("r30", mostrar_equips_resum))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, resposta_handler))
    print("✅ Bot Ginkana en marxa...")
    app.run_polling()

if __name__=="__main__":
    main()
