from fastapi import APIRouter

from app.api.v1.endpoints import auth, bills, clients, dashboard, invoices, newsletter, payments, users
from app.api.v1.router import api_router

__all__ = ['api_router']
