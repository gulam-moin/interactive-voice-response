from twilio.rest import Client

# Your Account SID and Auth Token from Twilio Console (as strings)
account_sid = 'AC27a3ff623958d4c3f6b841ad08106cdb'
auth_token = '2df88fcd3e7b5eeeca2f587188bd25f3'

client = Client(account_sid, auth_token)

call = client.calls.create(
    to='+919844869941',          # Your verified Indian phone number with country code and quotes
    from_='+17576974901',        # Your Twilio phone number with country code and quotes
    url='https://6b50bb1719bf.ngrok-free.app/ivr' # Your ngrok URL with /ivr path and quotes
)

print("Call initiated! Call SID:", call.sid)
