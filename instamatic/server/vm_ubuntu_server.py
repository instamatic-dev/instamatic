import ast
import datetime
import logging
import subprocess as sp
import threading
import time
from pathlib import Path
from socket import *

import virtualbox

from instamatic import config

HOST = config.settings.VM_server_host
PORT = config.settings.VM_server_port
VM_ID = config.settings.VM_ID
VM_USERNAME = config.settings.VM_USERNAME
VM_PWD = config.settings.VM_PWD
VM_DELAY1 = config.settings.VM_STARTUP_DELAY
VM_DELAY2 = config.settings.VM_DESKTOP_DELAY
VM_SF = config.settings.VM_SHARED_FOLDER
#ENABLE_SHELXT = config.settings.ENABLE_SHELXT
BUFF = 1024


def start_vm_process(vmname=VM_ID, vmachine_pwd=VM_PWD, time_delay=VM_DELAY1, mode='headless'):
    """mode can be either gui or headless."""
    try:
        vbox = virtualbox.VirtualBox()
    except ModuleNotFoundError:
        print('Please install virtualbox with guest ubuntu and virtualbox SDK first before using this server.')
        print('Download virtualbox python SDK from:')
        print('https://www.virtualbox.org/wiki/Downloads')

    session = virtualbox.Session()
    machine = vbox.find_machine(vmname)
    progress = machine.launch_vm_process(session, mode, '')
    progress.wait_for_completion()

    """wait for certain sec to ensure a normal vm startup"""
    time.sleep(time_delay)

    """assume vm is password protected"""
    session.console.keyboard.put_keys(vmachine_pwd)
    session.console.keyboard.put_keys(['ENTER'])
    print('password delivered!')
    return session


def vm_ubuntu_start_terminal(session):
    """type ctrl+alt+t to bring up terminal in the ubuntu machine."""
    session.console.keyboard.put_keys(press_keys='t', hold_keys=['CTRL', 'ALT'])


def vm_ubuntu_execute_script(vmname=VM_ID, vmachine_username=VM_USERNAME, vmachine_pwd=VM_PWD, time_delay=30, script_path='/usr/loca/bin/xds'):
    try:
        vbox = virtualbox.VirtualBox()
    except ModuleNotFoundError:
        print('Please install virtualbox with guest ubuntu and virtualbox SDK first before using this server.')
        print('Download virtualbox python SDK from:')
        print('https://www.virtualbox.org/wiki/Downloads')

    session = virtualbox.Session()
    machine = vbox.find_machine(vmname)
    progress = machine.launch_vm_process(session, 'headless', '')
    time.sleep(time_delay)

    gs = session.console.guest.create_session(vmachine_username, vmachine_pwd)

    process, stdout, stderr = gs.execute(script_path)
    print(stdout)


def vm_ubuntu_start_xds_AtFolder(session, conn, shelxt, unitcell, spgr, composition):
    """incoming conn should contain a path that is shared already between VBox
    and windows."""

    #path = "/media/sf_SharedWithVM/test_vm_server"

    while True:

        try:
            data = conn.recv(BUFF).decode()
        except ConnectionResetError:
            print('cRED experiment ended and connection was forcely closed.')
            print('A new cRED experiment will build a new connection.')
            break

        now = datetime.datetime.now().strftime('%H:%M:%S.%f')

        if not data:
            break

        print(f'{now} | {data}')
        if data == 'close':
            print(f'{now} | closing connection')
            conn.send(b'Connection closed')
            conn.close()
            break
        elif data == 'kill':
            print(f'{now} | closing down VM')
            close_down_vm_process(session)
            print('VM closed down safely!')
            conn.send(b'Connection closed')
            conn.close()
            break
        else:
            conn.send(b'OK')
            data = ast.literal_eval(data)
            path = data['path']
            slashindex = VM_SF.rfind('\\')
            path_vm = path.replace(VM_SF[:slashindex + 1], '\\media\\sf_')
            path_vm = path_vm.replace('\\', '/')
            session.console.keyboard.put_keys('cd ')
            session.console.keyboard.put_keys(f'{path_vm}')
            session.console.keyboard.put_keys(['ENTER'])

            session.console.keyboard.put_keys('xds')
            session.console.keyboard.put_keys(['ENTER'])

            """Not sure if I should put some delay here, but just to avoid neglected communication"""
            time.sleep(120)

            if shelxt:
                try:
                    generate_xdsconv_input(path)
                    session.console.keyboard.put_keys('xdsconv')
                    session.console.keyboard.put_keys(['ENTER'])
                    time.sleep(5)

                    generate_shelxt_input(unitcell, spgr, composition, path)
                    solve_structure_shelxt(path)

                except Exception as e:
                    print(e)
                    print('Because of the error auto structure solution could not be performed.')

    print('Connection closed')


def close_down_vm_process(session):
    session.console.power_down()


def generate_shelxt_input(unitcell, spgr, composition, path):
    from edtools.make_shelx import comp2dict, get_latt_symm_cards, get_sfac
    composition = comp2dict(composition)

    if unitcell is None:
        with open(Path(path) / 'CORRECT.LP', 'r') as f:
            for line in f:
                if line.startswith(' UNIT_CELL_CONSTANTS='):
                    cell = list(map(float, line.strip('\n').split()[1:7]))
                elif line.startswith(' UNIT CELL PARAMETERS'):
                    cell = list(map(float, line.strip('\n').split()[3:9]))
    else:
        cell = [float(ucl) for ucl in unitcell]

    if spgr is None:
        with open(Path(path) / 'CORRECT.LP', 'r') as f:
            for line in f:
                if line.startswith(' SPACE GROUP NUMBER'):
                    spgr = int(line.strip('\n').split()[-1])
                elif line.startswith(' SPACE_GROUP_NUMBER='):
                    spgr = int(line.strip('\n').split()[1])
    else:
        spgr = str(spgr)

    wavelength = config.microscope.wavelength
    a, b, c, al, be, ga = cell
    spgr = str(spgr)
    out = Path(path) / 'shelx.ins'

    f = open(out, 'w')

    print(f'TITL {spgr}', file=f)
    print(f'CELL {wavelength:.4f} {a:6.3f} {b:6.3f} {c:6.3f} {al:7.3f} {be:7.3f} {ga:7.3f}', file=f)
    print(f'ZERR 1.00    0.000  0.000  0.000   0.000   0.000   0.000', file=f)

    LATT, SYMM = get_latt_symm_cards(spgr)

    print(LATT, file=f)
    for line in SYMM:
        print(line, file=f)

    UNIT = 'UNIT'
    for name, number in composition.items():
        SFAC = get_sfac(name)
        print(SFAC, file=f)
        UNIT += f' {number}'

    print(UNIT, file=f)
    print('TREF 5000', file=f)
    print('HKLF 4', file=f)
    print('END', file=f)
    print(f'SHELXT ins file generated at {path}.')


def generate_xdsconv_input(path):
    out = Path(path) / 'XDSCONV.INP'
    f = open(out, 'w')
    print("""
INPUT_FILE= XDS_ASCII.HKL
INCLUDE_RESOLUTION_RANGE= 20 0.8 ! optional
OUTPUT_FILE= shelx.hkl  SHELX    ! Warning: do _not_ name this file "temp.mtz" !
FRIEDEL'S_LAW= FALSE             ! default is FRIEDEL'S_LAW=TRUE""", file=f)

    print(f'Wrote xdsconv input file at {path}.')


def solve_structure_shelxt(path, ins_name='shelx'):
    CWD = str(path)
    cmd = ['shelxt', ins_name]
    print(f'SHELXT attempting at {path}...')
    p = sp.Popen(cmd, cwd=CWD, stdout=sp.PIPE)
    for line in p.stdout:
        if b'R1  Rweak' in line:
            print(f'Possible solution found at {path}!!!')

    p.wait()
    print('Shelxt finished running.')


def main():
    import argparse

    description = """
The script sets up socket connection between `instamatic` and `VirtualBox` software via `virtualbox` python API. Therefore, `VirtualBox` and the corresponding SDK need to be installed before running this command. This script is developed particularly for the possibility of running `XDS` under windows 7 or newer, a system which a lot of TEM computers may be using.

After installation of VirtualBox and the corresponding SDK, `XDS` needs to be installed correctly in the guest Ubuntu system. In addition, a shared folder between `VirtualBox` and windows system needs to be set up properly in order for the server to work.

The host and port are defined in `config/settings.yaml`.
"""

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-shelxt',
                        action='store_true', dest='shelxt',
                        help='Run SHELXT when xds ASCII HKL file is generated.')

    parser.add_argument('-c', '--unitcell',
                        action='store', type=str, nargs=6, dest='unitcell',
                        metavar=('a', 'b', 'c', 'al', 'be', 'ga'),
                        help='Six numbers of the unit cell parameters.')

    parser.add_argument('-s', '--spgr',
                        action='store', type=str, dest='spgr',
                        help='Space group.')

    parser.add_argument('-m', '--composition',
                        action='store', type=str, nargs='+', dest='composition', metavar=('Xn', 'Ym'),
                        help='Unit cell composition, i.e. `-m H2 O1`.')

    parser.set_defaults(shelxt=False,
                        unitcell=None,
                        spgr=None,
                        composition=None)

    options = parser.parse_args()

    shelxt = options.shelxt
    unitcell = options.unitcell
    spgr = options.spgr
    composition = options.composition

    #print(shelxt, unitcell, spgr, composition)

    total_wait_sec = VM_DELAY1 + VM_DELAY2 + 10
    print('Starting Ubuntu server installed in VirtualBox...')
    print(f'Please allow around {total_wait_sec} sec for VM to finish start-up process.')
    session = start_vm_process()
    time.sleep(VM_DELAY2)
    vm_ubuntu_start_terminal(session)
    print('Ctrl Alt T sent!')

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_xdsVM_server_{date}.log'
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
            threading.Thread(target=vm_ubuntu_start_xds_AtFolder, args=(session, conn, shelxt, unitcell, spgr, composition)).start()

    # time.sleep(5)
    # vm_ubuntu_start_xds_AtFolder(session)
    # time.sleep(5)
    # close_down_vm_process(session)
    # time.sleep(5)
    #print("VM server closed down safely!")


if __name__ == '__main__':
    main()
