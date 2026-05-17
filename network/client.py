# Placeholder for network client (HTTP/WebSocket)

class NetworkClient:
    def __init__(self):
        print("[NETWORK] Initialized client")

    def send(self, data):
        print(f"[NETWORK] Sending: {data}")

    def receive(self):
        print("[NETWORK] Receiving data")
        return None
