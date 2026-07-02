import asyncio
import websockets

async def ws_listen():
    uri = "ws://127.0.0.1:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to websocket, listening for messages for 20s...")
            end = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    print("MSG:", msg[:1000])
                except asyncio.TimeoutError:
                    # no message in this interval
                    continue
    except Exception as e:
        print("WebSocket client error:", e)

if __name__ == '__main__':
    asyncio.run(ws_listen())
