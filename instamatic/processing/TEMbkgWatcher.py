from instamatic import TEMController
import threading
import numpy as np
import time
import socket
import pickle

def getTEMStatus(ctrl):
    print("Background ctrl object is reading...")
    TEMStatus = ctrl.to_dict()
    TEMStatus = {'position': ctrl.stageposition.get(),
                 'magnification': ctrl.magnification.get()}
    #return TEMStatus
    rand = np.random.random((1,3))
    return rand

class TemReader(threading.Thread):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.TEMStatus = getTEMStatus(self.ctrl)
    
    def run(self):
        while True:
            self.TEMStatus = getTEMStatus(self.ctrl)
            time.sleep(1)
        
def main():
    ctrl = TEMController.initialize(camera = 'disable')
    
    tem_reader = TemReader(ctrl)
    tem_reader.start()
    
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind(('localhost', 8090))
    serversocket.listen(5)
    connection, address = serversocket.accept()
    
    while 1:
        buf = connection.recv(1024)
        if len(buf) > 0:
            if buf.decode() == "s":
                TEMStatus = tem_reader.TEMStatus
                connection.send(pickle.dumps(TEMStatus))
            elif buf.decode() == "exit":
                break
            else:
                connection.send(buf)
        
if __name__ == '__main__':
    main()