from typing import Literal

from pydantic import BaseModel, Field


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


class DashboardAssistantHistoryItem(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=2000)


class DashboardAssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    period: str | None = Field(default='monthly')
    financial_year_start: int | None = Field(default=None, ge=2000, le=2100)
    history: list[DashboardAssistantHistoryItem] = Field(default_factory=list, max_length=12)


class DashboardAssistantResponse(BaseModel):
    answer: str
    model: str
