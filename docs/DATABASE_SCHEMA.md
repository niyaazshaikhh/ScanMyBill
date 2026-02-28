# Database Schema

## Tables

### `users`
- `id` (PK, UUID string)
- `email` (unique, indexed)
- `hashed_password` (nullable for OAuth-only users)
- `full_name`
- `role` (`admin` or `user`)
- `is_active`
- `created_at`

### `clients`
- `id` (PK)
- `owner_id` (FK -> `users.id`)
- `name`
- `email` (nullable)
- `phone` (nullable)
- `gst_number` (nullable)
- `created_at`

### `invoices`
- `id` (PK)
- `owner_id` (FK -> `users.id`)
- `client_id` (FK -> `clients.id`, nullable)
- `invoice_number` (indexed)
- `invoice_date` (indexed)
- `gst_number` (nullable)
- `type` (`sales` or `purchase`, indexed)
- `subtotal`
- `gst_amount`
- `total_amount`
- `source` (`uploaded` or `created`)
- `original_file_path` (nullable)
- `notes` (nullable)
- `created_at`

### `invoice_items`
- `id` (PK)
- `invoice_id` (FK -> `invoices.id`)
- `description`
- `quantity`
- `price`
- `gst_percent`
- `line_total`

### `bill_uploads`
- `id` (PK)
- `owner_id` (FK -> `users.id`)
- `invoice_id` (FK -> `invoices.id`, nullable)
- `file_name`
- `file_path`
- `mime_type`
- `file_size`
- `ocr_text` (nullable)
- `processed`
- `created_at`

### `payment_events`
- `id` (PK)
- `owner_id` (FK -> `users.id`)
- `provider`
- `provider_payment_id` (indexed)
- `status`
- `payload` (nullable JSON string)
- `created_at`

## Indexing Notes
- User lookup by email is indexed.
- Invoice filtering by owner/type/date is indexed through explicit and implicit indexes.
- Payment provider IDs are indexed for reconciliation.