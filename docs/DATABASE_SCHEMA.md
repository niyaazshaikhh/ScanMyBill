# Database Schema

Last updated: March 26, 2026

This document reflects SQLAlchemy models in `backend/app/models`.

## Core Identity and Access

### `users`
- `id` (PK, UUID string)
- `full_name`
- `email` (unique, indexed)
- `hashed_password` (nullable for OAuth accounts)
- `role` (`admin`, `user`)
- `is_active`
- `notifications_enabled`
- `failed_login_attempts`
- `account_locked_until` (nullable)
- `last_failed_login_at` (nullable)
- `subscription_plan` (`FREE`, `STANDARD`, `PRO`, `BUSINESS`)
- `subscription_status` (`ACTIVE`, `CANCELLED`, `EXPIRED`)
- `razorpay_subscription_id` (nullable, indexed)
- `subscription_started_at` (nullable)
- `subscription_expires_at` (nullable)
- `reset_token` (nullable, unique, indexed)
- `reset_token_expiry` (nullable)
- `created_at`
- `updated_at`

### `user_sessions`
- `id` (PK)
- `user_id` (FK -> `users.id`, indexed)
- `refresh_jti` (unique, indexed)
- `refresh_token_hash` (unique, indexed)
- `is_active` (indexed)
- `last_activity_at` (indexed)
- `inactive_expires_at` (indexed)
- `refresh_expires_at` (indexed)
- `revoked_at` (nullable)
- `created_at`
- `updated_at`

### `password_reset_tokens`
- `id` (PK)
- `user_id` (FK -> `users.id`, indexed)
- `token_hash` (unique, indexed)
- `expires_at` (indexed)
- `used_at` (nullable, indexed)
- `created_at`

### `revoked_tokens`
- `id` (PK)
- `user_id` (FK -> `users.id`, indexed)
- `token_hash` (unique, indexed)
- `jti` (nullable, indexed)
- `expires_at` (indexed)
- `revoked_at`

### `token_blacklist`
- `id` (PK)
- `token` (unique, indexed)
- `blacklisted_at` (indexed)

## Business Master Data

### `clients`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `name` (indexed)
- `address` (nullable)
- `state_name` (nullable)
- `state_code` (nullable)
- `email` (nullable)
- `phone` (nullable)
- `gst_number` (nullable)
- `created_at`

### `personal_details`
- `id` (PK)
- `owner_id` (FK -> `users.id`, unique, indexed)
- `company_name`
- `gstin_number` (unique, indexed)
- `address` (nullable)
- `state_name` (nullable)
- `state_code` (nullable)
- `gst_filing_period` (nullable)
- `email` (nullable)
- `bank_name` (nullable)
- `account_number` (nullable)
- `branch` (nullable)
- `ifsc_code` (nullable)
- `created_at`
- `updated_at`

### `hsn_sac_masters`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `description`
- `hsn_sac_code` (indexed)
- `tax_rate`
- `created_at`
- Unique constraint: `(owner_id, hsn_sac_code)`

## Invoices and Documents

### `invoices`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `client_id` (FK -> `clients.id`, nullable, `SET NULL` on delete)
- `invoice_number` (indexed)
- `invoice_date` (indexed)
- `place_of_supply` (nullable)
- `place_of_supply_code` (nullable)
- `gst_number` (nullable)
- `type` (`sales`, `purchase`, indexed)
- `subtotal`
- `gst_amount`
- `total_amount`
- `source` (`uploaded`, `created`)
- `original_file_path` (nullable)
- `notes` (nullable)
- `created_at`
- Runtime index guard: unique owner + invoice number

### `invoice_items`
- `id` (PK)
- `invoice_id` (FK -> `invoices.id`, indexed, `CASCADE` on delete)
- `description`
- `hsn_sac` (nullable)
- `quantity`
- `price`
- `gst_percent`
- `line_total`

### `bill_uploads`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `invoice_id` (FK -> `invoices.id`, nullable, `SET NULL` on delete)
- `file_name`
- `file_path`
- `mime_type`
- `file_size`
- `ocr_text` (nullable)
- `processed`
- `created_at`

### `non_gst_challans`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `client_id` (FK -> `clients.id`, nullable, indexed, `SET NULL` on delete)
- `challan_number` (indexed)
- `financial_year_start` (nullable, indexed)
- `sequence_number` (nullable, indexed)
- `challan_date` (indexed)
- `subtotal`
- `notes` (nullable)
- `original_file_path` (nullable)
- `created_at`
- Unique constraints:
  - `(owner_id, client_id, challan_number)`
  - `(owner_id, financial_year_start, sequence_number)`

### `non_gst_challan_items`
- `id` (PK)
- `challan_id` (FK -> `non_gst_challans.id`, indexed, `CASCADE` on delete)
- `description`
- `quantity`
- `rate`
- `line_total`

### `recent_upload_states`
- `owner_id` (PK, FK -> `users.id`)
- `cleared_at` (nullable)
- `created_at`
- `updated_at`

### `undo_delete_records`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `record_type` (`invoice`, `client`, indexed)
- `record_id` (indexed)
- `payload_json`
- `expires_at` (indexed)
- `consumed_at` (nullable, indexed)
- `created_at` (indexed)

## Platform and Engagement

### `payment_events`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `provider`
- `provider_payment_id` (indexed)
- `status`
- `payload` (nullable)
- `created_at`

### `notifications`
- `id` (PK)
- `owner_id` (FK -> `users.id`, indexed)
- `category` (`activity`, `alert`, `system`)
- `title`
- `message`
- `route` (nullable)
- `dedupe_key` (nullable)
- `is_read` (indexed)
- `created_at` (indexed)
- Unique constraint: `(owner_id, dedupe_key)`

### `newsletter_subscribers`
- `id` (PK)
- `email` (unique, indexed)
- `is_active`
- `subscribed_at`
- `unsubscribed_at` (nullable)

## Notes
- The backend currently auto-creates and adjusts schema at startup.
- Add explicit Alembic migrations before strict production rollout.
