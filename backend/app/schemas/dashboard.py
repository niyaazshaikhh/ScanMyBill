from pydantic import BaseModel


class TrendPoint(BaseModel):
    label: str
    sales: float
    purchases: float


class GSTRingPoint(BaseModel):
    name: str
    value: float


class DashboardSummary(BaseModel):
    total_sales: float
    total_purchases: float
    gst_collected: float
    gst_paid: float
    gst_payable: float
    trend: list[TrendPoint]
    gst_summary: list[GSTRingPoint]