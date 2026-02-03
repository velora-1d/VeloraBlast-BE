import requests
import base64
import hashlib
import hmac
import os

MIDTRANS_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY", "SB-Mid-server-YOUR_SERVER_KEY")
MIDTRANS_CLIENT_KEY = os.getenv("MIDTRANS_CLIENT_KEY", "SB-Mid-client-YOUR_CLIENT_KEY")
IS_PRODUCTION = os.getenv("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"

BASE_URL = "https://app.midtrans.com/snap/v1" if IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/v1"

def get_auth_header():
    auth_string = f"{MIDTRANS_SERVER_KEY}:"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    return {"Authorization": f"Basic {encoded_auth}", "Content-Type": "application/json"}

def create_transaction(order_id: int, amount: int, item_name: str, customer_email: str):
    url = f"{BASE_URL}/transactions"
    payload = {
        "transaction_details": {
            "order_id": str(order_id),
            "gross_amount": amount
        },
        "item_details": [
            {
                "id": "subscription",
                "price": amount,
                "quantity": 1,
                "name": item_name
            }
        ],
        "customer_details": {
            "email": customer_email
        }
    }
    
    response = requests.post(url, json=payload, headers=get_auth_header())
    return response.json()

def verify_signature(order_id: str, status_code: str, gross_amount: str, signature_key: str):
    """Verifikasi signature dari webhook Midtrans"""
    raw_string = f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}"
    expected_signature = hashlib.sha512(raw_string.encode()).hexdigest()
    return expected_signature == signature_key
