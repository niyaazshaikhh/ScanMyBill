# ER Diagram Description

## Entities and Relationships

1. `User` -> `Client` (1-to-many)
- One user owns many clients.
- Each client belongs to exactly one user (`clients.owner_id`).

2. `User` -> `Invoice` (1-to-many)
- One user owns many invoices.
- Each invoice belongs to exactly one user (`invoices.owner_id`).

3. `Client` -> `Invoice` (1-to-many, optional link on invoice)
- One client can have many invoices.
- Invoice can be unlinked (`client_id` nullable) for OCR imports before client mapping.

4. `Invoice` -> `InvoiceItem` (1-to-many)
- Each invoice contains multiple items.
- Items are deleted when invoice is deleted (`CASCADE`).

5. `Invoice` -> `BillUpload` (1-to-0/1)
- Uploaded bill can generate one structured invoice.
- Upload keeps OCR text and file metadata for traceability.

6. `User` -> `BillUpload` (1-to-many)
- One user can upload many bill files.

7. `User` -> `PaymentEvent` (1-to-many)
- Tracks Razorpay subscription/payment lifecycle records per user.

## Textual ER Representation

`User (1) --- (M) Client`

`User (1) --- (M) Invoice --- (M) InvoiceItem`

`Client (1) --- (M) Invoice`

`User (1) --- (M) BillUpload --- (0..1) Invoice`

`User (1) --- (M) PaymentEvent`