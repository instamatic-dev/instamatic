"""Utility script to enable rotation control from a dmscript See
`https://github.com/instamatic-dev/instamatic/tree/master/dmscript` for
usage."""
import datetime
import logging
import subprocess as sp
import threading
from socket import *

from instamatic import config
from instamatic import TEMController


HOST = config.settings.fei_server_host
PORT = config.settings.fei_server_port


def handle(conn):
    while True:
        data = conn.recv(1024).decode()
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')

        if not data:
            break

        if data == 'close':
            break
        elif data == 'kill':
            break
        else:
            conn.send(b'Connection closed')
            conn.close()

            print('Connection closed')
            run_rotation_with_speed(data)


def run_rotation_with_speed(data):
    data = [float(s) for s in data.split(',')]
    target_angle = data[0]
    speed = data[1]
    print(f'Rotating to {target_angle} with speed level {speed}...')
    ctrl.stage.set_with_speed(a=target_angle, speed=speed)
    print('Rotation completed.')


def main():
    import argparse

    description = """
Utility script to enable rotation control from a dmscript. See [https://github.com/instamatic-dev/instamatic/tree/master/dmscript] for usage.
"""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    options = parser.parse_args()

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_temserver_Themis_{date}.log'
    logging.basicConfig(format='%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s',
                        filename=logfile,
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    ctrl = TEMController.initialize()

    s = socket(AF_INET, SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)

    log.info(f'TEM server listening on {HOST}:{PORT}')
    print(f'TEM server listening on {HOST}:{PORT}')

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()


if __name__ == '__main__':
    main()
