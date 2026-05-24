import requests
import time
headers = {
  'Accept': 'application/json',
}
params = {
    'resolution':'4h',
    'symbol':'BTCUSD',
    'start': int(time.time()) - 40*4*60*60,
    'end':int(time.time())
}
r = requests.get('https://cdn-ind.testnet.deltaex.org/v2/history/candles', params= params, headers = headers)

result = r.json().get("result",[])
print(result[0])
print(len(result))