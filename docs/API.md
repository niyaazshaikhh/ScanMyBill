# API Documentation (v1)

Last updated: March 26, 2026

Base URL: `http://localhost:8000/api/v1`  
Health endpoints: `http://localhost:8000/health/*`

## Authentication (`/auth`)

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

## Dashboard (`/dashboard`)

- `GET /dashboard/summary`
  - query: `period=monthly|quarterly|semi-annually|annually`
  - optional query: `year`, `financial_year_start`
- `GET /dashboard/admin-overview` (admin only)
- `POST /dashboard/assistant`
- `GET /dashboard/recent-uploads`
- `DELETE /dashboard/recent-uploads`

## Bills (`/bills`)

- `POST /bills/upload` (multipart/form-data)
  - fields: `file`, `invoice_type` (`sales` or `purchase`)
  - flow: upload validation -> AI/OCR extraction -> parsed invoice persistence

## Invoices (`/invoices`)

- `GET /invoices`
- `GET /invoices/latest-created`
- `POST /invoices/create`
- `POST /invoices/create/pdf`
- `GET /invoices/export-folder`
- `DELETE /invoices/{invoice_id}`
- `GET /invoices/{invoice_id}`
- `GET /invoices/{invoice_id}/preview`
- `GET /invoices/{invoice_id}/pdf`

## Delivery Challans (`/delivery-challans`)

- `GET /delivery-challans`
- `GET /delivery-challans/latest-created`
- `POST /delivery-challans/create`
- `POST /delivery-challans/create/pdf`
- `DELETE /delivery-challans/{challan_id}`
- `GET /delivery-challans/{challan_id}/preview`
- `GET /delivery-challans/{challan_id}/pdf`

## Clients (`/clients`)

- `GET /clients`
- `POST /clients`
- `GET /clients/analytics`
- `PUT /clients/{client_id}`
- `DELETE /clients/{client_id}`

## HSN/SAC Master (`/hsn-sac-master-list`)

- `GET /hsn-sac-master-list`
- `POST /hsn-sac-master-list`
- `PUT /hsn-sac-master-list/{entry_id}`
- `DELETE /hsn-sac-master-list/{entry_id}`

## Payments (`/payments`)

- `GET /payments/config`
- `POST /payments/orders`
- `POST /payments/subscriptions`
- `POST /payments/subscriptions/cancel`
- `POST /payments/verify`
- `POST /payments/webhook`

Recommended checkout sequence:

1. Frontend calls `POST /payments/orders`.
2. Backend creates Razorpay order and stores status.
3. Frontend opens Razorpay checkout with `order_id`.
4. Frontend posts signature payload to `POST /payments/verify`.
5. Backend verifies signature and marks payment as completed.

## Users (`/users`)

- `GET /users/me`
- `PUT /users/notification-preference`
- `GET /users/personal-details`
- `PUT /users/personal-details`

## Notifications (`/notifications`)

- `GET /notifications`
- `POST /notifications/read-all`
- `DELETE /notifications/clear-all`
- `POST /notifications/{notification_id}/read`
- `POST /notifications/{notification_id}/undo-delete`

## Newsletter (`/newsletter`)

- `POST /newsletter/subscribe`
- `POST /newsletter/unsubscribe`
- `GET /newsletter/unsubscribe`
- `GET /newsletter/subscribers`
- `POST /newsletter/send`

## Admin (`/admin`)

Admin routes require admin access.

- `GET /admin/users`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/reset-password`
- `GET /admin/newsletter/subscribers`
- `GET /admin/newsletter/users`
- `DELETE /admin/newsletter/subscribers/{subscriber_id}`
- `POST /admin/newsletter/send`

## Debug (`/debug`)

- `GET /debug/ai-config`

## Health Endpoints (outside `/api/v1`)

- `GET /health/live`
- `GET /health/ready`
- `GET /healthz`
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
