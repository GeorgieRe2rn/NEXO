from threading import Lock

# Un escritor de ingesta por proceso; especialmente importante con SQLite.
feed_lock = Lock()
