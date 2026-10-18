"""Génération du reçu PDF (maquette Bujito Digital) — multi-pages, sans chevauchement."""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import qrcode
from django.utils import timezone
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

YELLOW = HexColor("#FBD600")
DARK = HexColor("#111111")
GREY_BAR = HexColor("#2B2B2B")
GREY_BOX = HexColor("#F2F2F2")
GREY_TEXT = HexColor("#666666")
GREEN = HexColor("#28A745")
ORANGE_M = HexColor("#FF7900")
LIGHT_LINE = HexColor("#DDDDDD")

ASSETS = Path(__file__).resolve().parent / "assets"
_FONTS_READY = False


def _ensure_fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    for path in (
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            pdfmetrics.registerFont(TTFont("ReceiptSans", path))
            break
        except Exception:
            continue
    for path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        try:
            pdfmetrics.registerFont(TTFont("ReceiptSans-Bold", path))
            break
        except Exception:
            continue
    _FONTS_READY = True


def _font(bold: bool = False) -> str:
    _ensure_fonts()
    names = pdfmetrics.getRegisteredFontNames()
    if bold and "ReceiptSans-Bold" in names:
        return "ReceiptSans-Bold"
    if "ReceiptSans" in names:
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
    q = value.quantize(Decimal("0.01"))
    return f"{str(q).replace('.', ',')} $"


def _service_copy(payment, meta: dict) -> tuple[str, str, str]:
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


def _extra_service_rows(meta: dict) -> list[tuple[str, str]]:
    """Lignes additionnelles (produits, note…) pour le détail service."""
    rows: list[tuple[str, str]] = []
    items = meta.get("product_items") or meta.get("items") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, start=1):
            if isinstance(item, dict):
                label = (item.get("description") or item.get("name") or f"Article {idx}").strip()
                qty = item.get("quantity") or item.get("qty") or 1
                price = item.get("price") or item.get("amount")
                value = f"x{qty}"
                if price is not None:
                    value = f"{value} · {_money(price, 'USD')}"
                rows.append((f"Article {idx} :", f"{label} ({value})"))
            else:
                rows.append((f"Article {idx} :", str(item)))
    note = (meta.get("note") or meta.get("admin_note") or "").strip()
    if note:
        rows.append(("Note :", note))
    return rows


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
    c.setFillColor(YELLOW)
    c.circle(x + size / 2, y + size / 2, size / 2, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(_font(True), max(6, size * 0.42))
    c.drawCentredString(x + size / 2, y + size * 0.32, "bu.")


def _draw_brand(c, x, y, mark_size=22, title_size=14, light=True):
    _draw_logo_mark(c, x, y, mark_size)
    c.setFont(_font(True), title_size)
    c.setFillColor(white if light else DARK)
    c.drawString(x + mark_size + 6, y + mark_size * 0.55, "Bujito")
    w = c.stringWidth("Bujito", _font(True), title_size)
    c.setFillColor(YELLOW if light else HexColor("#C9A000"))
    c.drawString(x + mark_size + 6 + w + 3, y + mark_size * 0.55, "Digital")
    c.setFillColor(Color(1, 1, 1, alpha=0.85) if light else GREY_TEXT)
    c.setFont(_font(), 7)
    c.drawString(x + mark_size + 6, y + 2, "Vos services digitaux, notre priorité !")


def _qr_image(payload: str) -> ImageReader:
    qr = qrcode.QRCode(version=2, box_size=6, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


class _ReceiptLayout:
    """Curseur Y + en-tête/pied de page + saut de page automatique."""

    def __init__(self, c: canvas.Canvas, width: float, height: float):
        self.c = c
        self.width = width
        self.height = height
        self.margin = 15 * mm
        self.footer_h = 16 * mm
        self.header_h = 30 * mm
        self.content_bottom = self.footer_h + 8 * mm
        self.y = height
        self.page = 1
        self._draw_header(full=True)
        self.y = height - self.header_h - 10 * mm

    def _draw_header(self, full: bool = True):
        c, w, h = self.c, self.width, self.height
        hh = self.header_h if full else 22 * mm
        c.setFillColor(DARK)
        c.rect(0, h - hh, w, hh, fill=1, stroke=0)
        c.setFillColor(YELLOW)
        path = c.beginPath()
        path.moveTo(0, h)
        path.lineTo(24 * mm, h)
        path.lineTo(0, h - 14 * mm)
        path.close()
        c.drawPath(path, fill=1, stroke=0)
        path = c.beginPath()
        path.moveTo(w, h)
        path.lineTo(w - 24 * mm, h)
        path.lineTo(w, h - 14 * mm)
        path.close()
        c.drawPath(path, fill=1, stroke=0)

        _draw_brand(
            c,
            self.margin,
            h - (26 * mm if full else 16 * mm),
            mark_size=22 if full else 16,
            title_size=14 if full else 11,
            light=True,
        )
        if full:
            services = (
                "Achat en Chine",
                "Commande en ligne",
                "Assistance & Conseils",
                "Paiement sécurisé",
            )
            sy = h - 12 * mm
            for label in services:
                c.setFillColor(YELLOW)
                c.setFont(_font(True), 8)
                # Décaler à gauche pour ne pas chevaucher le triangle jaune.
                c.drawRightString(w - self.margin - 70, sy, "●")
                c.setFillColor(white)
                c.setFont(_font(), 8)
                c.drawRightString(w - self.margin - 12, sy, label)
                sy -= 10
        else:
            c.setFillColor(white)
            c.setFont(_font(), 8)
            c.drawRightString(w - self.margin, h - 12 * mm, f"Page {self.page}")

    def _draw_footer(self):
        c, w = self.c, self.width
        c.setFillColor(DARK)
        c.rect(0, 0, w, self.footer_h, fill=1, stroke=0)
        c.setFillColor(YELLOW)
        path = c.beginPath()
        path.moveTo(w, 0)
        path.lineTo(w, 20 * mm)
        path.lineTo(w - 42 * mm, 0)
        path.close()
        c.drawPath(path, fill=1, stroke=0)
        c.setFillColor(YELLOW)
        c.setFont(_font(), 8)
        c.drawString(self.margin, 7 * mm, "+243 858 850 051")
        c.drawCentredString(w / 2, 7 * mm, "www.bujitodigital.com")
        c.setFillColor(DARK)
        c.setFont(_font(True), 7)
        c.drawRightString(w - 5 * mm, 5 * mm, "Ensemble vers plus")
        c.drawRightString(w - 5 * mm, 2 * mm, "d'opportunités !")

    def new_page(self):
        self._draw_footer()
        self.c.showPage()
        self.page += 1
        self._draw_header(full=False)
        self.y = self.height - 22 * mm - 12 * mm

    def ensure(self, needed: float):
        if self.y - needed < self.content_bottom:
            self.new_page()

    def space(self, amount: float):
        self.ensure(amount)
        self.y -= amount

    def finish(self):
        """Dessine le pied de page final sans ouvrir une page vide."""
        self._draw_footer()


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
    layout = _ReceiptLayout(c, width, height)
    margin = layout.margin
    content_w = width - 2 * margin
    label_w = 44 * mm

    # --- Titre + badge PAYÉ ---
    layout.ensure(18 * mm)
    y = layout.y
    c.setStrokeColor(DARK)
    c.setLineWidth(1.2)
    c.rect(margin, y - 2, 11, 14, fill=0, stroke=1)
    c.line(margin + 2.5, y + 8, margin + 8.5, y + 8)
    c.line(margin + 2.5, y + 4, margin + 8.5, y + 4)
    c.setFillColor(DARK)
    c.setFont(_font(True), 16)
    c.drawString(margin + 16, y, "REÇU DE PAIEMENT")
    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 8)
    c.drawString(margin + 16, y - 11, "MERCI POUR VOTRE CONFIANCE !")

    badge_w, badge_h = 38 * mm, 9 * mm
    bx = width - margin - badge_w
    by = y - 3
    _rounded_rect(c, bx, by, badge_w, badge_h, 4.5 * mm, fill=YELLOW)
    c.setFillColor(DARK)
    c.circle(bx + 6 * mm, by + badge_h / 2, 2.8 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(_font(True), 8)
    c.drawCentredString(bx + 6 * mm, by + badge_h / 2 - 2.5, "✓")
    c.setFillColor(DARK)
    c.setFont(_font(True), 11)
    c.drawString(bx + 11 * mm, by + badge_h / 2 - 3.5, "PAYÉ")
    layout.y = y - 18 * mm

    # --- Infos client ---
    layout.ensure(32 * mm)
    info_top = layout.y
    client_rows = [
        ("Numéro de reçu :", str(receipt_no)),
        ("Nom du client :", str(client_name)),
        ("Téléphone :", str(phone)),
        ("Email :", str(email)),
    ]
    row_y = info_top
    for label, value in client_rows:
        c.setFillColor(DARK)
        c.setFont(_font(), 9)
        c.drawString(margin, row_y, label)
        c.setFont(_font(True), 9)
        wrapped = simpleSplit(value, _font(True), 9, content_w / 2 - 42 * mm)
        for i, line in enumerate(wrapped[:2]):
            c.drawString(margin + 38 * mm, row_y - i * 10, line)
        row_y -= max(12, 10 * min(len(wrapped), 2) + 2)

    mid_x = width / 2 + 6 * mm
    c.setStrokeColor(LIGHT_LINE)
    c.setLineWidth(0.8)
    c.line(mid_x - 4 * mm, info_top + 4, mid_x - 4 * mm, row_y + 8)
    _draw_brand(c, mid_x, info_top - 12, mark_size=16, title_size=10, light=False)
    layout.y = min(row_y, info_top - 24 * mm) - 7 * mm

    def _kv_block(title: str, rows: list[tuple[str, str]], *, trailing_total=None):
        """Bloc gris à en-tête sombre, lignes label/valeur, total jaune optionnel."""
        nonlocal layout
        line_gap = 13
        pad_x = 5 * mm
        header_h = 9 * mm
        total_h = 11 * mm if trailing_total else 0
        # Pré-calcul hauteur (avec wrap)
        body_h = 7 * mm
        prepared: list[tuple[str, list[str]]] = []
        value_w = content_w - label_w - 2 * pad_x
        for label, value in rows:
            lines = simpleSplit(str(value), _font(True), 9, value_w) or [""]
            prepared.append((label, lines))
            body_h += max(line_gap, 10 * len(lines) + 3)

        # Dessiner éventuellement sur plusieurs pages : on découpe les lignes
        idx = 0
        first_chunk = True
        while idx < len(prepared) or (first_chunk and not prepared):
            layout.ensure(header_h + 28 * mm + (total_h if idx >= len(prepared) - 1 else 0))
            # Combien de lignes tiennent sur cette page ?
            avail = layout.y - layout.content_bottom - header_h - 6 * mm
            if trailing_total and idx + 1 >= len(prepared):
                avail -= total_h + 4 * mm
            chunk: list[tuple[str, list[str]]] = []
            used = 8 * mm
            while idx < len(prepared):
                label, lines = prepared[idx]
                need = max(line_gap, 11 * len(lines) + 4)
                if chunk and used + need > avail:
                    break
                if not chunk and need > avail:
                    # forcer au moins une ligne (éventuellement tronquée)
                    lines = lines[: max(1, int((avail - 8 * mm) / 11))]
                    need = max(line_gap, 11 * len(lines) + 4)
                chunk.append((label, lines))
                used += need
                idx += 1

            chunk_body = used
            show_total = trailing_total is not None and idx >= len(prepared)
            box_h = header_h + chunk_body + (total_h if show_total else 4 * mm)
            layout.ensure(box_h + 4 * mm)
            box_top = layout.y
            box_x = margin

            _rounded_rect(c, box_x, box_top - box_h, content_w, box_h, 3 * mm, fill=GREY_BOX)
            c.setFillColor(GREY_BAR)
            c.roundRect(box_x, box_top - header_h, content_w, header_h, 3 * mm, fill=1, stroke=0)
            c.rect(box_x, box_top - header_h, content_w, 3 * mm, fill=1, stroke=0)
            c.setFillColor(white)
            c.setFont(_font(True), 10)
            suffix = "" if first_chunk else " (suite)"
            c.drawString(box_x + pad_x, box_top - 6.8 * mm, f"{title}{suffix}")

            cy = box_top - header_h - 8 * mm
            for label, lines in chunk:
                c.setFillColor(DARK)
                c.setFont(_font(), 9)
                c.drawString(box_x + pad_x, cy, label)
                c.setFont(_font(True), 9)
                for i, line in enumerate(lines):
                    c.drawString(box_x + pad_x + label_w, cy - i * 11, line)
                cy -= max(line_gap, 11 * len(lines) + 4)

            if show_total:
                total_label, total_value = trailing_total
                ty = box_top - box_h + 2.5 * mm
                _rounded_rect(
                    c,
                    box_x + 3 * mm,
                    ty,
                    content_w - 6 * mm,
                    total_h - 3 * mm,
                    4 * mm,
                    fill=YELLOW,
                )
                c.setFillColor(DARK)
                c.setFont(_font(True), 10)
                c.drawString(box_x + 10 * mm, ty + 4.5, total_label)
                c.setFont(_font(True), 13)
                c.drawRightString(box_x + content_w - 8 * mm, ty + 4, total_value)

            layout.y = box_top - box_h - 8 * mm
            first_chunk = False
            if not prepared:
                break

    service_rows = [
        ("Service payé :", service_label),
        ("Description :", description),
    ]
    if tracking:
        service_rows.append(("Référence / suivi :", tracking))
    service_rows.extend(_extra_service_rows(meta))
    service_rows.extend(
        [
            ("Montant :", _money(service_amount, payment.currency)),
            ("Frais de traitement :", _money(fee, payment.currency)),
        ]
    )
    _kv_block(
        "DÉTAIL DU SERVICE",
        service_rows,
        trailing_total=("MONTANT TOTAL PAYÉ", _money(total, payment.currency)),
    )

    # --- DÉTAIL DU PAIEMENT (lignes aérées, badge statut sans overlap) ---
    header_h = 9 * mm
    row_step = 14
    status_h = 8.5 * mm
    top_pad = 10 * mm
    # 3 lignes texte + espace dédié au badge (hauteur badge + marge)
    body_h = top_pad + 3 * row_step + 10 + status_h + 6 * mm
    box_h = header_h + body_h
    layout.ensure(box_h + 8 * mm)
    box_top = layout.y
    box_x = margin
    _rounded_rect(c, box_x, box_top - box_h, content_w, box_h, 3 * mm, fill=GREY_BOX)
    c.setFillColor(GREY_BAR)
    c.roundRect(box_x, box_top - header_h, content_w, header_h, 3 * mm, fill=1, stroke=0)
    c.rect(box_x, box_top - header_h, content_w, 3 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(_font(True), 10)
    c.drawString(box_x + 5 * mm, box_top - 6.2 * mm, "DÉTAIL DU PAIEMENT")

    py = box_top - header_h - top_pad

    c.setFillColor(DARK)
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Mode de paiement :")
    c.setFont(_font(True), 9)
    c.drawString(box_x + 5 * mm + label_w, py, str(method))
    if "orange" in method_code or "orange" in str(method).lower():
        c.setFillColor(ORANGE_M)
        c.roundRect(box_x + content_w - 36 * mm, py - 2, 28 * mm, 8 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(_font(True), 7)
        c.drawCentredString(box_x + content_w - 22 * mm, py, "Orange Money")
    py -= row_step

    c.setFillColor(DARK)
    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Numéro de transaction :")
    c.setFont(_font(True), 9)
    tx_lines = simpleSplit(str(tx_no), _font(True), 9, content_w - label_w - 12 * mm)
    c.drawString(box_x + 5 * mm + label_w, py, tx_lines[0] if tx_lines else "")
    py -= row_step

    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py, "Date de paiement :")
    c.setFont(_font(True), 9)
    c.drawString(box_x + 5 * mm + label_w, py, date_label)
    # Espace clair sous la date avant le badge (évite le chevauchement).
    py -= row_step + 8

    c.setFont(_font(), 9)
    c.drawString(box_x + 5 * mm, py + 1, "Statut :")
    status_w = 44 * mm
    sx = box_x + 5 * mm + label_w
    badge_bottom = py - (status_h / 2) + 2
    _rounded_rect(c, sx, badge_bottom, status_w, status_h, 4.2 * mm, fill=GREEN)
    c.setFillColor(white)
    c.setFont(_font(True), 8)
    c.drawCentredString(
        sx + status_w / 2,
        badge_bottom + status_h / 2 - 2.8,
        "✓  Paiement confirmé",
    )

    layout.y = box_top - box_h - 8 * mm

    # --- QR + Merci ---
    qr_size = 24 * mm
    layout.ensure(qr_size + 6 * mm)
    foot_y = layout.y
    verify_url = f"https://www.bujitodigital.com/verify/{receipt_no}"
    qr = _qr_image(verify_url)
    c.drawImage(qr, margin, foot_y - qr_size, qr_size, qr_size, mask="auto")
    c.setFillColor(YELLOW)
    c.circle(margin + qr_size / 2, foot_y - qr_size / 2, 5 * mm, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(_font(True), 7)
    c.drawCentredString(margin + qr_size / 2, foot_y - qr_size / 2 - 2, "bu.")

    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 8)
    text_x = margin + qr_size + 5 * mm
    c.drawString(text_x, foot_y - 10 * mm, "Scannez ce QR code pour vérifier")
    c.drawString(text_x, foot_y - 14 * mm, "l'authenticité de votre reçu.")

    c.setStrokeColor(LIGHT_LINE)
    c.setLineWidth(0.8)
    c.line(width / 2 + 4 * mm, foot_y - 2 * mm, width / 2 + 4 * mm, foot_y - qr_size + 2 * mm)

    c.setFillColor(DARK)
    c.setFont(_font(True), 20)
    c.drawString(width / 2 + 10 * mm, foot_y - 10 * mm, "Merci !")
    c.setStrokeColor(YELLOW)
    c.setLineWidth(2.5)
    c.line(width / 2 + 10 * mm, foot_y - 12 * mm, width / 2 + 38 * mm, foot_y - 12 * mm)
    c.setFillColor(GREY_TEXT)
    c.setFont(_font(), 8)
    c.drawString(width / 2 + 10 * mm, foot_y - 18 * mm, "Votre confiance nous motive !")
    c.drawString(width / 2 + 10 * mm, foot_y - 22 * mm, "Bujito Digital, toujours à vos côtés.")

    layout.y = foot_y - qr_size - 6 * mm
    layout.finish()
    c.save()
    return buf.getvalue()


def build_receipt_png(payment) -> bytes:
    """Deprecated : le reçu officiel est un PDF."""
    return build_receipt_pdf(payment)
