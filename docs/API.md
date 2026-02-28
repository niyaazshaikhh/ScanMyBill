# API Documentation (v1)

Base URL: `http://localhost:8000/api/v1`
Interactive docs: `http://localhost:8000/docs`

## Authentication

### `POST /auth/register`
Register a user and return JWT.

Request body:
```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "John Doe"
}
```

### `POST /auth/login`
Email/password login and return JWT.

### `POST /auth/google`
Google OAuth login via ID token.

### `GET /auth/me`
Get current authenticated user.

## Dashboard

### `GET /dashboard/summary?period=monthly|quarterly|semi-annually|annually`
Returns:
- Total Sales
- Total Purchases
- GST Collected
- GST Paid
- GST Payable
- Trend data for charts
- GST pie segments

## Bills/OCR

### `POST /bills/upload` (multipart/form-data)
Fields:
- `file` (image/pdf)
- `invoice_type` (`sales` or `purchase`)

Flow:
- Secure upload validation
- OCR extraction (Tesseract)
- Structured data parsing
- Invoice creation from extracted values

## Invoices

### `GET /invoices`
Query params:
- `period`
- `invoice_type`
- `bucket` (optional folder filter)

### `POST /invoices/create`
Create manual invoice with items.

### `GET /invoices/{invoice_id}`
Get invoice details.

### `GET /invoices/{invoice_id}/pdf`
Download single invoice PDF.

### `GET /invoices/export-folder?period=...&bucket=...&invoice_type=...`
Download combined folder PDF.

## Clients

### `GET /clients`
List clients + total transactions + total revenue.

### `POST /clients`
Create client.

### `GET /clients/analytics`
Overview metrics and top clients.

## Payments (Razorpay Demo)

### `GET /payments/config`
Returns publishable key for frontend checkout.

### `POST /payments/subscriptions/demo`
Creates demo subscription (or mock when keys are absent).

### `POST /payments/verify`
Verifies Razorpay subscription payment signature.