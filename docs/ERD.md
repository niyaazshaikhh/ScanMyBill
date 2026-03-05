# ERD Description

This document summarizes the active entity relationships in the backend model layer.

## Primary Relationships

1. `User` -> `Client` (1-to-many)
- A user owns multiple clients.
- `clients.owner_id` references `users.id`.

2. `User` -> `Invoice` (1-to-many)
- A user owns multiple invoices.
- `invoices.owner_id` references `users.id`.

3. `Client` -> `Invoice` (1-to-many, optional on invoice)
- An invoice can be linked to a client or remain unlinked.
- `invoices.client_id` is nullable.

4. `Invoice` -> `InvoiceItem` (1-to-many)
- Each invoice has one or more line items.
- `invoice_items.invoice_id` uses `CASCADE` delete.

5. `User` -> `NonGSTChallan` (1-to-many)
- A user owns multiple delivery challans.
- `non_gst_challans.owner_id` references `users.id`.

6. `Client` -> `NonGSTChallan` (1-to-many, optional)
- A challan may optionally link to a client.
- `non_gst_challans.client_id` is nullable.

7. `NonGSTChallan` -> `NonGSTChallanItem` (1-to-many)
- Each challan has multiple items.
- `non_gst_challan_items.challan_id` uses `CASCADE` delete.

8. `User` -> `BillUpload` (1-to-many)
- Users can upload many bill files.
- `bill_uploads.owner_id` references `users.id`.

9. `Invoice` -> `BillUpload` (logical 1-to-0/1)
- Uploads can be attached to generated invoices for traceability.
- `bill_uploads.invoice_id` is nullable.

10. `User` -> `HSNSACMaster` (1-to-many)
- Users maintain reusable HSN/SAC tax rows.
- `hsn_sac_masters.owner_id` references `users.id`.

11. `User` -> `PersonalDetails` (1-to-1)
- Company/business identity profile per user.
- `personal_details.owner_id` is unique.

12. `User` -> `PaymentEvent` (1-to-many)
- Captures Razorpay lifecycle and verification records.
- `payment_events.owner_id` references `users.id`.

13. `User` -> `Notification` (1-to-many)
- Stores in-app notifications and read state.
- `notifications.owner_id` references `users.id`.

14. `User` -> `UserSession` (1-to-many)
- Refresh-token backed auth sessions.
- `user_sessions.user_id` references `users.id`.

15. `User` -> `PasswordResetToken` (1-to-many)
- Password reset token history.
- `password_reset_tokens.user_id` references `users.id`.

16. `User` -> `RevokedToken` (1-to-many)
- Tracks revoked token hashes for invalidation.
- `revoked_tokens.user_id` references `users.id`.

17. `NewsletterSubscriber` (standalone)
- Public newsletter list not bound to auth user identity.

18. `TokenBlacklist` (standalone)
- Legacy/global blacklist entries keyed by token text/hash.

## Text ER Snapshot

`User (1) --- (M) Client`

`User (1) --- (M) Invoice --- (M) InvoiceItem`

`Client (1) --- (M) Invoice`

`User (1) --- (M) NonGSTChallan --- (M) NonGSTChallanItem`

`Client (1) --- (M) NonGSTChallan`

`User (1) --- (M) BillUpload --- (0..1) Invoice`

`User (1) --- (M) HSNSACMaster`

`User (1) --- (1) PersonalDetails`

`User (1) --- (M) PaymentEvent`

`User (1) --- (M) Notification`

`User (1) --- (M) UserSession`

`User (1) --- (M) PasswordResetToken`

`User (1) --- (M) RevokedToken`
