import html
"""
services/invoice_service.py
ReportLab PDF invoice generator.
Ported from invoice.py — logic unchanged.
Instead of writing to a fixed path, writes to a temp file and returns the path
so FastAPI can serve it as a file download.

NOTE: settings_manager is not available in the web version.
Shop info is now read from config.py (SHOP_INFO dict below).
Update SHOP_INFO or wire it to a settings table later.
"""
import re
import tempfile
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                Table, TableStyle, HRFlowable)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch

from core.settings import get_all_settings

def generate_invoice(ticket: dict) -> str:
    """
    Build a PDF invoice for the given ticket dict.
    Returns the path to a temporary PDF file.
    The caller (FastAPI route) serves and then cleans it up.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()

    _build_pdf(ticket, path)
    return path


def _build_pdf(ticket: dict, path: str):
    settings = get_all_settings()
    currency = settings.get("currency_symbol", "$")
    tax_rate = float(settings.get("tax_rate", "0.0"))
    tax_lbl  = settings.get("tax_label", "Tax")

    shop_name    = settings.get("shop_name", "30 Or Less")
    shop_tagline = settings.get("shop_tagline", "IT Service Center")
    shop_phone   = settings.get("shop_phone", "")
    shop_email   = settings.get("shop_email", "contact.30orless@gmail.com")
    shop_address = settings.get("shop_address", "")

    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.65*inch, rightMargin=0.65*inch,
                            topMargin=0.55*inch, bottomMargin=0.55*inch)
    W   = letter[0] - 1.3*inch
    blk = colors.HexColor("#000000")
    lgry= colors.HexColor("#888888")
    bdr = colors.HexColor("#333333")

    t_id        = ticket.get("id",         "—")
    t_name      = ticket.get("name",       "—")
    t_phone     = ticket.get("phone",      "—")
    t_email     = ticket.get("email",      "—") or "—"
    t_address   = ticket.get("address",    "—") or "—"
    t_device    = ticket.get("device",     "—") or "—"
    t_serial    = ticket.get("serial",     "—") or "—"
    t_repair    = ticket.get("repair",     "—")
    t_issue     = ticket.get("issue",      "—") or "—"
    t_price     = ticket.get("price",      "—")
    t_due       = ticket.get("due",        "—") or "—"
    t_created   = ticket.get("created",    "—") or "—"
    t_status    = ticket.get("status",     "—") or "—"
    t_priority  = ticket.get("priority",   "—") or "—"
    t_data_ok   = ticket.get("data_ok",    False)
    t_auth      = ticket.get("auth",       False)
    t_tech      = ticket.get("technician", "") or ""

    def sty(size=10, bold=False, color=blk, align="LEFT", leading=None):
        return ParagraphStyle("s",
            fontSize=size,
            fontName="Courier-Bold" if bold else "Courier",
            textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            leading=leading or size * 1.35)

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = Table([[
        Paragraph(html.escape(shop_name.upper()), sty(22, bold=True)),
        Paragraph(f"INVOICE<br/><font size=9>{html.escape(t_id)}</font>",
                  sty(14, bold=True, align="RIGHT"))
    ]], colWidths=[W*0.6, W*0.4])
    hdr.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LINEBELOW",     (0,0),(-1,-1), 0.5, blk),
        ("LEFTPADDING",   (0,0),(0,-1),  0),
        ("RIGHTPADDING",  (-1,0),(-1,-1),0),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(hdr)

    contact_parts = [html.escape(p) for p in [shop_tagline, shop_phone, shop_email, shop_address] if p]
    contact_str   = "  ·  ".join(contact_parts)
    sub = Table([[
        Paragraph(contact_str, sty(9, color=lgry)),
        Paragraph(f"Date: {html.escape(t_created)}", sty(9, color=lgry, align="RIGHT"))
    ]], colWidths=[W*0.6, W*0.4])
    sub.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(0,-1),  0),
        ("RIGHTPADDING",  (-1,0),(-1,-1),0),
    ]))
    story.append(sub)
    story.append(Spacer(1, 10))

    def info_table(rows, table_w=W):
        t = Table(rows, colWidths=[table_w*0.28, table_w*0.72])
        t.setStyle(TableStyle([
            ("FONTNAME",      (0,0),(0,-1),  "Courier-Bold"),
            ("FONTNAME",      (1,0),(1,-1),  "Courier"),
            ("FONTSIZE",      (0,0),(-1,-1), 9),
            ("TEXTCOLOR",     (0,0),(-1,-1), blk),
            ("LINEBELOW",     (0,0),(-1,0),  0.5, blk),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ]))
        return t

    # ── Customer + Ticket two-col block ───────────────────────────────────────
    two_col = Table([[
        info_table([
            [Paragraph("CUSTOMER", sty(8, bold=True, color=lgry)), ""],
            ["Name",    Paragraph(html.escape(t_name),    sty(9))],
            ["Phone",   Paragraph(html.escape(t_phone),   sty(9))],
            ["Email",   Paragraph(html.escape(t_email),   sty(9))],
            ["Address", Paragraph(html.escape(t_address), sty(9))],
        ], table_w=W*0.55),
        info_table([
            [Paragraph("TICKET", sty(8, bold=True, color=lgry)), ""],
            ["Ticket #",   Paragraph(html.escape(t_id),       sty(9))],
            ["Priority",   Paragraph(html.escape(t_priority), sty(9))],
            ["Status",     Paragraph(html.escape(t_status),   sty(9))],
            ["Due Date",   Paragraph(html.escape(t_due),      sty(9))],
            ["Technician", Paragraph(html.escape(t_tech or "—"), sty(9))],
        ], table_w=W*0.45),
    ]], colWidths=[W*0.55, W*0.45])
    two_col.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(0,-1),  16),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=W, thickness=1, color=bdr))
    story.append(Spacer(1, 8))

    # ── Device ────────────────────────────────────────────────────────────────
    story.append(Paragraph("DEVICE", sty(8, bold=True, color=lgry)))
    story.append(Spacer(1, 3))
    dev_rows = [["Device", Paragraph(html.escape(t_device), sty(9))]]
    if t_serial and t_serial != "—":
        dev_rows.append(["Serial #", Paragraph(html.escape(t_serial), sty(9))])
    story.append(info_table(dev_rows))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=W, thickness=1, color=bdr))
    story.append(Spacer(1, 8))

    # ── Repair ────────────────────────────────────────────────────────────────
    story.append(Paragraph("REPAIR", sty(8, bold=True, color=lgry)))
    story.append(Spacer(1, 3))
    story.append(info_table([
        ["Type",  Paragraph(html.escape(t_repair), sty(9))],
        ["Issue", Paragraph(html.escape(t_issue).replace("\n", "<br/>"), sty(9))],
    ]))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=W, thickness=1, color=bdr))
    story.append(Spacer(1, 8))

    # ── Charges ───────────────────────────────────────────────────────────────
    story.append(Paragraph("CHARGES", sty(8, bold=True, color=lgry)))
    story.append(Spacer(1, 6))

    is_tax_exempt = bool(ticket.get("tax_exempt", False))
    discount_type = ticket.get("discount_type", "None")
    
    # Legacy notes check (fallback)
    t_notes_raw   = ticket.get("notes", "") or ""
    if "[TAX_EXEMPT]" in t_notes_raw: is_tax_exempt = True
    if "[VET_DISCOUNT:10%]" in t_notes_raw: discount_type = "Veteran / First Responder (10%)"

    try:
        stored_amount = float(str(t_price).replace(currency, "").replace(",", "").strip())
    except ValueError:
        stored_amount = None

    effective_tax_rate = 0.0 if is_tax_exempt else tax_rate

    if stored_amount is not None:
        # Calculate discount if applicable
        disc_amount = 0.0
        display_base = stored_amount
        
        if discount_type == "Veteran / First Responder (10%)":
            disc_amount = display_base * 0.10
            stored_amount = display_base - disc_amount

        tax_amount = stored_amount * (effective_tax_rate / 100)
        total      = stored_amount + tax_amount

        charge_rows = [
            [Paragraph("Description", sty(9, bold=True)),
             Paragraph("Amount",      sty(9, bold=True, align="RIGHT"))],
            [Paragraph(html.escape(t_repair), sty(9)),
             Paragraph(f"{html.escape(currency)}{display_base:,.2f}", sty(9, align="RIGHT"))],
        ]
        
        if disc_amount > 0:
            charge_rows.append([
                Paragraph(f"{html.escape(discount_type)} Applied", sty(9, color=lgry)),
                Paragraph(f"-{html.escape(currency)}{disc_amount:,.2f}", sty(9, align="RIGHT")),
            ])
            
        if effective_tax_rate > 0:
            charge_rows.append([
                Paragraph(f"{html.escape(tax_lbl)} ({effective_tax_rate:.2g}%)", sty(9, color=lgry)),
                Paragraph(f"{html.escape(currency)}{tax_amount:,.2f}", sty(9, align="RIGHT")),
            ])
        elif is_tax_exempt:
            charge_rows.append([
                Paragraph("Tax Exempt Status", sty(9, color=lgry)),
                Paragraph(f"{html.escape(currency)}0.00", sty(9, align="RIGHT")),
            ])
            
        total_str = f"{currency}{total:,.2f}"
        charge_rows.append([
            "",
            Paragraph(f"<b>TOTAL &nbsp; {html.escape(total_str)}</b>", sty(11, bold=True, align="RIGHT")),
        ])
        line_below_idx = len(charge_rows) - 2
    else:
        charge_rows = [
            [Paragraph("Description", sty(9, bold=True)),
             Paragraph("Amount",      sty(9, bold=True, align="RIGHT"))],
            [Paragraph(html.escape(t_repair), sty(9)),
             Paragraph(html.escape(t_price), sty(9, align="RIGHT"))],
            ["", Paragraph(f"<b>TOTAL &nbsp; {html.escape(t_price)}</b>",
                           sty(11, bold=True, align="RIGHT"))],
        ]
        line_below_idx = 1

    price_tbl = Table(charge_rows, colWidths=[W*0.75, W*0.25])
    price_tbl.setStyle(TableStyle([
        ("LINEBELOW",     (0,0),              (-1,0),              0.5, blk),
        ("LINEBELOW",     (0,line_below_idx), (-1,line_below_idx), 0.5, bdr),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("FONTNAME",      (0,1),(-1,-1), "Courier"),
        ("FONTSIZE",      (0,1),(-1,-1), 9),
    ]))
    story.append(price_tbl)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width=W, thickness=1, color=bdr))
    story.append(Spacer(1, 12))

    # ── Signatures ────────────────────────────────────────────────────────────
    sig = Table([[
        Table([[Paragraph("Customer Signature", sty(8, color=lgry))],
               [HRFlowable(width=2.2*inch, thickness=0.5, color=blk)]],
              colWidths=[2.4*inch]),
        Table([[Paragraph("Date", sty(8, color=lgry))],
               [HRFlowable(width=1.4*inch, thickness=0.5, color=blk)]],
              colWidths=[1.6*inch]),
        Table([[Paragraph("Technician", sty(8, color=lgry))],
               [Paragraph(html.escape(t_tech), sty(9)) if t_tech
                else HRFlowable(width=2.2*inch, thickness=0.5, color=blk)]],
              colWidths=[2.4*inch]),
    ]], colWidths=[W*0.4, W*0.25, W*0.35])
    sig.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "BOTTOM"),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    story.append(sig)
    story.append(Spacer(1, 12))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=1, color=blk))
    story.append(Spacer(1, 6))
    
    invoice_footer = settings.get("invoice_footer", f"Thank you for choosing {shop_name}.")
    if not invoice_footer:
        invoice_footer = f"Thank you for choosing {shop_name}."
        
    story.append(Paragraph(
        html.escape(invoice_footer),
        sty(8, color=lgry, align="CENTER")))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Data backup consent: {'Yes' if t_data_ok else 'No'}  |  "
        f"Repair authorized: {'Yes' if t_auth else 'No'}",
        sty(7, color=lgry, align="CENTER")))

    doc.build(story)
