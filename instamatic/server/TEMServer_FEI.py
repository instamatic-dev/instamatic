import subprocess as sp
from socket import *
import datetime
from instamatic import config
from instamatic import TEMController
import threading
import logging

"""
Utility script to enable rotation control from a dmscript
See `https://github.com/stefsmeets/instamatic/tree/master/dmscript` for usage
"""

ctrl = TEMController.initialize()

HOST = config.cfg.fei_server_host
PORT = config.cfg.fei_server_port


def handle(conn):
    while True:
        data = conn.recv(1024).decode()
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")
        
        if not data:
            break
        
        if data == "close":
            break
        elif data == "kill":
            break
        else:
            conn.send(b"Connection closed")
            conn.close()
            
            print("Connection closed")
            run_rotation_with_speed(data)


def run_rotation_with_speed(data):
    data = [float(s) for s in data.split(',')]
    target_angle = data[0]
    speed = data[1]
    print("Rotating to {} with speed level {}...".format(target_angle, speed))
    ctrl.stageposition.set_with_speed(a = target_angle, speed = speed)
    print("Rotation completed.")


def main():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_temserver_Themis_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    
    s = socket(AF_INET, SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)
    
    log.info(f"TEM server listening on {HOST}:{PORT}")
    print(f"TEM server listening on {HOST}:{PORT}")
    
    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()
            
if __name__ == '__main__':
    main()
