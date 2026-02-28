from pydantic import BaseModel


class RazorpayConfigResponse(BaseModel):
    key_id: str | None


class SubscriptionDemoResponse(BaseModel):
    subscription_id: str
    status: str
    short_url: str | None = None
    mock: bool = False


class PaymentVerifyRequest(BaseModel):
    razorpay_signature: str
    razorpay_payment_id: str | None = None
    razorpay_subscription_id: str | None = None