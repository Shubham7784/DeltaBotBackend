import requests
headers = {
  'Accept': 'application/json',
  'api-key': '****',
  'signature': '****',
  'timestamp': '****'
}

r = requests.get('https://api.india.delta.exchange/v2/wallet/balances', params={

}, headers = headers)

print(r.json())