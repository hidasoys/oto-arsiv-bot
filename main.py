import os
import re
from datetime import datetime

from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME")

records_cache = {}

ASK_SASE, ASK_ACIKLAMA, ASK_KM, ASK_IS_EMRI, ASK_FIYAT = range(5)


def normalize_plate(value):
    return re.sub(r"[\s\-.]", "", str(value or "").upper())


def parse_price(value):
    text = str(value or "0")
    text = text.replace("TL", "").replace("₺", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def money(value):
    return f"{value:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")


def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    return spreadsheet.worksheet(SHEET_NAME)


def get_records_by_plate(plate):
    sheet = get_sheet()
    rows = sheet.get_all_values()
    records = []

    for index, row in enumerate(rows[1:], start=2):
        row += [""] * (8 - len(row))

        if normalize_plate(row[0]) == plate:
            records.append({
                "row": index,
                "plaka": row[0],
                "sase": row[1],
                "aciklama": row[2],
                "saat": row[3],
                "tarih": row[4],
                "is_emri": row[5],
                "kilometre": row[6],
                "fiyat": row[7] or "-"
            })

    return records


def build_list_message(plate, records):
    list_records = list(reversed(records))
    sase = list_records[0]["sase"] or "-"

    return (
        f"🚗 Plaka: {plate}\n"
        f"🔩 Şase No: {sase}\n"
        f"📌 Toplam Kayıt: {len(list_records)}\n\n"
        f"Kayıt seçin:"
    )


def build_list_keyboard(plate, records):
    list_records = list(reversed(records))
    keyboard = []

    for i, record in enumerate(list_records, start=1):
        keyboard.append([
            InlineKeyboardButton(
                text=f"{i}) {record['tarih']} - {record['kilometre']} KM",
                callback_data=f"detail|{plate}|{record['row']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ Yeni Servis Kaydı Ekle",
            callback_data=f"new|{plate}"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def build_detail_message(record):
    return (
        "📌 Servis Kaydı Detayı\n\n"
        f"🚗 Plaka: {record['plaka']}\n"
        f"📅 Tarih: {record['tarih']}\n"
        f"⏰ Saat: {record['saat']}\n"
        f"🧾 İş Emri: {record['is_emri']}\n"
        f"🛣 Kilometre: {record['kilometre']}\n"
        f"💰 Fiyat: {record['fiyat']}\n\n"
        f"📝 Açıklama:\n{record['aciklama']}"
    )


def create_service_pdf(record):
    os.makedirs("pdfler", exist_ok=True)

    safe_plate = normalize_plate(record["plaka"])
    filename = f"servis_fisi_{safe_plate}_{record['row']}.pdf"
    filepath = os.path.join("pdfler", filename)

    pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))

    price = parse_price(record["fiyat"])
    kdv = price * 0.20
    total = price + kdv

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    blue = colors.HexColor("#003B7A")
    gray = colors.HexColor("#D9D9D9")

    c.setFillColor(gray)
    c.rect(0, height - 230, width, 230, fill=1, stroke=0)

    c.setFillColor(blue)
    c.rect(width - 160, height - 80, 150, 40, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.rect(width - 160, height - 105, 80, 35, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Arial-Bold", 22)
    c.drawString(110, height - 75, "OTO SERVİS KAYDI")

    c.setFont("Arial-Bold", 13)
    c.drawString(55, height - 160, str(record["plaka"]))
    c.setStrokeColor(blue)
    c.setLineWidth(2)
    c.line(55, height - 170, 240, height - 170)

    c.setFont("Arial-Bold", 11)
    c.drawString(55, height - 200, str(record["sase"]))
    c.setStrokeColor(blue)
    c.line(55, height - 210, 260, height - 210)

    table_y = height - 300

    c.setFillColor(blue)
    c.rect(50, table_y, 75, 35, fill=1, stroke=0)
    c.rect(125, table_y, 240, 35, fill=1, stroke=0)

    c.setFillColor(gray)
    c.rect(365, table_y, 95, 35, fill=1, stroke=0)
    c.rect(460, table_y, 65, 35, fill=1, stroke=0)
    c.rect(525, table_y, 70, 35, fill=1, stroke=0)

    c.setFont("Arial-Bold", 10)

    c.setFillColor(colors.white)
    c.drawCentredString(87, table_y + 13, "NO")
    c.drawCentredString(245, table_y + 13, "İŞ TANIMI")

    c.setFillColor(colors.black)
    c.drawCentredString(412, table_y + 13, "FİYAT")
    c.drawCentredString(492, table_y + 13, "ADET")
    c.drawCentredString(560, table_y + 13, "TOPLAM")

    row_y = table_y - 45

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)

    c.rect(50, row_y, 75, 45, fill=0)
    c.rect(125, row_y, 240, 45, fill=0)
    c.rect(365, row_y, 95, 45, fill=0)
    c.rect(460, row_y, 65, 45, fill=0)
    c.rect(525, row_y, 70, 45, fill=0)

    c.setFont("Arial", 10)
    c.drawCentredString(87, row_y + 18, "01")

    description = str(record["aciklama"])[:90]
    c.drawString(135, row_y + 24, description[:45])
    if len(description) > 45:
        c.drawString(135, row_y + 10, description[45:90])

    c.drawCentredString(412, row_y + 18, money(price))
    c.drawCentredString(492, row_y + 18, "1")
    c.drawCentredString(560, row_y + 18, money(price))

    summary_x = 390
    summary_y = 240

    c.setFont("Arial-Bold", 11)
    c.drawString(summary_x, summary_y, "TOPLAM:")
    c.drawRightString(565, summary_y, money(price))

    c.drawString(summary_x, summary_y - 22, "KDV:")
    c.drawRightString(565, summary_y - 22, money(kdv))

    c.drawString(summary_x, summary_y - 44, "G.TOPLAM:")
    c.drawRightString(565, summary_y - 44, money(total))

    c.setFillColor(blue)
    c.rect(summary_x, summary_y - 85, 95, 22, fill=1, stroke=0)

    c.setFillColor(gray)
    c.rect(summary_x + 95, summary_y - 85, 95, 22, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Arial-Bold", 12)
    c.drawCentredString(summary_x + 142, summary_y - 80, money(total))

    c.setFillColor(blue)
    c.rect(0, 55, 145, 25, fill=1, stroke=0)
    c.rect(0, 30, 170, 25, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Arial", 8)
    c.drawString(50, 20, f"Oluşturma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    c.save()
    return filepath


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 Oto Arşiv Bot aktif.\n\n"
        "Plaka yazarak servis geçmişini sorgulayabilirsiniz.\n\n"
        "Örnek: 54ABC123"
    )


async def handle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text.lower() == "/start":
        await start(update, context)
        return

    plate = normalize_plate(text)
    records = get_records_by_plate(plate)

    if not records:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="➕ Yeni Kayıt Oluştur", callback_data=f"new|{plate}")]
        ])

        await update.message.reply_text(
            f"🚗 {plate} için kayıt bulunamadı.\n\n"
            f"Yeni servis kaydı oluşturmak ister misiniz?",
            reply_markup=keyboard
        )
        return

    records_cache[plate] = records

    await update.message.reply_text(
        build_list_message(plate, records),
        reply_markup=build_list_keyboard(plate, records)
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("detail|"):
        _, plate, row_str = data.split("|")
        row_number = int(row_str)

        records = records_cache.get(plate)

        if not records:
            records = get_records_by_plate(plate)
            records_cache[plate] = records

        record = next((r for r in records if r["row"] == row_number), None)

        if not record:
            await query.edit_message_text("⚠️ Kayıt bulunamadı. Plakayı tekrar sorgulayın.")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="📄 PDF Servis Fişi Oluştur",
                    callback_data=f"pdf|{plate}|{record['row']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Geri Dön",
                    callback_data=f"back|{plate}"
                )
            ]
        ])

        await query.edit_message_text(
            build_detail_message(record),
            reply_markup=keyboard
        )
        return

    if data.startswith("pdf|"):
        _, plate, row_str = data.split("|")
        row_number = int(row_str)

        records = records_cache.get(plate)

        if not records:
            records = get_records_by_plate(plate)
            records_cache[plate] = records

        record = next((r for r in records if r["row"] == row_number), None)

        if not record:
            await query.message.reply_text("⚠️ PDF oluşturulamadı. Kayıt bulunamadı.")
            return

        filepath = create_service_pdf(record)

        with open(filepath, "rb") as pdf_file:
            await query.message.reply_document(
                document=pdf_file,
                filename=os.path.basename(filepath),
                caption="📄 Servis fişi oluşturuldu."
            )
        return

    if data.startswith("back|"):
        _, plate = data.split("|")

        records = records_cache.get(plate)

        if not records:
            records = get_records_by_plate(plate)
            records_cache[plate] = records

        await query.edit_message_text(
            build_list_message(plate, records),
            reply_markup=build_list_keyboard(plate, records)
        )
        return


async def start_new_record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, plate = query.data.split("|")
    existing_records = get_records_by_plate(plate)

    context.user_data["new_record"] = {
        "plaka": plate
    }

    if existing_records:
        first_sase = existing_records[0]["sase"]
        context.user_data["new_record"]["sase"] = first_sase

        await query.message.reply_text(
            f"➕ Yeni servis kaydı oluşturuluyor.\n\n"
            f"🚗 Plaka: {plate}\n"
            f"🔩 Şase No: {first_sase}\n\n"
            f"Açıklamayı yazın:"
        )

        return ASK_ACIKLAMA

    await query.message.reply_text(
        f"➕ Yeni servis kaydı oluşturuluyor.\n\n"
        f"🚗 Plaka: {plate}\n\n"
        f"Şase numarasını yazın:"
    )

    return ASK_SASE


async def ask_sase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_record"]["sase"] = update.message.text.strip()
    await update.message.reply_text("Açıklamayı yazın:")
    return ASK_ACIKLAMA


async def ask_aciklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_record"]["aciklama"] = update.message.text.strip()
    await update.message.reply_text("Kilometre bilgisini yazın:")
    return ASK_KM


async def ask_km(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_record"]["kilometre"] = update.message.text.strip()
    await update.message.reply_text("İş emri numarasını yazın:")
    return ASK_IS_EMRI


async def ask_is_emri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_record"]["is_emri"] = update.message.text.strip()
    await update.message.reply_text("Fiyat bilgisini yazın:")
    return ASK_FIYAT


async def ask_fiyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_record"]["fiyat"] = update.message.text.strip()

    data = context.user_data["new_record"]
    now = datetime.now()
    tarih = now.strftime("%d.%m.%Y")
    saat = now.strftime("%H:%M")

    sheet = get_sheet()

    sheet.append_row([
        data["plaka"],
        data["sase"],
        data["aciklama"],
        saat,
        tarih,
        data["is_emri"],
        data["kilometre"],
        data["fiyat"]
    ])

    records = get_records_by_plate(data["plaka"])
    records_cache[data["plaka"]] = records

    await update.message.reply_text(
        "✅ Yeni servis kaydı oluşturuldu.\n\n"
        f"🚗 Plaka: {data['plaka']}\n"
        f"🔩 Şase No: {data['sase']}\n"
        f"📅 Tarih: {tarih}\n"
        f"⏰ Saat: {saat}\n"
        f"🧾 İş Emri: {data['is_emri']}\n"
        f"🛣 Kilometre: {data['kilometre']}\n"
        f"💰 Fiyat: {data['fiyat']}\n\n"
        f"📝 Açıklama:\n{data['aciklama']}"
    )

    context.user_data.pop("new_record", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_record", None)
    await update.message.reply_text("❌ Yeni kayıt oluşturma işlemi iptal edildi.")
    return ConversationHandler.END


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN .env içinde boş.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    new_record_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_new_record, pattern=r"^new\|")],
        states={
            ASK_SASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sase)],
            ASK_ACIKLAMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_aciklama)],
            ASK_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_km)],
            ASK_IS_EMRI: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_is_emri)],
            ASK_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fiyat)],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^/iptal$"), cancel)],
    )

    app.add_handler(new_record_conversation)
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plate))
    app.add_handler(MessageHandler(filters.COMMAND, handle_plate))

    print("Bot çalışıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()