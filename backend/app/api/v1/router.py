from fastapi import APIRouter

from app.api.v1.endpoints import auth, bills, clients, dashboard, invoices, newsletter, payments

api_router = APIRouter()
api_router.include_router(auth.router, tags=['auth'])
api_router.include_router(dashboard.router, prefix='/dashboard', tags=['dashboard'])
api_router.include_router(invoices.router, prefix='/invoices', tags=['invoices'])
api_router.include_router(clients.router, prefix='/clients', tags=['clients'])
api_router.include_router(bills.router, prefix='/bills', tags=['bills'])
api_router.include_router(payments.router, prefix='/payments', tags=['payments'])
api_router.include_router(newsletter.router, prefix='/newsletter', tags=['newsletter'])
