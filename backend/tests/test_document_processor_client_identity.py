import unittest

from app.models.invoice import InvoiceType
from app.schemas.bill import DeliveryChallanExtractedPayload
from app.services.document_processor import (
    _determine_bill_type,
    _extract_invoice_party_identity,
    _resolve_client_identity,
)


def _empty_challan_payload() -> DeliveryChallanExtractedPayload:
    return DeliveryChallanExtractedPayload(
        challan_number=None,
        order_number=None,
        challan_date=None,
        from_party=None,
        to_party=None,
        subtotal=0.0,
        notes=None,
        items=[],
    )


class DocumentProcessorClientIdentityTests(unittest.TestCase):
    def test_determine_bill_type_prefers_company_gstin_role_match(self) -> None:
        bill_type = _determine_bill_type(
            document_type='gst_invoice',
            explicit_transaction_type='purchase',
            fallback=InvoiceType.PURCHASE,
            company_name='Acme Labs Pvt Ltd',
            company_gstin='27AAAAA0000A1Z5',
            seller_name='Acme Labs Private Limited',
            buyer_name='Client One',
            seller_gstin='27AAAAA0000A1Z5',
            buyer_gstin='29BBBBB1111B1Z6',
            from_party=None,
            to_party=None,
        )

        self.assertEqual(bill_type, InvoiceType.SALES)

    def test_determine_bill_type_uses_company_name_when_gstin_missing(self) -> None:
        bill_type = _determine_bill_type(
            document_type='delivery_challan',
            explicit_transaction_type=None,
            fallback=InvoiceType.PURCHASE,
            company_name='Acme Traders LLP',
            company_gstin=None,
            seller_name='Fallback Seller',
            buyer_name='Fallback Buyer',
            seller_gstin=None,
            buyer_gstin=None,
            from_party='Acme Traders LLP Warehouse',
            to_party='Customer Depot',
        )

        self.assertEqual(bill_type, InvoiceType.SALES)

    def test_extract_invoice_party_identity_from_nested_objects(self) -> None:
        raw = {
            'seller': {
                'name': 'Vendor Corp',
                'gstin': '27AAAAA0000A1Z5',
            },
            'buyer': {
                'name': 'Buyer Retail',
                'gstin': '29BBBBB1111B1Z6',
            },
        }

        seller_name, buyer_name, seller_gstin, buyer_gstin = _extract_invoice_party_identity(raw)

        self.assertEqual(seller_name, 'Vendor Corp')
        self.assertEqual(buyer_name, 'Buyer Retail')
        self.assertEqual(seller_gstin, '27AAAAA0000A1Z5')
        self.assertEqual(buyer_gstin, '29BBBBB1111B1Z6')

    def test_resolve_client_identity_for_sales_invoice_uses_buyer(self) -> None:
        client_name, client_gstin = _resolve_client_identity(
            document_type='gst_invoice',
            bill_type=InvoiceType.SALES,
            challan_payload=_empty_challan_payload(),
            seller_name='Vendor Corp',
            buyer_name='Buyer Retail',
            seller_gstin='27AAAAA0000A1Z5',
            buyer_gstin='29BBBBB1111B1Z6',
            fallback_gstin=None,
        )

        self.assertEqual(client_name, 'Buyer Retail')
        self.assertEqual(client_gstin, '29BBBBB1111B1Z6')

    def test_resolve_client_identity_for_purchase_challan_uses_from_party(self) -> None:
        challan_payload = DeliveryChallanExtractedPayload(
            challan_number=7,
            order_number='SO-07',
            challan_date=None,
            from_party='Supplier One',
            to_party='My Company',
            subtotal=0.0,
            notes=None,
            items=[],
        )

        client_name, client_gstin = _resolve_client_identity(
            document_type='delivery_challan',
            bill_type=InvoiceType.PURCHASE,
            challan_payload=challan_payload,
            seller_name='Fallback Seller',
            buyer_name='Fallback Buyer',
            seller_gstin='27AAAAA0000A1Z5',
            buyer_gstin='29BBBBB1111B1Z6',
            fallback_gstin=None,
        )

        self.assertEqual(client_name, 'Supplier One')
        self.assertEqual(client_gstin, '27AAAAA0000A1Z5')

    def test_resolve_client_identity_uses_fallback_gstin(self) -> None:
        client_name, client_gstin = _resolve_client_identity(
            document_type='gst_invoice',
            bill_type=InvoiceType.SALES,
            challan_payload=_empty_challan_payload(),
            seller_name='Vendor Corp',
            buyer_name='Buyer Retail',
            seller_gstin='27AAAAA0000A1Z5',
            buyer_gstin=None,
            fallback_gstin='29BBBBB1111B1Z6',
        )

        self.assertEqual(client_name, 'Buyer Retail')
        self.assertEqual(client_gstin, '29BBBBB1111B1Z6')


if __name__ == '__main__':
    unittest.main()
