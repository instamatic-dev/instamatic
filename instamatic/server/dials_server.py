import ast
import datetime
import logging
import subprocess as sp
import sys
import threading
from pathlib import Path
from socket import *

from instamatic import config


try:
    EXE = Path(sys.argv[1])
except BaseException:
    EXE = Path(config.settings.dials_script)

CWD = EXE.parent

HOST = config.settings.indexing_server_host
PORT = config.settings.indexing_server_port
BUFF = 1024


def run_dials_indexing(data):
    path = data['path']
    rotrange = data['rotrange']
    nframes = data['nframes']
    osc = data['osc']

    cmd = [str(EXE), path]
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    fn = config.locations['logs'] / f'Dials_indexing_{date}.log'
    unitcelloutput = []

    p = sp.Popen(cmd, cwd=CWD, stdout=sp.PIPE)
    for line in p.stdout:
        if b'Unit cell:' in line:
            print(line.decode('utf-8'))
            unitcelloutput = line

    if unitcelloutput:
        with open(fn, 'a') as f:
            f.write(f'\nData Path: {path}\n')
            f.write('{}'.format(unitcelloutput[4:].decode('utf-8')))
            f.write(f'Rotation range: {rotrange} degrees\n')
            f.write(f'Number of frames: {nframes}\n')
            f.write(f'Oscillation angle: {osc} deg\n\n\n\n')
            print(f'Indexing result written to dials indexing log file; path: {path}')

    p.wait()
    unitcelloutput = []
    now = datetime.datetime.now().strftime('%H:%M:%S.%f')
    print(f'{now} | DIALS indexing has finished')


def handle(conn):
    """Handle incoming connection."""
    ret = 0

    while True:
        data = conn.recv(BUFF).decode()
        now = datetime.datetime.now().strftime('%H:%M:%S.%f')

        if not data:
            break

        print(f'{now} | {data}')
        if data == 'close':
            print(f'{now} | Closing connection')
            break

        elif data == 'kill':
            print(f'{now} | Killing server')
            ret = 1
            break

        else:
            conn.send(b'OK')
            data = ast.literal_eval(data)
            run_dials_indexing(data)

    conn.send(b'Connection closed')
    conn.close()
    print('Connection closed')

    return ret


def main():
    import argparse

    description = f"""
Starts a simple server to send indexing jobs to. Runs `{EXE}` for every job sent to it. Opens a socket on port {HOST}:{PORT}.

The data sent to the server is a dict containing the following elements:

- `path`: Path to the data directory (str)
- `rotrange`: Total rotation range in degrees (float)
- `nframes`: Number of data frames (int)
- `osc`: Oscillation range in degrees (float)
"""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    options = parser.parse_args()

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_indexing_server_{date}.log'
    logging.basicConfig(format='%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s',
                        filename=logfile,
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    s = socket(AF_INET, SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)

    log.info(f'Indexing server (DIALS) listening on {HOST}:{PORT}')
    log.info(f'Running command: {EXE}')
    print(f'Indexing server (DIALS) listening on {HOST}:{PORT}')
    print(f'Running command: {EXE}')

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()


if __name__ == '__main__':
    main()
