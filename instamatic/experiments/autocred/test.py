import threading
import time

def d():
    while True:
        print "threading running"
        time.sleep(1)    

t = threading.Thread(target=d, name = "daemon")
t.daemon = True
t.start()

stopEvent = threading.Event()
i = 0

while not stopEvent.is_set():
    print "main running..."
    i = i+1
    time.sleep(1)
    if i == 10:
        stopEvent.set()