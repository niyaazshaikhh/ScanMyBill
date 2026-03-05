# API Documentation (v1)

Base URL: `http://localhost:8000/api/v1`  
Health endpoints: `http://localhost:8000/health/*`

## Authentication

Auth routes are under `/auth`.

- `POST /auth/create-account`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/admin/login`
- `POST /auth/google`
- `GET /auth/me`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

## Dashboard

- `GET /dashboard/summary?period=monthly|quarterly|semi-annually|annually&year=...`
- `GET /dashboard/admin-overview` (admin only)

## Bills (AI Extraction Upload Flow)

- `POST /bills/upload` (multipart/form-data)
  - fields: `file`, `invoice_type` (`sales` or `purchase`)
  - flow: upload validation -> AI/OCR extraction -> parsed invoice persistence

## Invoices

- `GET /invoices`
- `GET /invoices/latest-created`
- `POST /invoices/create`
- `POST /invoices/create/pdf`
- `GET /invoices/export-folder`
- `GET /invoices/{invoice_id}`
- `GET /invoices/{invoice_id}/preview`
- `GET /invoices/{invoice_id}/pdf`
- `DELETE /invoices/{invoice_id}`

## Delivery Challans (Non-GST)

Routes are under `/delivery-challans`.

- `GET /delivery-challans`
- `GET /delivery-challans/latest-created`
- `POST /delivery-challans/create`
- `POST /delivery-challans/create/pdf`
- `GET /delivery-challans/{challan_id}/preview`
- `GET /delivery-challans/{challan_id}/pdf`
- `DELETE /delivery-challans/{challan_id}`

## Clients

- `GET /clients`
- `POST /clients`
- `PUT /clients/{client_id}`
- `DELETE /clients/{client_id}`
- `GET /clients/analytics`

## HSN/SAC Master

Routes are under `/hsn-sac-master-list`.

- `GET /hsn-sac-master-list`
- `POST /hsn-sac-master-list`
- `PUT /hsn-sac-master-list/{entry_id}`
- `DELETE /hsn-sac-master-list/{entry_id}`

## Payments (Razorpay)

Routes are under `/payments`.

- `GET /payments/config`
- `POST /payments/orders` (recommended production checkout flow)
- `POST /payments/subscriptions`
- `POST /payments/subscriptions/cancel`
- `POST /payments/verify`
- `POST /payments/webhook`

### Recommended Production Checkout Sequence

1. Frontend calls `POST /payments/orders`.
2. Backend creates Razorpay order and stores status as `ORDER_CREATED`.
3. Frontend opens Razorpay checkout with `order_id`.
4. Frontend posts `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature` to `POST /payments/verify`.
5. Backend verifies signature + payment status and updates DB order status to `PAID`.

## User Profile and Preferences

Routes are under `/users`.

- `GET /users/me`
- `PUT /users/notification-preference`
- `GET /users/personal-details`
- `PUT /users/personal-details`

## Notifications

Routes are under `/notifications`.

- `GET /notifications`
- `POST /notifications/read-all`
- `POST /notifications/{notification_id}/read`
- `DELETE /notifications/clear-all`

## Newsletter

Routes are under `/newsletter`.

- `POST /newsletter/subscribe`
- `POST /newsletter/unsubscribe`
- `GET /newsletter/unsubscribe`
- `GET /newsletter/subscribers`
- `POST /newsletter/send`

## Admin

Routes are under `/admin` and require admin access.

- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/reset-password`
- `GET /admin/newsletter/subscribers`
- `GET /admin/newsletter/users`
- `DELETE /admin/newsletter/subscribers/{subscriber_id}`
- `POST /admin/newsletter/send`

## Debug

Routes are under `/debug`.

- `GET /debug/ai-config`

## Health Endpoints (outside `/api/v1`)

- `GET /health/live`
- `GET /health/ready`
- `GET /health`

## Error Envelope

Standard error response format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message"
  }
}
```

## OpenAPI UI

- `GET /docs` (only when docs are enabled)
- `GET /redoc` (only when docs are enabled)
