import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.payment_event import PaymentEvent
from app.models.user import SubscriptionPlan, SubscriptionStatus, User
from app.schemas.payment import (
    CreateSubscriptionRequest,
    PaymentVerifyRequest,
    RazorpayConfigResponse,
    RazorpayPlanOption,
    SubscriptionCancelResponse,
    SubscriptionResponse,
)
from app.services.notifications import create_notification

router = APIRouter()
logger = logging.getLogger(__name__)


def _create_notification_best_effort(
    db: Session,
    *,
    user_id: str,
    title: str,
    message: str,
    route: str | None = '/settings',
    dedupe_key: str | None = None,
) -> None:
    try:
        notification = create_notification(
            db,
            user_id=user_id,
            title=title,
            message=message,
            route=route,
            dedupe_key=dedupe_key,
        )
        if notification:
            db.commit()
    except Exception:
        db.rollback()


def _build_plan_options(client: razorpay.Client | None = None) -> list[RazorpayPlanOption]:
    plan_options: list[RazorpayPlanOption] = []
    for plan_id in settings.allowed_razorpay_plan_ids:
        option = RazorpayPlanOption(
            id=plan_id,
            mapped_plan=_resolve_plan_hint(plan_id=plan_id),
        )
        if client:
            try:
                plan = client.plan.fetch(plan_id)
                item = plan.get('item') if isinstance(plan.get('item'), dict) else {}
                notes = plan.get('notes') if isinstance(plan.get('notes'), dict) else {}
                item_name = item.get('name') if isinstance(item, dict) else None
                item_description = item.get('description') if isinstance(item, dict) else None
                option = RazorpayPlanOption(
                    id=plan.get('id', plan_id),
                    item_name=item_name,
                    interval=plan.get('interval'),
                    period=plan.get('period'),
                    amount=item.get('amount'),
                    currency=item.get('currency'),
                    mapped_plan=_resolve_plan_hint(
                        plan_id=str(plan.get('id', plan_id) or plan_id),
                        item_name=item_name if isinstance(item_name, str) else None,
                        item_description=item_description if isinstance(item_description, str) else None,
                        notes=notes,
                    ),
                )
            except Exception:
                # Fallback to plan ID only when metadata fetch fails.
                pass
        plan_options.append(option)
    return plan_options


def _to_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def _plan_from_text(value: str | None) -> SubscriptionPlan | None:
    if not value:
        return None
    normalized = value.strip().lower()
    tokens = normalized.replace('-', ' ').replace('_', ' ')
    if 'business' in tokens or 'enterprise' in tokens or 'premium' in tokens:
        return SubscriptionPlan.BUSINESS
    if ' pro ' in f' {tokens} ' or 'professional' in tokens:
        return SubscriptionPlan.PRO
    if 'standard' in tokens or 'starter' in tokens or 'basic' in tokens:
        return SubscriptionPlan.STANDARD
    if 'free' in tokens or 'trial' in tokens:
        return SubscriptionPlan.FREE
    return None


def _resolve_plan_hint(
    *,
    plan_id: str | None = None,
    item_name: str | None = None,
    item_description: str | None = None,
    notes: dict[str, Any] | None = None,
) -> SubscriptionPlan | None:
    if notes:
        for key in ('plan', 'plan_name', 'tier', 'plan_tier'):
            raw = notes.get(key)
            if isinstance(raw, str):
                mapped = _plan_from_text(raw)
                if mapped and mapped != SubscriptionPlan.FREE:
                    return mapped

    for candidate in (item_name, item_description, plan_id):
        if not isinstance(candidate, str):
            continue
        mapped = _plan_from_text(candidate)
        if mapped and mapped != SubscriptionPlan.FREE:
            return mapped

    return None


PLAN_RANK: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.FREE: 0,
    SubscriptionPlan.STANDARD: 1,
    SubscriptionPlan.PRO: 2,
    SubscriptionPlan.BUSINESS: 3,
}


def _plan_rank(plan: SubscriptionPlan) -> int:
    return PLAN_RANK.get(plan, 0)


def _plan_label(plan: SubscriptionPlan) -> str:
    return plan.value.title()


def _resolve_subscription_notification(
    *,
    previous_plan: SubscriptionPlan,
    previous_status: SubscriptionStatus,
    previous_expires_at: datetime | None,
    current_plan: SubscriptionPlan,
    current_status: SubscriptionStatus,
    current_expires_at: datetime | None,
) -> tuple[str, str]:
    if current_status == SubscriptionStatus.CANCELLED:
        return ('Plan Cancelled', 'Your active subscription plan has been cancelled.')

    if current_status == SubscriptionStatus.EXPIRED:
        return ('Subscription Expired', 'Your subscription has expired.')

    if current_status != SubscriptionStatus.ACTIVE:
        return ('Subscription Updated', 'Your subscription details have been updated.')

    if _plan_rank(current_plan) > _plan_rank(previous_plan):
        if previous_plan == SubscriptionPlan.FREE or previous_status != SubscriptionStatus.ACTIVE:
            return ('Subscription Activated', f'Your {_plan_label(current_plan)} plan is now active.')
        return ('Plan Upgraded', f'Your plan has been upgraded to {_plan_label(current_plan)}.')

    if (
        current_plan == previous_plan
        and previous_status == SubscriptionStatus.ACTIVE
        and current_expires_at
        and (previous_expires_at is None or current_expires_at > previous_expires_at)
    ):
        return ('Plan Renewed', f'Your {_plan_label(current_plan)} plan has been renewed.')

    if current_plan == previous_plan and previous_status == SubscriptionStatus.ACTIVE:
        return ('Plan Renewed', f'Your {_plan_label(current_plan)} plan remains active.')

    if _plan_rank(current_plan) < _plan_rank(previous_plan):
        return ('Plan Updated', f'Your plan has been changed to {_plan_label(current_plan)}.')

    return ('Subscription Activated', f'Your {_plan_label(current_plan)} plan is now active.')


def _build_webhook_notification_dedupe_key(
    *,
    event_name: str,
    subscription_id: str | None,
    payment_id: str | None,
    cycle_marker: str | None = None,
) -> str | None:
    if event_name == 'subscription.charged':
        if payment_id:
            return f'subscription-payment-{payment_id}'
        if subscription_id and cycle_marker:
            return f'subscription-charge-{subscription_id}-{cycle_marker}'
    if subscription_id:
        return f'subscription-webhook-{event_name}-{subscription_id}'
    if payment_id:
        return f'subscription-webhook-{event_name}-{payment_id}'
    return None


def _resolve_subscription_plan(
    plan_id: str | None,
    client: razorpay.Client | None,
    *,
    plan_name_hint: str | None = None,
) -> SubscriptionPlan:
    hinted = _plan_from_text(plan_name_hint)
    if hinted and hinted != SubscriptionPlan.FREE:
        return hinted

    if client and plan_id:
        try:
            plan = client.plan.fetch(plan_id)
            item = plan.get('item') if isinstance(plan.get('item'), dict) else {}
            candidates = [
                item.get('name') if isinstance(item, dict) else None,
                item.get('description') if isinstance(item, dict) else None,
            ]
            for candidate in candidates:
                mapped = _plan_from_text(candidate)
                if mapped and mapped != SubscriptionPlan.FREE:
                    return mapped
        except Exception:
            pass

    return SubscriptionPlan.STANDARD if plan_id else SubscriptionPlan.FREE


def _resolve_user_for_subscription(db: Session, subscription: dict[str, Any]) -> User | None:
    notes = subscription.get('notes')
    if isinstance(notes, dict):
        notes_user_id = notes.get('user_id')
        if isinstance(notes_user_id, str) and notes_user_id:
            user = db.get(User, notes_user_id)
            if user:
                return user

    subscription_id = subscription.get('id')
    if isinstance(subscription_id, str) and subscription_id:
        user = db.scalar(select(User).where(User.razorpay_subscription_id == subscription_id))
        if user:
            return user

        payment_event = db.scalar(
            select(PaymentEvent)
            .where(
                PaymentEvent.provider == 'razorpay',
                PaymentEvent.provider_payment_id == subscription_id,
            )
            .order_by(PaymentEvent.created_at.desc())
            .limit(1)
        )
        if payment_event:
            return db.get(User, payment_event.owner_id)

    return None


def _activate_subscription(
    user: User,
    *,
    plan: SubscriptionPlan,
    subscription_id: str | None,
    started_at: datetime | None,
    expires_at: datetime | None,
) -> None:
    user.subscription_plan = plan
    user.subscription_status = SubscriptionStatus.ACTIVE
    if subscription_id:
        user.razorpay_subscription_id = subscription_id
    user.subscription_started_at = started_at or user.subscription_started_at or datetime.now(timezone.utc)
    user.subscription_expires_at = expires_at


def _cancel_subscription(user: User, *, expires_at: datetime | None) -> None:
    user.subscription_plan = SubscriptionPlan.FREE
    user.subscription_status = SubscriptionStatus.CANCELLED
    user.subscription_expires_at = expires_at or user.subscription_expires_at or datetime.now(timezone.utc)


def _expire_subscription(user: User) -> None:
    user.subscription_plan = SubscriptionPlan.FREE
    user.subscription_status = SubscriptionStatus.EXPIRED
    user.subscription_expires_at = user.subscription_expires_at or datetime.now(timezone.utc)


def _sync_user_subscription_from_entity(
    user: User,
    subscription: dict[str, Any],
    client: razorpay.Client | None,
) -> None:
    notes = subscription.get('notes') if isinstance(subscription.get('notes'), dict) else {}
    plan_hint = notes.get('selected_plan_name') if isinstance(notes, dict) else None
    plan_id = subscription.get('plan_id') if isinstance(subscription.get('plan_id'), str) else None
    status_value = str(subscription.get('status') or '').lower()
    subscription_id = subscription.get('id') if isinstance(subscription.get('id'), str) else None
    started_at = _to_utc_datetime(subscription.get('current_start') or subscription.get('start_at'))
    expires_at = _to_utc_datetime(
        subscription.get('current_end') or subscription.get('ended_at') or subscription.get('charge_at')
    )

    if status_value in {'cancelled', 'halted'}:
        _cancel_subscription(user, expires_at=expires_at)
        return

    if status_value in {'completed', 'expired'}:
        _expire_subscription(user)
        return

    _activate_subscription(
        user,
        plan=_resolve_subscription_plan(plan_id, client, plan_name_hint=plan_hint),
        subscription_id=subscription_id,
        started_at=started_at,
        expires_at=expires_at,
    )


def _verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False

    generated = hmac.new(
        settings.razorpay_webhook_secret.encode('utf-8'),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


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

    selected_plan_name: str | None = None
    try:
        selected_plan = client.plan.fetch(plan_id)
        item = selected_plan.get('item') if isinstance(selected_plan.get('item'), dict) else {}
        if isinstance(item, dict):
            selected_plan_name = item.get('name')
    except Exception:
        selected_plan_name = None

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
                'selected_plan_name': selected_plan_name or '',
            },
        }
        subscription = client.subscription.create(subscription_payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Razorpay API error') from exc

    subscription_id = subscription.get('id', '')
    if isinstance(subscription_id, str) and subscription_id:
        current_user.razorpay_subscription_id = subscription_id

    event = PaymentEvent(
        owner_id=current_user.id,
        provider='razorpay',
        provider_payment_id=subscription_id,
        status=subscription.get('status', 'created'),
        payload=json.dumps(subscription),
    )
    db.add(event)
    db.commit()
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Subscription Checkout Started',
        message='Your subscription checkout link has been generated.',
    )

    return SubscriptionResponse(
        subscription_id=subscription_id,
        status=subscription.get('status', 'created'),
        short_url=subscription.get('short_url'),
    )


@router.post('/subscriptions/cancel', response_model=SubscriptionCancelResponse)
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubscriptionCancelResponse:
    subscription_id = current_user.razorpay_subscription_id
    if not subscription_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='No active subscription found.')

    cancel_payload: dict[str, Any] = {}
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        try:
            try:
                cancelled = client.subscription.cancel(
                    subscription_id,
                    {'cancel_at_cycle_end': 0},
                )
            except TypeError:
                cancelled = client.subscription.cancel(subscription_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Failed to cancel subscription with Razorpay.',
            ) from exc

        if isinstance(cancelled, dict):
            cancel_payload = cancelled

    expires_at = _to_utc_datetime(
        cancel_payload.get('current_end') or cancel_payload.get('ended_at') or cancel_payload.get('charge_at')
    )
    _cancel_subscription(current_user, expires_at=expires_at)

    db.add(
        PaymentEvent(
            owner_id=current_user.id,
            provider='razorpay',
            provider_payment_id=subscription_id,
            status='subscription.cancelled',
            payload=json.dumps({'subscription': cancel_payload or None}),
        )
    )
    db.commit()
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title='Plan Cancelled',
        message='Your active subscription plan has been cancelled.',
        dedupe_key=f'subscription-cancel-{subscription_id}',
    )

    return SubscriptionCancelResponse(
        cancelled=True,
        subscription_id=subscription_id,
        status=current_user.subscription_status.value,
        expires_at=current_user.subscription_expires_at,
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Incomplete payment verification payload')
    except Exception:
        logger.warning(
            'razorpay_verify_failed user_id=%s reason=invalid_signature payment_id=%s subscription_id=%s',
            current_user.id,
            payload.razorpay_payment_id,
            payload.razorpay_subscription_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Razorpay signature')

    payment_data: dict[str, Any] = {}
    if payload.razorpay_payment_id:
        try:
            fetched_payment = client.payment.fetch(payload.razorpay_payment_id)
            if isinstance(fetched_payment, dict):
                payment_data = fetched_payment
        except Exception as exc:
            logger.exception(
                'razorpay_verify_failed user_id=%s reason=payment_fetch_failed payment_id=%s',
                current_user.id,
                payload.razorpay_payment_id,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Failed to verify payment status') from exc

    payment_status = str(payment_data.get('status') or '').lower() if payment_data else ''
    if payment_data and payment_status not in {'authorized', 'captured'}:
        logger.warning(
            'razorpay_verify_failed user_id=%s reason=unexpected_payment_status payment_id=%s status=%s',
            current_user.id,
            payload.razorpay_payment_id,
            payment_status,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Payment status is not valid')

    if payment_data and payload.razorpay_subscription_id:
        payment_subscription_id = payment_data.get('subscription_id')
        if isinstance(payment_subscription_id, str) and payment_subscription_id != payload.razorpay_subscription_id:
            logger.warning(
                'razorpay_verify_failed user_id=%s reason=subscription_mismatch payment_id=%s expected_subscription=%s actual_subscription=%s',
                current_user.id,
                payload.razorpay_payment_id,
                payload.razorpay_subscription_id,
                payment_subscription_id,
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Payment does not match subscription')

    subscription_data: dict[str, Any] = {}
    if payload.razorpay_subscription_id:
        try:
            fetched = client.subscription.fetch(payload.razorpay_subscription_id)
            if isinstance(fetched, dict):
                subscription_data = fetched
        except Exception:
            subscription_data = {}

    previous_plan = current_user.subscription_plan
    previous_status = current_user.subscription_status
    previous_expires_at = current_user.subscription_expires_at

    if subscription_data:
        _sync_user_subscription_from_entity(current_user, subscription_data, client)
    else:
        _activate_subscription(
            current_user,
            plan=SubscriptionPlan.STANDARD,
            subscription_id=payload.razorpay_subscription_id,
            started_at=datetime.now(timezone.utc),
            expires_at=None,
        )

    event_payload = {
        'verify_payload': payload.model_dump(),
        'payment': payment_data or None,
        'subscription': subscription_data or None,
    }
    event = PaymentEvent(
        owner_id=current_user.id,
        provider='razorpay',
        provider_payment_id=payload.razorpay_subscription_id or payload.razorpay_payment_id or '',
        status='verified',
        payload=json.dumps(event_payload),
    )
    db.add(event)
    db.commit()
    title, message = _resolve_subscription_notification(
        previous_plan=previous_plan,
        previous_status=previous_status,
        previous_expires_at=previous_expires_at,
        current_plan=current_user.subscription_plan,
        current_status=current_user.subscription_status,
        current_expires_at=current_user.subscription_expires_at,
    )
    dedupe_key = (
        f'subscription-payment-{payload.razorpay_payment_id}'
        if payload.razorpay_payment_id
        else (f'subscription-verify-{payload.razorpay_subscription_id}' if payload.razorpay_subscription_id else None)
    )
    _create_notification_best_effort(
        db,
        user_id=current_user.id,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
    )

    logger.info(
        'razorpay_verify_success user_id=%s payment_id=%s subscription_id=%s',
        current_user.id,
        payload.razorpay_payment_id,
        payload.razorpay_subscription_id,
    )
    return {'verified': True}


@router.post('/webhook')
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Razorpay webhook secret is not configured.',
        )

    signature = request.headers.get('X-Razorpay-Signature')
    if not signature:
        logger.warning('razorpay_webhook_rejected reason=missing_signature')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing Razorpay webhook signature')

    payload_bytes = await request.body()
    if not _verify_webhook_signature(payload_bytes, signature):
        logger.warning('razorpay_webhook_rejected reason=invalid_signature')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Razorpay webhook signature')

    try:
        data = json.loads(payload_bytes.decode('utf-8'))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid webhook payload') from exc

    event_name = str(data.get('event') or '').lower()
    payload = data.get('payload')
    if not isinstance(payload, dict):
        return {'received': True}

    subscription_wrapper = payload.get('subscription')
    if not isinstance(subscription_wrapper, dict):
        return {'received': True}

    subscription_data = subscription_wrapper.get('entity')
    if not isinstance(subscription_data, dict):
        return {'received': True}

    user = _resolve_user_for_subscription(db, subscription_data)
    if not user:
        logger.info('razorpay_webhook_ignored reason=user_not_found event=%s', event_name)
        return {'received': True}

    previous_plan = user.subscription_plan
    previous_status = user.subscription_status
    previous_expires_at = user.subscription_expires_at

    razorpay_client: razorpay.Client | None = None
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        razorpay_client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    subscription_status = str(subscription_data.get('status') or '').lower()
    if event_name in {'subscription.cancelled', 'subscription.halted'} or subscription_status in {'cancelled', 'halted'}:
        expires_at = _to_utc_datetime(subscription_data.get('ended_at') or subscription_data.get('current_end'))
        _cancel_subscription(user, expires_at=expires_at)
    elif event_name in {'subscription.completed'} or subscription_status in {'completed', 'expired'}:
        _expire_subscription(user)
    elif event_name in {
        'subscription.activated',
        'subscription.authenticated',
        'subscription.charged',
        'subscription.pending',
    } or subscription_status in {'active', 'authenticated', 'pending'}:
        _sync_user_subscription_from_entity(user, subscription_data, razorpay_client)

    payment_wrapper = payload.get('payment')
    payment_entity = payment_wrapper.get('entity') if isinstance(payment_wrapper, dict) else {}
    payment_id = payment_entity.get('id') if isinstance(payment_entity.get('id'), str) else None
    subscription_id = subscription_data.get('id') if isinstance(subscription_data.get('id'), str) else None

    db.add(
        PaymentEvent(
            owner_id=user.id,
            provider='razorpay',
            provider_payment_id=subscription_id or payment_id or f'webhook:{event_name or "event"}',
            status=event_name or subscription_status or 'webhook',
            payload=payload_bytes.decode('utf-8'),
        )
    )
    db.commit()

    title, message = _resolve_subscription_notification(
        previous_plan=previous_plan,
        previous_status=previous_status,
        previous_expires_at=previous_expires_at,
        current_plan=user.subscription_plan,
        current_status=user.subscription_status,
        current_expires_at=user.subscription_expires_at,
    )
    if event_name == 'subscription.charged' and user.subscription_status == SubscriptionStatus.ACTIVE:
        title = 'Plan Renewed'
        message = f'Your {_plan_label(user.subscription_plan)} plan has been renewed.'
    elif title == 'Plan Renewed':
        title = 'Subscription Updated'
        message = 'Your subscription details have been updated.'

    cycle_source = subscription_data.get('current_end') or subscription_data.get('charge_at') or subscription_data.get('ended_at')
    cycle_marker = str(cycle_source) if cycle_source else None
    dedupe_key = _build_webhook_notification_dedupe_key(
        event_name=event_name or 'subscription.update',
        subscription_id=subscription_id,
        payment_id=payment_id,
        cycle_marker=cycle_marker,
    )
    _create_notification_best_effort(
        db,
        user_id=user.id,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
    )

    logger.info(
        'razorpay_webhook_processed user_id=%s event=%s subscription_id=%s payment_id=%s',
        user.id,
        event_name,
        subscription_id,
        payment_id,
    )
    return {'received': True}
