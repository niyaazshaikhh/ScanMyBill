# ERD Description

Last updated: March 26, 2026

This summarizes active entity relationships in the backend model layer.

## Primary Relationships

1. `User` -> `Client` (1-to-many)  
`clients.owner_id` references `users.id`.

2. `User` -> `Invoice` (1-to-many)  
`invoices.owner_id` references `users.id`.

3. `Client` -> `Invoice` (1-to-many, optional on invoice)  
`invoices.client_id` is nullable (`SET NULL` on delete).

4. `Invoice` -> `InvoiceItem` (1-to-many)  
`invoice_items.invoice_id` uses `CASCADE` delete.

5. `User` -> `NonGSTChallan` (1-to-many)  
`non_gst_challans.owner_id` references `users.id`.

6. `Client` -> `NonGSTChallan` (1-to-many, optional)  
`non_gst_challans.client_id` is nullable (`SET NULL` on delete).

7. `NonGSTChallan` -> `NonGSTChallanItem` (1-to-many)  
`non_gst_challan_items.challan_id` uses `CASCADE` delete.

8. `User` -> `BillUpload` (1-to-many)  
`bill_uploads.owner_id` references `users.id`.

9. `Invoice` -> `BillUpload` (1-to-0/1)  
Uploads can be linked for traceability via nullable `bill_uploads.invoice_id`.

10. `User` -> `HSNSACMaster` (1-to-many)  
`hsn_sac_masters.owner_id` references `users.id`.

11. `User` -> `PersonalDetails` (1-to-1)  
`personal_details.owner_id` is unique.

12. `User` -> `PaymentEvent` (1-to-many)  
`payment_events.owner_id` references `users.id`.

13. `User` -> `Notification` (1-to-many)  
`notifications.owner_id` references `users.id`.

14. `User` -> `UserSession` (1-to-many)  
`user_sessions.user_id` references `users.id`.

15. `User` -> `PasswordResetToken` (1-to-many)  
`password_reset_tokens.user_id` references `users.id`.

16. `User` -> `RevokedToken` (1-to-many)  
`revoked_tokens.user_id` references `users.id`.

17. `User` -> `RecentUploadState` (1-to-0/1)  
`recent_upload_states.owner_id` is both PK and FK.

18. `User` -> `UndoDeleteRecord` (1-to-many)  
`undo_delete_records.owner_id` references `users.id` and stores short-lived restore payloads.

19. `NewsletterSubscriber` (standalone)  
Public newsletter list not bound to auth user identity.

20. `TokenBlacklist` (standalone)  
Legacy/global blacklist entries keyed by token/hash.

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

`User (1) --- (0..1) RecentUploadState`

`User (1) --- (M) UndoDeleteRecord`
