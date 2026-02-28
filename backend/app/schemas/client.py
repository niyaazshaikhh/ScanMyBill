from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ClientBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    gst_number: str | None = Field(default=None, max_length=20)


class ClientCreate(ClientBase):
    pass


class ClientResponse(ClientBase):
    id: str
    created_at: datetime
    total_transactions: int = 0
    total_revenue: float = 0.0

    model_config = {'from_attributes': True}


class ClientAnalytics(BaseModel):
    client_id: str
    client_name: str
    transactions: int
    revenue: float


class ClientsOverview(BaseModel):
    total_clients: int
    total_transactions: int
    total_revenue: float
    top_clients: list[ClientAnalytics]