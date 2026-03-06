from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceType
from app.schemas.dashboard import DashboardSummary, GSTRingPoint, TrendPoint
from app.utils.period import financial_half_label, financial_quarter_label

VALID_PERIODS = {'monthly', 'quarterly', 'semi-annually', 'annually'}


def build_dashboard_summary(
    db: Session,
    user_id: str,
    period: str,
    year: int | None = None,
    financial_year_start: int | None = None,
) -> DashboardSummary:
    normalized_period = period if period in VALID_PERIODS else 'monthly'

    invoices = db.scalars(select(Invoice).where(Invoice.owner_id == user_id)).all()
    filtered = _filter_by_period(
        invoices,
        normalized_period,
        year=year,
        financial_year_start=financial_year_start,
    )

    total_sales = sum(item.total_amount for item in filtered if item.type == InvoiceType.SALES)
    total_purchases = sum(item.total_amount for item in filtered if item.type == InvoiceType.PURCHASE)
    gst_collected = sum(item.gst_amount for item in filtered if item.type == InvoiceType.SALES)
    gst_paid = sum(item.gst_amount for item in filtered if item.type == InvoiceType.PURCHASE)

    trend = _build_trend(filtered, normalized_period)
    gst_summary = [
        GSTRingPoint(name='GST Collected', value=round(gst_collected, 2)),
        GSTRingPoint(name='GST Paid', value=round(gst_paid, 2)),
        GSTRingPoint(name='GST Payable', value=round(gst_collected - gst_paid, 2)),
    ]

    return DashboardSummary(
        total_sales=round(total_sales, 2),
        total_purchases=round(total_purchases, 2),
        gst_collected=round(gst_collected, 2),
        gst_paid=round(gst_paid, 2),
        gst_payable=round(gst_collected - gst_paid, 2),
        trend=trend,
        gst_summary=gst_summary,
    )


def _filter_by_period(
    invoices: list[Invoice],
    period: str,
    year: int | None = None,
    financial_year_start: int | None = None,
) -> list[Invoice]:
    if financial_year_start is not None:
        return [
            invoice
            for invoice in invoices
            if (
                (invoice.invoice_date.year == financial_year_start and invoice.invoice_date.month >= 4)
                or (invoice.invoice_date.year == financial_year_start + 1 and invoice.invoice_date.month <= 3)
            )
        ]

    selected_year = year
    if selected_year is None and period != 'annually':
        selected_year = date.today().year

    if selected_year is None:
        return invoices

    return [invoice for invoice in invoices if invoice.invoice_date.year == selected_year]


def _build_trend(invoices: list[Invoice], period: str) -> list[TrendPoint]:
    if period == 'monthly':
        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        def label_for(invoice: Invoice) -> str:
            return labels[invoice.invoice_date.month - 1]

    elif period == 'quarterly':
        labels = ['Q1', 'Q2', 'Q3', 'Q4']

        def label_for(invoice: Invoice) -> str:
            return financial_quarter_label(invoice.invoice_date)

    elif period == 'semi-annually':
        labels = ['H1', 'H2']

        def label_for(invoice: Invoice) -> str:
            return financial_half_label(invoice.invoice_date)

    else:
        years = sorted({invoice.invoice_date.year for invoice in invoices})
        if not years:
            years = [date.today().year]
        labels = [str(year) for year in years]

        def label_for(invoice: Invoice) -> str:
            return str(invoice.invoice_date.year)

    accumulator = {
        label: {'sales': 0.0, 'purchases': 0.0}
        for label in labels
    }

    for invoice in invoices:
        label = label_for(invoice)
        if label not in accumulator:
            continue
        if invoice.type == InvoiceType.SALES:
            accumulator[label]['sales'] += invoice.total_amount
        else:
            accumulator[label]['purchases'] += invoice.total_amount

    return [
        TrendPoint(
            label=label,
            sales=round(values['sales'], 2),
            purchases=round(values['purchases'], 2),
        )
        for label, values in accumulator.items()
    ]
