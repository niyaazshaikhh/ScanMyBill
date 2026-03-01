import json

import razorpay
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.payment_event import PaymentEvent
from app.models.user import User
from app.schemas.payment import (
    CreateSubscriptionRequest,
    PaymentVerifyRequest,
    RazorpayConfigResponse,
    RazorpayPlanOption,
    SubscriptionResponse,
)

router = APIRouter()


def _build_plan_options(client: razorpay.Client | None = None) -> list[RazorpayPlanOption]:
    plan_options: list[RazorpayPlanOption] = []
    for plan_id in settings.allowed_razorpay_plan_ids:
        option = RazorpayPlanOption(id=plan_id)
        if client:
            try:
                plan = client.plan.fetch(plan_id)
                item = plan.get('item') if isinstance(plan.get('item'), dict) else {}
                option = RazorpayPlanOption(
                    id=plan.get('id', plan_id),
                    item_name=item.get('name'),
                    interval=plan.get('interval'),
                    period=plan.get('period'),
                    amount=item.get('amount'),
                    currency=item.get('currency'),
                )
            except Exception:
                # Fallback to plan ID only when metadata fetch fails.
                pass
        plan_options.append(option)
    return plan_options


@router.get('/config', response_model=RazorpayConfigResponse)
def payment_config() -> RazorpayConfigResponse:
    plan_options: list[RazorpayPlanOption] = []
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        plan_options = _build_plan_options(client)
    else:
        plan_options = _build_plan_options()
    return RazorpayConfigResponse(key_id=settings.razorpay_key_id, plans=plan_options)


@router.post('/subscriptions', response_model=SubscriptionResponse)
def create_subscription(
    payload: CreateSubscriptionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubscriptionResponse:
    allowed_plan_ids = settings.allowed_razorpay_plan_ids
    if not settings.razorpay_key_id or not settings.razorpay_key_secret or not allowed_plan_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Razorpay is not fully configured. Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, and at least one plan in RAZORPAY_PLAN_ID or RAZORPAY_PLAN_IDS.',
        )

    requested_plan_id = payload.plan_id if payload else None
    if requested_plan_id and requested_plan_id not in allowed_plan_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected plan is not allowed.')

    plan_id = requested_plan_id or allowed_plan_ids[0]
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    try:
        subscription_payload = {
            'plan_id': plan_id,
            'total_count': 12,
            'customer_notify': 1,
            'notes': {
                'source': 'scanmybill_live',
                'user_id': current_user.id,
                'user_email': current_user.email,
                'selected_plan_id': plan_id,
            },
        }
        subscription = client.subscription.create(subscription_payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Razorpay API error') from exc

    event = PaymentEvent(
        owner_id=current_user.id,
        provider='razorpay',
        provider_payment_id=subscription.get('id', ''),
        status=subscription.get('status', 'created'),
        payload=json.dumps(subscription),
    )
    db.add(event)
    db.commit()

    return SubscriptionResponse(
        subscription_id=subscription.get('id', ''),
        status=subscription.get('status', 'created'),
        short_url=subscription.get('short_url'),
    )


@router.post('/verify')
def verify_payment(
    payload: PaymentVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Razorpay is not fully configured.',
        )

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    try:
        if payload.razorpay_subscription_id and payload.razorpay_payment_id:
            client.utility.verify_subscription_payment_signature(
                {
                    'razorpay_subscription_id': payload.razorpay_subscription_id,
                    'razorpay_payment_id': payload.razorpay_payment_id,
                    'razorpay_signature': payload.razorpay_signature,
                }
            )
        else:
            return {'verified': False, 'error': 'Incomplete payload'}
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Razorpay signature')

    event = PaymentEvent(
        owner_id=current_user.id,
        provider='razorpay',
        provider_payment_id=payload.razorpay_subscription_id or payload.razorpay_payment_id or '',
        status='verified',
        payload=json.dumps(payload.model_dump()),
    )
    db.add(event)
    db.commit()

    return {'verified': True}
