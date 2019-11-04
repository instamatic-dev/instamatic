from socket import *
import datetime
from instamatic import config
from instamatic.goniotool import GonioToolWrapper
import threading
import logging

"""
Utility script for remote/automated control of `GonioTool`
"""

goniotool = GonioToolWrapper()
goniotool.startup()

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
            set_rotation_speed(data)


def set_rotation_speed(data):
    speed = int(data)
    print(f"Setting rotation speed to `{speed}`")
    goniotool.set_rate(speed)


def main():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_goniotool_server_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)
    
    s = socket(AF_INET, SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)
    
    log.info(f"Goniotool server listening on {HOST}:{PORT}")
    print(f"Goniotool server listening on {HOST}:{PORT}")
    
    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()
            
if __name__ == '__main__':
    main()
