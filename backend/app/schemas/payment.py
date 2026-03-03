from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class _StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CreateSubscriptionRequest(_StrictRequestModel):
    plan_id: str | None = Field(default=None, min_length=1, max_length=120)


class PaymentVerifyRequest(_StrictRequestModel):
    razorpay_signature: str = Field(min_length=16, max_length=255)
    razorpay_payment_id: str | None = Field(default=None, min_length=1, max_length=255)
    razorpay_subscription_id: str | None = Field(default=None, min_length=1, max_length=255)
