from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    bills,
    clients,
    debug,
    dashboard,
    hsn_sac_master_list,
    invoices,
    newsletter,
    non_gst_challans as delivery_challans,
    notifications,
    payments,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, tags=['auth'])
api_router.include_router(admin.router, prefix='/admin', tags=['admin'])
api_router.include_router(debug.router, prefix='/debug', tags=['debug'])
api_router.include_router(dashboard.router, prefix='/dashboard', tags=['dashboard'])
api_router.include_router(invoices.router, prefix='/invoices', tags=['invoices'])
api_router.include_router(delivery_challans.router, prefix='/delivery-challans', tags=['delivery-challans'])
api_router.include_router(clients.router, prefix='/clients', tags=['clients'])
api_router.include_router(hsn_sac_master_list.router, prefix='/hsn-sac-master-list', tags=['hsn-sac-master-list'])
api_router.include_router(bills.router, prefix='/bills', tags=['bills'])
api_router.include_router(payments.router, prefix='/payments', tags=['payments'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(notifications.router, prefix='/notifications', tags=['notifications'])
api_router.include_router(newsletter.router, prefix='/newsletter', tags=['newsletter'])
