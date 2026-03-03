from datetime import datetime

from pydantic import BaseModel


class RazorpayPlanOption(BaseModel):
    id: str
    item_name: str | None = None
    interval: int | None = None
    period: str | None = None
    amount: int | None = None
    currency: str | None = None


class RazorpayConfigResponse(BaseModel):
    key_id: str | None
    plans: list[RazorpayPlanOption] = []


class SubscriptionResponse(BaseModel):
    subscription_id: str
    status: str
    short_url: str | None = None


class SubscriptionCancelResponse(BaseModel):
    cancelled: bool
    subscription_id: str | None = None
    status: str
    expires_at: datetime | None = None


class CreateSubscriptionRequest(BaseModel):
    plan_id: str | None = None


class PaymentVerifyRequest(BaseModel):
    razorpay_signature: str
    razorpay_payment_id: str | None = None
    razorpay_subscription_id: str | None = None
