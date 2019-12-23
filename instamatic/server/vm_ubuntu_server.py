import virtualbox
from socket import *
import time
import datetime
import logging
import threading
from instamatic import config
import ast

HOST = config.cfg.VM_server_host
PORT = config.cfg.VM_server_port
BUFF = 1024

def start_vm_process(vmname="Ubuntu 14.04.3", vmachine_pwd="testtest", time_delay=20):
	try:
		vbox = virtualbox.VirtualBox()
	except ModuleNotFoundError:
		print("Please install virtualbox with guest ubuntu and virtualbox SDK first before using this server.")
		print("Download virtualbox python SDK from:")
		print("https://www.virtualbox.org/wiki/Downloads")

	session = virtualbox.Session()
	machine = vbox.find_machine(vmname)
	progress = machine.launch_vm_process(session, "gui", "")
	progress.wait_for_completion()

	"""wait for 15 s to ensure a normal vm startup"""
	time.sleep(time_delay)

	"""assume vm is password protected"""
	session.console.keyboard.put_keys(vmachine_pwd)
	session.console.keyboard.put_keys(["ENTER"])
	return session


def vm_ubuntu_start_terminal(session):
	"""type ctrl+alt+t to bring up terminal in the ubuntu machine"""
	session.console.keyboard.put_keys(press_keys="t", hold_keys=["CTRL","ALT"])

def vm_ubuntu_start_xds_AtFolder(session, conn):
	"""incoming conn should contain a path that is shared already between VBox and windows"""
	
	#path = "/media/sf_SharedWithVM/test_vm_server"

	while True:
		data = conn.recv(BUFF).decode()
		data = ast.literal_eval(data)
		now = datetime.datetime.now().strftime("%H:%M:%S.%f")

		if not data:
			break

		print(f"{now} | {data}")
		if data == "close":
			print(f"{now} | closing connection")
			break
		elif data == "kill":
			print(f"{now} | closing down VM")
			close_down_vm_process(session)
			print("VM closed down safely!")
			break
		else:
			conn.send(b"OK")
			path = data #Need checking
			session.console.keyboard.put_keys("cd ")
			session.console.keyboard.put_keys("{}".format(path))
			session.console.keyboard.put_keys(["ENTER"])

			session.console.keyboard.put_keys("xds")
			session.console.keyboard.put_keys(["ENTER"])

			"""Not sure if I should put some delay here, but just to avoid neglected communication"""
			time.sleep(60)

	conn.send(b"Connection closed")
	conn.close()
	print("Connection closed")

def close_down_vm_process(session):
	session.console.power_down()

def main():
	print("Starting Ubuntu server installed in VirtualBox...")
	session = start_vm_process()
	time.sleep(15)
	vm_ubuntu_start_terminal(session)

	date = datetime.datetime.now().strftime("%Y-%m-%d")
	logfile = config.logs_drc / f"instamatic_xdsVM_server_{date}.log"
	logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s",
						filename=logfile,
						level=logging.DEBUG)
	logging.captureWarnings(True)
	log = logging.getLogger(__name__)

	s = socket(AF_INET, SOCK_STREAM)
	s.bind((HOST, PORT))
	s.listen(5)

	log.info(f"Indexing server (XDS) listening on {HOST}:{PORT}")
	print(f"Indexing server (XDS) listening on {HOST}:{PORT}")

	with s:
		while True:
			conn, addr = s.accept()
			log.info('Connected by %s', addr)
			print('Connected by', addr)
			threading.Thread(target=vm_ubuntu_start_xds_AtFolder, args=(session, conn,)).start()

	#time.sleep(5)
	#vm_ubuntu_start_xds_AtFolder(session)
	#time.sleep(5)
	#close_down_vm_process(session)
	#time.sleep(5)
	#print("VM server closed down safely!")

if __name__ == '__main__':
	main()