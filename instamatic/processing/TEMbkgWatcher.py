from instamatic import TEMController
import threading
import numpy as np
import time
import socket
import pickle
import logging
import datetime

def getTEMStatus(ctrl):
    #print("Background ctrl object is reading TEM...")
    TEMStatus = ctrl.to_dict()
    #TEMStatus = {'position': ctrl.stageposition.get(),
    #             'magnification': ctrl.magnification.get()}
    return TEMStatus
    #rand = np.random.random((1,3))
    #return rand
    
def getgonioStatus(ctrl):
    #print("Background ctrl object is reading gonio...")
    gonioStatus = ctrl.stageposition.get()
    
    return gonioStatus

class TemReader(threading.Thread):
    def __init__(self, ctrl, log):
        super().__init__()
        self.ctrl = ctrl
        self.log = log
        ## log file can be used to get the statistics of the TEM states.
        self.TEMStatus = getTEMStatus(self.ctrl)
        self.gonioStatus = getgonioStatus(self.ctrl)
    
    def run(self):
        while True:
            self.TEMStatus = getTEMStatus(self.ctrl)
            self.gonioStatus = getgonioStatus(self.ctrl)
            date = datetime.datetime.now().strftime("%Y-%m-%d")
            self.log.info("{} TEMStatus: {}; gonioStatus: {}".format(date, self.TEMStatus, self.gonioStatus))
            time.sleep(1)
        
def accept_connection(connection, tem_reader):
    
    while 1:
        buf = connection.recv(1024)
        if len(buf) > 0:
            if buf.decode() == "s":
                gonioStatus = tem_reader.gonioStatus
                connection.send(pickle.dumps(gonioStatus))
            elif buf.decode() == "exit":
                break
            else:
                connection.send(buf)
    connection.close()
    
def main():
    ctrl = TEMController.initialize(camera = 'disable')
    
    from instamatic import config
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_TEMWatcher_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    log.info("Instamatic watcher running in background. started")
    
    tem_reader = TemReader(ctrl, log)
    tem_reader.start()
    
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind(('localhost', 8090))
    serversocket.listen(5)

    while 1:
        connection, address = serversocket.accept()
        print(address)
        threading.Thread(target=accept_connection, args=(connection,tem_reader, )).start()
    
    serversocket.close()
    
if __name__ == '__main__':
    main()