import threading
from werkzeug.serving import make_server

_server = None
_thread = None
_lock = threading.Lock()


def start_server():
    global _server, _thread

    with _lock:
        if _server is not None:
            return "SERVER_ALREADY_RUNNING"

        from app import app

        _server = make_server(
            "127.0.0.1",
            5000,
            app,
            threaded=True
        )

        _thread = threading.Thread(
            target=_server.serve_forever,
            daemon=True
        )
        _thread.start()

    return "SERVER_STARTED"
