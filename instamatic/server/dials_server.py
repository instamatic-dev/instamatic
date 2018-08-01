import time
import os, sys
import subprocess as sp
from socket import *
import datetime

from instamatic import config
import logging
import threading
from pathlib import Path


try:
    EXE = Path(sys.argv[1])
except:
    EXE = Path(config.cfg.dials_script)

CWD = EXE.parent

HOST = config.cfg.dials_server_host
PORT = config.cfg.dials_server_port
BUFF = 1024


def parse_dials_index_log(fn="dials.index.log"):
    with open(fn, "r") as f:
        print("Unit cell = ...")


def run_dials_indexing(path):
    cmd = [str(EXE), path]

    p = sp.Popen(cmd, cwd=CWD)
    p.wait()

    # parse_dials_index_log("dials.index.log")

    now = datetime.datetime.now().strftime("%H:%M:%S.%f")


def handle(conn):
    ret = 0

    while True:
        data = conn.recv(BUFF).decode()
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")

        if not data:
            break
    
        print("{now} | {data}".format(now=now, data=datadata))
        if data == "close":
            print("{now} | Closing connection".format(now=now))
            break

        elif data == "kill":
            print("{now} | Killing server".format(now=now))
            ret = 1
            break

        else:
            conn.send(b"OK")
            run_dials_indexing(data)

    conn.send(b"Connection closed")
    conn.close()
    print("Connection closed")

    return ret


def main():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / "instamatic_DialsServer_{date}.log".format(date=date)
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    s = socket(AF_INET, SOCK_STREAM)
    s.bind((HOST,PORT))
    s.listen(5)

    log.info("Dials server listening on {HOST}:{PORT}".format(HOST=HOST, PORT=PORT))
    log.info("Running command: {EXE}".format(EXE))
    print("Server listening on {HOST}:{PORT}".format(HOST=HOST, PORT=PORT))
    print("Running command: {EXE}".format(EXE))

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()

    
if __name__ == '__main__':
    main()