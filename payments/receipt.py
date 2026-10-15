"""Génération du reçu PDF (maquette Bujito Digital)."""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import qrcode
from django.utils import timezone
from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

YELLOW = HexColor("#FBD600")
DARK = HexColor("#111111")
GREY_BAR = HexColor("#2B2B2B")
GREY_BOX = HexColor("#F2F2F2")
GREY_TEXT = HexColor("#666666")
GREEN = HexColor("#28A745")
ORANGE_M = HexColor("#FF7900")

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS / "logo.png"

_FONTS_READY = False


def _ensure_fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular = [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    bold = [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for path in regular:
        try:
            pdfmetrics.registerFont(TTFont("ReceiptSans", path))
            break
        except Exception:
            continue
    for path in bold:
        try:
            pdfmetrics.registerFont(TTFont("ReceiptSans-Bold", path))
            break
        except Exception:
            continue
    _FONTS_READY = True


def _font(bold: bool = False) -> str:
    _ensure_fonts()
    if bold and "ReceiptSans-Bold" in pdfmetrics.getRegisteredFontNames():
        return "ReceiptSans-Bold"
    if "ReceiptSans" in pdfmetrics.getRegisteredFontNames():
        return "ReceiptSans"
    return "Helvetica-Bold" if bold else "Helvetica"


def _money(amount, currency: str) -> str:
    try:
        value = Decimal(str(amount))
    except Exception:
        value = Decimal("0")
    code = (currency or "USD").upper()
    if code in {"CDF", "FCFA", "XOF"}:
        return f"{value.quantize(Decimal('1'))} {code}"
    if code == "CNY":
        return f"{value.quantize(Decimal('0.01'))} ¥"
    # Format FR-like : 50,00 $
    q = value.quantize(Decimal("0.01"))
    text = f"{q}".replace(".", ",")
    return f"{text} $"


def _service_copy(payment, meta: dict) -> tuple[str, str, str]:
    tracking = ""
    if payment.order_id:
        return (
            "Achat de produits en Chine",
            "Commande et suivi de vos produits en Chine",
            f"CMD-{payment.order_id}",
        )
    if payment.expedition_id:
        return (
            "Expédition / Groupage",
            f"Expédition #{payment.expedition_id}",
            f"EXP-{payment.expedition_id}",
        )
    if meta.get("type") == "money_transfer":
        return (
            "Transfert d'argent",
            meta.get("beneficiary_name") or "Transfert",
            payment.reference or "",
        )
    return "Paiement Bujito", "Service Bujito Digital", ""


def _rounded_rect(c, x, y, w, h, r, fill=None, stroke=None, stroke_width=0.5):
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_width)
    p = c.beginPath()
    p.moveTo(x + r, y)
    p.lineTo(x + w - r, y)
    p.arcTo(x + w - 2 * r, y, x + w, y + 2 * r, -90, 90)
    p.lineTo(x + w, y + h - r)
    p.arcTo(x + w - 2 * r, y + h - 2 * r, x + w, y + h, 0, 90)
    p.lineTo(x + r, y + h)
    p.arcTo(x, y + h - 2 * r, x + 2 * r, y + h, 90, 90)
    p.lineTo(x, y + r)
    p.arcTo(x, y, x + 2 * r, y + 2 * r, 180, 90)
    p.close()
    if fill is not None and stroke is not None:
        c.drawPath(p, fill=1, stroke=1)
    elif fill is not None:
        c.drawPath(p, fill=1, stroke=0)
    else:
        c.drawPath(p, fill=0, stroke=1)
    c.restoreState()


def _draw_logo_mark(c, x, y, size=22):
    """Cercle jaune « bu. »."""
    c.setFillColor(YELLOW)
    c.circle(x + size / 2, y + size / 2, size / 2, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(_font(True), size * 0.42)
    c.drawCentredString(x + size / 2, y + size * 0.32, "bu.")


def _draw_brand(c, x, y, mark_size=22, title_size=14):
    _draw_logo_mark(c, x, y, mark_size)
    c.setFont(_font(True), title_size)
    c.setFillColor(white)
    c.drawString(x + mark_size + 6, y + mark_size * 0.55, "Bujito")
    w = c.stringWidth("Bujito", _font(True), title_size)
    c.setFillColor(YELLOW)
    c.drawString(x + mark_size + 6 + w + 3, y + mark_size * 0.55, "Digital")
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.setFont(_font(), 7)
    c.drawString(
        x + mark_size + 6,
        y + 2,
        "Vos services digitaux, notre priorité !",
    )


def _draw_brand_dark(c, x, y, mark_size=20, title_size=12):
    _draw_logo_mark(c, x, y, mark_size)
    c.setFont(_font(True), title_size)
    c.setFillColor(DARK)
    c.drawString(x + mark_size + 6, y + mark_size * 0.55, "Bujito")
    w = c.stringWidth("Bujito", _font(True), title_size)
    c.setFillColor(HexColor("#C9A000"))
    c.drawString(x + mark_size + 6 + w + 3, y + mark_size * 0.55, "Digital")
    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 6.5)
    c.drawString(
        x + mark_size + 6,
        y + 2,
        "Vos services digitaux, notre priorité !",
    )


def _qr_image(payload: str) -> ImageReader:
    qr = qrcode.QRCode(version=2, box_size=6, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def build_receipt_pdf(payment) -> bytes:
    meta = payment.provider_raw_response if isinstance(payment.provider_raw_response, dict) else {}
    service_amount = meta.get("service_amount") or meta.get("recharge_amount")
    processing_fee = meta.get("processing_fee") or meta.get("recharge_fee") or "0"
    try:
        fee = Decimal(str(processing_fee))
    except Exception:
        fee = Decimal("0")
    try:
        total = Decimal(str(payment.amount))
    except Exception:
        total = Decimal("0")
    if service_amount is None:
        service_amount = total - fee
    else:
        try:
            service_amount = Decimal(str(service_amount))
        except Exception:
            service_amount = total - fee

    user = payment.user
    client_name = (getattr(user, "full_name", "") or "").strip() or user.email
    phone = getattr(user, "phone_number", "") or payment.phone_number or "—"
    email = user.email or "—"
    service_label, description, tracking = _service_copy(payment, meta)
    method = getattr(payment.method, "name", None) or getattr(payment.method, "code", "—")
    method_code = (getattr(payment.method, "code", "") or "").lower()
    paid_at = payment.updated_at or payment.created_at or timezone.now()
    try:
        local_dt = timezone.localtime(paid_at)
    except Exception:
        local_dt = paid_at
    months = (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )
    date_label = (
        f"{local_dt.day} {months[local_dt.month - 1]} {local_dt.year} "
        f"à {local_dt.strftime('%H:%M')}"
    )
    receipt_no = payment.reference or f"BD{payment.pk}"
    tx_no = payment.external_id or payment.reference or str(payment.pk)

    buf = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buf, pagesize=A4)
    margin = 18 * mm

    # --- Header noir ---
    header_h = 38 * mm
    c.setFillColor(DARK)
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    # Accents jaunes coins
    c.setFillColor(YELLOW)
    path = c.beginPath()
    path.moveTo(0, height)
    path.lineTo(28 * mm, height)
    path.lineTo(0, height - 18 * mm)
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    path = c.beginPath()
    path.moveTo(width, height)
    path.lineTo(width - 28 * mm, height)
    path.lineTo(width, height - 18 * mm)
    path.close()
    c.drawPath(path, fill=1, stroke=0)

    _draw_brand(c, margin, height - 28 * mm, mark_size=24, title_size=15)

    services = [
        ("●", "Achat en Chine"),
        ("●", "Commande en ligne"),
        ("●", "Assistance & Conseils"),
        ("●", "Paiement sécurisé"),
    ]
    sy = height - 16 * mm
    for icon, label in services:
        c.setFillColor(YELLOW)
        c.setFont(_font(True), 8)
        c.drawRightString(width - margin - 55, sy, icon)
        c.setFillColor(white)
        c.setFont(_font(), 8)
        c.drawRightString(width - margin, sy, label)
        sy -= 11

    # --- Titre + badge PAYÉ ---
    y = height - header_h - 18 * mm
    c.setFillColor(DARK)
    c.setFont(_font(True), 18)
    c.drawString(margin + 18, y, "REÇU DE PAIEMENT")
    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 9)
    c.drawString(margin + 18, y - 12, "MERCI POUR VOTRE CONFIANCE !")
    # petite icône reçu
    c.setStrokeColor(DARK)
    c.setLineWidth(1.2)
    c.rect(margin, y - 4, 12, 16, fill=0, stroke=1)
    c.line(margin + 3, y + 8, margin + 9, y + 8)
    c.line(margin + 3, y + 4, margin + 9, y + 4)

    badge_w, badge_h = 42 * mm, 10 * mm
    bx = width - margin - badge_w
    by = y - 4
    _rounded_rect(c, bx, by, badge_w, badge_h, 5 * mm, fill=YELLOW)
    c.setFillColor(DARK)
    c.circle(bx + 7 * mm, by + badge_h / 2, 3.2 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(_font(True), 9)
    c.drawCentredString(bx + 7 * mm, by + badge_h / 2 - 3, "✓")
    c.setFillColor(DARK)
    c.setFont(_font(True), 12)
    c.drawString(bx + 13 * mm, by + badge_h / 2 - 4, "PAYÉ")

    # --- Infos client ---
    y = by - 18 * mm
    left_x = margin
    lines = [
        ("Numéro de reçu :", receipt_no),
        ("Nom du client :", client_name),
        ("Téléphone :", phone),
        ("Email :", email),
    ]
    row_y = y
    for label, value in lines:
        c.setFillColor(DARK)
        c.setFont(_font(), 9)
        c.drawString(left_x, row_y, label)
        c.setFont(_font(True), 9)
        c.drawString(left_x + 38 * mm, row_y, str(value))
        row_y -= 12

    # séparateur vertical + logo droit
    mid_x = width / 2 + 8 * mm
    c.setStrokeColor(HexColor("#DDDDDD"))
    c.setLineWidth(0.8)
    c.line(mid_x - 6 * mm, y + 6, mid_x - 6 * mm, row_y + 8)
    _draw_brand_dark(c, mid_x, y - 10, mark_size=20, title_size=11)

    # --- DÉTAIL DU SERVICE ---
    box_top = row_y - 8 * mm
    box_x = margin
    box_w = width - 2 * margin
    header_bar_h = 9 * mm
    body_h = 38 * mm
    total_h = 11 * mm
    box_h = header_bar_h + body_h + total_h

    _rounded_rect(c, box_x, box_top - box_h, box_w, box_h, 3 * mm, fill=GREY_BOX)
    c.setFillColor(GREY_BAR)
    c.roundRect(box_x, box_top - header_bar_h, box_w, header_bar_h, 3 * mm, fill=1, stroke=0)
    # couvrir coins bas de la barre
    c.rect(box_x, box_top - header_bar_h, box_w, 3 * mm, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 4 * mm, box_top - 6.2 * mm, "⚙")
    c.setFillColor(white)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 10 * mm, box_top - 6.2 * mm, "DÉTAIL DU SERVICE")

    detail_y = box_top - header_bar_h - 8 * mm
    details = [
        ("Service payé :", service_label),
        ("Description :", description),
    ]
    if tracking:
        details.append(("Référence / suivi :", tracking))
    details.extend(
        [
            ("Montant :", _money(service_amount, payment.currency)),
            ("Frais de traitement :", _money(fee, payment.currency)),
        ]
    )
    for label, value in details:
        c.setFillColor(DARK)
        c.setFont(_font(), 9)
        c.drawString(box_x + 5 * mm, detail_y, label)
        c.setFont(_font(True), 9)
        c.drawString(box_x + 42 * mm, detail_y, str(value))
        detail_y -= 11

    # barre jaune total
    ty = box_top - box_h + 2 * mm
    _rounded_rect(c, box_x + 3 * mm, ty, box_w - 6 * mm, total_h - 3 * mm, 4 * mm, fill=YELLOW)
    c.setFillColor(DARK)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 10 * mm, ty + 4, "MONTANT TOTAL PAYÉ")
    c.setFont(_font(True), 13)
    total_txt = _money(total, payment.currency)
    c.drawRightString(box_x + box_w - 8 * mm, ty + 3.5, total_txt)

    # --- DÉTAIL DU PAIEMENT ---
    pay_top = ty - 10 * mm
    pay_body_h = 36 * mm
    pay_h = header_bar_h + pay_body_h
    _rounded_rect(c, box_x, pay_top - pay_h, box_w, pay_h, 3 * mm, fill=GREY_BOX)
    c.setFillColor(GREY_BAR)
    c.roundRect(box_x, pay_top - header_bar_h, box_w, header_bar_h, 3 * mm, fill=1, stroke=0)
    c.rect(box_x, pay_top - header_bar_h, box_w, 3 * mm, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 4 * mm, pay_top - 6.2 * mm, "💳")
    c.setFillColor(white)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 12 * mm, pay_top - 6.2 * mm, "DÉTAIL DU PAIEMENT")

    py = pay_top - header_bar_h - 9 * mm
    c.setFillColor(DARK)
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Mode de paiement :")
    c.setFont(_font(True), 9)
    c.drawString(box_x + 42 * mm, py, str(method))
    if "orange" in method_code or "orange" in str(method).lower():
        c.setFillColor(ORANGE_M)
        c.roundRect(box_x + box_w - 38 * mm, py - 2, 30 * mm, 8 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(_font(True), 7)
        c.drawCentredString(box_x + box_w - 23 * mm, py, "Orange Money")

    py -= 13
    c.setFillColor(DARK)
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Numéro de transaction :")
    c.setFont(_font(True), 9)
    c.drawString(box_x + 48 * mm, py, str(tx_no))
    py -= 13
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Date de paiement :")
    c.setFont(_font(True), 9)
    c.drawString(box_x + 42 * mm, py, date_label)
    py -= 14
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Statut :")
    status_w = 42 * mm
    _rounded_rect(c, box_x + 28 * mm, py - 3, status_w, 8 * mm, 4 * mm, fill=GREEN)
    c.setFillColor(white)
    c.setFont(_font(True), 8)
    c.drawCentredString(box_x + 28 * mm + status_w / 2, py - 0.5, "✓  Paiement confirmé")

    # --- QR + Merci ---
    foot_y = pay_top - pay_h - 8 * mm
    verify_url = f"https://www.bujitodigital.com/verify/{receipt_no}"
    qr = _qr_image(verify_url)
    qr_size = 28 * mm
    c.drawImage(qr, margin, foot_y - qr_size, qr_size, qr_size, mask="auto")
    # petit logo au centre du QR
    c.setFillColor(YELLOW)
    c.circle(margin + qr_size / 2, foot_y - qr_size / 2, 5 * mm, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(_font(True), 7)
    c.drawCentredString(margin + qr_size / 2, foot_y - qr_size / 2 - 2, "bu.")

    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 8)
    text_x = margin + qr_size + 4 * mm
    c.drawString(text_x, foot_y - 10 * mm, "Scannez ce QR code pour vérifier")
    c.drawString(text_x, foot_y - 14 * mm, "l'authenticité de votre reçu.")

    c.setStrokeColor(HexColor("#DDDDDD"))
    c.setLineWidth(0.8)
    c.line(width / 2 + 5 * mm, foot_y - 2 * mm, width / 2 + 5 * mm, foot_y - qr_size + 2 * mm)

    c.setFillColor(DARK)
    c.setFont(_font(True), 22)
    c.drawString(width / 2 + 12 * mm, foot_y - 10 * mm, "Merci !")
    c.setStrokeColor(YELLOW)
    c.setLineWidth(2.5)
    c.line(width / 2 + 12 * mm, foot_y - 12 * mm, width / 2 + 40 * mm, foot_y - 12 * mm)
    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 8)
    c.drawString(width / 2 + 12 * mm, foot_y - 18 * mm, "Votre confiance nous motive !")
    c.drawString(width / 2 + 12 * mm, foot_y - 22 * mm, "Bujito Digital, toujours à vos côtés.")

    # --- Footer noir ---
    footer_h = 16 * mm
    c.setFillColor(DARK)
    c.rect(0, 0, width, footer_h, fill=1, stroke=0)
    c.setFillColor(YELLOW)
    path = c.beginPath()
    path.moveTo(width, 0)
    path.lineTo(width, 22 * mm)
    path.lineTo(width - 45 * mm, 0)
    path.close()
    c.drawPath(path, fill=1, stroke=0)

    c.setFillColor(YELLOW)
    c.setFont(_font(), 8)
    c.drawString(margin, 6 * mm, "☎  +243 858 850 051")
    c.drawCentredString(width / 2, 6 * mm, "🌐  www.bujitodigital.com")
    c.setFillColor(DARK)
    c.setFont(_font(True), 7)
    c.drawRightString(width - 4 * mm, 4 * mm, "Ensemble vers plus")
    c.drawRightString(width - 4 * mm, 1.5 * mm, "d'opportunités !")

    c.showPage()
    c.save()
    return buf.getvalue()


# Compat anciens imports / tests
def build_receipt_png(payment) -> bytes:
    """Deprecated : le reçu officiel est un PDF. Conservé pour compat."""
    return build_receipt_pdf(payment)
