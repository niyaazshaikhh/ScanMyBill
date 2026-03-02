import os
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("AZURE_DOC_INT_ENDPOINT")
key = os.getenv("AZURE_DOC_INT_KEY")

client = DocumentAnalysisClient(
    endpoint=endpoint,
    credential=AzureKeyCredential(key)
)

with open("sample_invoice.pdf", "rb") as f:
    poller = client.begin_analyze_document(
        "prebuilt-invoice",
        document=f
    )
    result = poller.result()

for doc in result.documents:
    print("Invoice Number:", doc.fields.get("InvoiceId").value)
    print("Invoice Date:", doc.fields.get("InvoiceDate").value)
    print("Vendor Name:", doc.fields.get("VendorName").value)
    print("Total Amount:", doc.fields.get("InvoiceTotal").value)