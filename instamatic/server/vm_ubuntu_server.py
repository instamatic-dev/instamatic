import virtualbox
import time

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

def vm_ubuntu_start_xds_AtFolder(session, path= "/media/sf_SharedWithVM/test_vm_server"):
	session.console.keyboard.put_keys("cd ")
	session.console.keyboard.put_keys("{}".format(path))
	session.console.keyboard.put_keys(["ENTER"])

	session.console.keyboard.put_keys("xds")
	session.console.keyboard.put_keys(["ENTER"])

def close_down_vm_process(session):
	session.console.power_down()

def main():
	print("Starting Ubuntu server installed in VirtualBox...")
	session = start_vm_process()
	time.sleep(5)
	vm_ubuntu_start_terminal(session)
	time.sleep(5)
	vm_ubuntu_start_xds_AtFolder(session)
	time.sleep(5)
	close_down_vm_process(session)
	time.sleep(5)
	print("VM server closed down safely!")

if __name__ == '__main__':
    main()