import datetime
import logging
import subprocess as sp
import threading
from pathlib import Path
from socket import *

from instamatic import config

HOST = config.settings.indexing_server_host
PORT = config.settings.indexing_server_port
BUFF = 1024

rlock = threading.RLock()


def parse_xds(path):
    """Parse the XDS output file `CORRECT.LP` and print a summary."""
    from instamatic.utils.xds_parser import xds_parser

    fn = Path(path) / 'CORRECT.LP'

    # rlock prevents messages getting mangled with
    # simultaneous print statements from different threads
    with rlock:
        if not fn.exists():
            print(f'FAIL: Cannot find file `{fn.name}`, was the indexing successful??')
            msg = f'{path}: Automatic indexing failed...'
        else:
            try:
                p = xds_parser(fn)
            except UnboundLocalError:
                msg = f'{path}: Automatic indexing completed but no cell reported...'
                print(f'FAIL: `{fn.name}` found, but could not be parsed...')
            else:
                msg = '\n'
                msg += p.cell_info()
                msg += '\n'
                msg += p.integration_info()
                msg += '\n'
                print(msg)

    return msg


def run_xds_indexing(path):
    """Call XDS on the given `path`.

    Uses WSL (Windows 10 only).
    """
    p = sp.Popen('bash -c xds_par 2>&1 >/dev/null', cwd=path)
    p.wait()

    msg = parse_xds(path)

    now = datetime.datetime.now().strftime('%H:%M:%S.%f')
    print(f'{now} | XDS indexing has finished')

    return msg


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
            msg = run_xds_indexing(data)
            conn.send(msg.encode())

    conn.send(b'Connection closed')
    conn.close()
    print('Connection closed')

    return ret


def main():
    import argparse

    description = f"""
Starts a simple XDS server to send indexing jobs to. Runs XDS for every job sent to it. Opens a socket on port {HOST}:{PORT}.

The data sent to the server as a bytes string containing the data path (must contain `cRED_log.txt`).
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

    log.info(f'Indexing server (XDS) listening on {HOST}:{PORT}')
    print(f'Indexing server (XDS) listening on {HOST}:{PORT}')

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn,)).start()


if __name__ == '__main__':
    main()
