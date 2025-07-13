import asyncio
import websockets
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CONNECTED_CLIENTS = set()
BROADCAST_QUEUE: asyncio.Queue[str] = asyncio.Queue()

async def register(websocket):
    """Registers a new WebSocket client."""
    CONNECTED_CLIENTS.add(websocket)
    logging.info(f"Client connected: {websocket.remote_address}. Total clients: {len(CONNECTED_CLIENTS)}")

async def unregister(websocket):
    """Unregisters a disconnected WebSocket client."""
    CONNECTED_CLIENTS.remove(websocket)
    logging.info(f"Client disconnected: {websocket.remote_address}. Total clients: {len(CONNECTED_CLIENTS)}")

async def consumer_handler(websocket):
    await register(websocket)
    try:
        async for message in websocket:
            logging.info(f"Received message from {websocket.remote_address}: {message}")
            await websocket.send(f"Server received your message: {message}")
    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Connection closed normally for {websocket.remote_address}")
    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Connection closed with error for {websocket.remote_address}: {e}")
    finally:
        await unregister(websocket)

async def producer_handler():
    while True:
        message: str = await BROADCAST_QUEUE.get()
        logging.info(f"Broadcasting message from queue: '{message}' to {len(CONNECTED_CLIENTS)} clients.")
        await broadcast_message(message)
        BROADCAST_QUEUE.task_done()

async def broadcast_message(message: str):
    if not CONNECTED_CLIENTS:
        logging.warning("No clients connected to broadcast message to.")
        return

    send_tasks = []
    for client in list(CONNECTED_CLIENTS):
        try:
            send_tasks.append(client.send(message))
        except Exception as e:
            logging.error(f"Error preparing message for client {client.remote_address}: {e}")

    if send_tasks:
        results = await asyncio.gather(*send_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                client = list(CONNECTED_CLIENTS)[i]
                logging.error(f"Failed to send message to client {client.remote_address} due to: {result}")


def run_websocket_server_in_thread(host: str = "127.0.0.1", port: int = 8765):
    logging.info(f"Starting WebSocket server on ws://{host}:{port} in a new thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    start_server = websockets.serve(consumer_handler, host, port)

    loop.run_until_complete(asyncio.gather(
        start_server,
        producer_handler()
    ))
    loop.run_forever()
    logging.info("WebSocket server thread stopped.")

def broadcast_from_main(message: str):
    try:
        BROADCAST_QUEUE.put_nowait(message)
        logging.info(f"Message '{message}' put into broadcast queue from main thread.")
    except asyncio.QueueFull:
        logging.warning("Broadcast queue is full. Message dropped.")
    except Exception as e:
        logging.error(f"Error putting message into queue: {e}")

if __name__ == "__main__":
    logging.info("Running WebSocket server independently for testing...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(websockets.serve(consumer_handler, "127.0.0.1", 8765))
    logging.info("WebSocket server started. Press Ctrl+C to exit.")

    async def test_broadcast():
        await asyncio.sleep(5)
        await broadcast_message("Hello from the server's internal test broadcast!")
        await asyncio.sleep(5)
        await broadcast_message("This is another test message!")

    loop.run_until_complete(test_broadcast())
    loop.run_forever()
