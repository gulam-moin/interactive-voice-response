import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

from_number = os.environ.get("TWILIO_FROM_NUMBER")
to_number = os.environ.get("TWILIO_TO_NUMBER")
ngrok_url = os.environ.get("NGROK_URL")

client = Client(account_sid, auth_token)

call = client.calls.create(
    to=to_number,
    from_=from_number,
    url=ngrok_url
)

print("Call initiated! Call SID:", call.sid)
