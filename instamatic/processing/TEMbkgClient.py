import socket
import pickle
import time

def acquire(task, socket):    
    socket.send(sending.encode())
    buf = socket.recv(1024)
    if len(buf) > 0:
        try:
            receiving = pickle.loads(buf)
        except:
            receiving = buf.decode()
        finally:
            return receiving

clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
clientsocket.connect(('localhost',8090))

while 1:
    sending = input('Acquire data?')
    t0 = time.clock()
    result = acquire(task=sending, socket=clientsocket)
    t1 = time.clock()
    print(f"{t1-t0:.5f} seconds")
    print(result)
    if sending == 'exit':
        break


