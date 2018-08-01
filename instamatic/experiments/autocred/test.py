import threading
import time
from queue import Queue

def d(q):
    i = 1
    while True:
        print("threading running")
        time.sleep(1)
        q.put(i)
        i = i + 1

q = Queue(maxsize= 1)
t = threading.Thread(target=d, name = "daemon", args = (q, ))
t.daemon = True
t.start()

stopEvent = threading.Event()
i = 0

while not stopEvent.is_set():
    print("main running...")
    i = i+1
    print(q.get())
    time.sleep(1)
    if i == 10:
        stopEvent.set()