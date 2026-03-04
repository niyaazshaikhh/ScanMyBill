from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.invoice import Invoice

from pdf2image import convert_from_path

def pdf_to_images(path):

    images = convert_from_path(path, dpi=300)

    return images


def build_invoice_pdf(invoice: Invoice) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('ScanMyBill.in - Invoice', styles['Title']))
    elements.append(Spacer(1, 12))

    details_data = [
        ['Invoice #', invoice.invoice_number],
        ['Date', invoice.invoice_date.isoformat()],
        ['Type', invoice.type.value.title()],
        ['Client', invoice.client.name if invoice.client else 'N/A'],
        ['Place of Supply', f"{invoice.place_of_supply or 'N/A'} ({invoice.place_of_supply_code or 'N/A'})"],
        ['Amount (Before Tax)', f'{invoice.subtotal:.2f}'],
        ['Total Tax Amount', f'{invoice.gst_amount:.2f}'],
        ['Grand Total', f'{invoice.total_amount:.2f}'],
    ]

    details_table = Table(details_data, hAlign='LEFT', colWidths=[120, 340])
    details_table.setStyle(
        TableStyle(
            [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    elements.append(details_table)
    elements.append(Spacer(1, 18))

    item_rows = [['Description', 'HSN/SAC', 'Qty', 'Rate', 'Tax %', 'Amount', 'CGST', 'SGST/UTGST', 'Grand Total']]
    for item in invoice.items:
        amount_before_tax = item.quantity * item.price
        total_tax_amount = amount_before_tax * (item.gst_percent / 100.0)
        cgst = total_tax_amount / 2.0
        sgst_utgst = total_tax_amount / 2.0
        grand_total = amount_before_tax + total_tax_amount
        item_rows.append(
            [
                item.description,
                item.hsn_sac or 'N/A',
                f'{item.quantity:.2f}',
                f'{item.price:.2f}',
                f'{item.gst_percent:.2f}',
                f'{amount_before_tax:.2f}',
                f'{cgst:.2f}',
                f'{sgst_utgst:.2f}',
                f'{grand_total:.2f}',
            ]
        )

    item_table = Table(
        item_rows,
        hAlign='LEFT',
        colWidths=[110, 60, 40, 50, 45, 50, 50, 60, 55],
    )
    item_table.setStyle(
        TableStyle(
            [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    elements.append(item_table)

    doc.build(elements)
    return buffer.getvalue()


def build_folder_export_pdf(invoices: list[Invoice], folder_label: str, period: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph('ScanMyBill.in - Folder Export', styles['Title']))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f'Period: {period} | Folder: {folder_label}', styles['Normal']))
    elements.append(Spacer(1, 12))

    rows = [['Date', 'Invoice #', 'Client', 'Type', 'GST', 'Amount']]
    for invoice in invoices:
        rows.append(
            [
                invoice.invoice_date.isoformat(),
                invoice.invoice_number,
                invoice.client.name if invoice.client else 'N/A',
                invoice.type.value.title(),
                f'{invoice.gst_amount:.2f}',
                f'{invoice.total_amount:.2f}',
            ]
        )

    totals = sum(item.total_amount for item in invoices)
    rows.append(['', '', '', '', 'Grand Total', f'{totals:.2f}'])

    table = Table(rows, hAlign='LEFT', colWidths=[75, 110, 125, 65, 65, 80])
    table.setStyle(
        TableStyle(
            [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('BACKGROUND', (4, -1), (-1, -1), colors.whitesmoke),
                ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
            ]
        )
    )
    elements.append(table)

    doc.build(elements)
    return buffer.getvalue()
