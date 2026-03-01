import json

import razorpay
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.payment_event import PaymentEvent
from app.models.user import User
from app.schemas.payment import PaymentVerifyRequest, RazorpayConfigResponse, SubscriptionResponse

router = APIRouter()


@router.get('/config', response_model=RazorpayConfigResponse)
def payment_config() -> RazorpayConfigResponse:
    return RazorpayConfigResponse(key_id=settings.razorpay_key_id)


@router.post('/subscriptions', response_model=SubscriptionResponse)
def create_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubscriptionResponse:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret or not settings.razorpay_plan_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Razorpay is not fully configured. Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, and RAZORPAY_PLAN_ID.',
        )

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    try:
        payload = {
            'plan_id': settings.razorpay_plan_id,
            'total_count': 12,
            'customer_notify': 1,
            'notes': {
                'source': 'scanmybill_live',
                'user_id': current_user.id,
                'user_email': current_user.email,
            },
        }
        subscription = client.subscription.create(payload)
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
