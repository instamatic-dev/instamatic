import socket
import tkinter.filedialog
from pathlib import Path
from tkinter import *
from tkinter.ttk import *

from .base_module import BaseModule
from instamatic import config

scripts_drc = config.locations['scripts']

SERVER_EXE = config.settings.indexing_server_exe
HOST = config.settings.indexing_server_host
PORT = config.settings.indexing_server_port
BUFSIZE = 1024

VM_SERVER_EXE = config.settings.VM_server_exe
VMHOST = config.settings.VM_server_host
VMPORT = config.settings.VM_server_port


class DebugFrame(LabelFrame):
    """GUI panel with advanced / debugging functions."""

    def __init__(self, parent):
        LabelFrame.__init__(self, parent, text='For debugging, be careful!')
        self.parent = parent

        self.init_vars()

        frame = Frame(self)

        Label(frame, text='Run custom python scripts').grid(row=1, column=0, sticky='W')

        self.e_script_file = Combobox(frame, width=50, textvariable=self.script_file, values=list(self.scripts.keys()))
        self.e_script_file.grid(row=2, column=0, columnspan=2, sticky='EW')
        self.scripts_combobox_update()

        self.BrowseButton = Button(frame, text='Browse..', command=self.browse)
        self.BrowseButton.grid(row=2, column=2, sticky='EW')

        self.RunButton = Button(frame, text='Run', command=self.run_script)
        self.RunButton.grid(row=2, column=3, sticky='EW')

        Separator(frame, orient=HORIZONTAL).grid(row=3, columnspan=8, sticky='ew', pady=10)

        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)

        Label(frame, text='Indexing server options').grid(row=0, column=0, sticky='W')

        Label(frame, text='Indexing server: DIALS').grid(row=2, column=0, sticky='W')

        self.BrowseButton = Button(frame, text='Start', command=self.start_server)
        self.BrowseButton.grid(row=2, column=2, sticky='EW')

        self.RunButton = Button(frame, text='Register', command=self.register_server)
        self.RunButton.grid(row=2, column=3, sticky='EW')

        self.RunButton = Button(frame, text='Kill', command=self.kill_server)
        self.RunButton.grid(row=2, column=4, sticky='EW')

        Label(frame, text='Indexing server: XDS (Ubuntu in VirtualBox)').grid(row=3, column=0, sticky='W')

        self.BrowseButton = Button(frame, text='Start', command=self.start_server_xdsVM)
        self.BrowseButton.grid(row=3, column=2, sticky='EW')

        self.RunButton = Button(frame, text='Register', command=self.register_server_xdsVM)
        self.RunButton.grid(row=3, column=3, sticky='EW')

        self.RunButton = Button(frame, text='Kill', command=self.kill_server_xdsVM)
        self.RunButton.grid(row=3, column=4, sticky='EW')

        self.use_shelxt_check = Checkbutton(frame, text='Use SHELXT for online structure solution', variable=self.var_use_shelxt, command=self.toggle_use_shelxt)
        self.use_shelxt_check.grid(row=4, column=0, sticky='W')

        Label(frame, text='Space group: ').grid(row=4, column=2, sticky='EW')
        self.e_sg = Entry(frame, textvariable=self.var_e_sg, width=15, state=NORMAL)
        self.e_sg.grid(row=4, column=3, sticky='EW', columnspan=2)

        Label(frame, text='Unit cell: ').grid(row=5, column=2, sticky='EW')
        self.e_uc = Entry(frame, textvariable=self.var_e_uc, width=15, state=NORMAL)
        self.e_uc.grid(row=5, column=3, sticky='EW', columnspan=2)

        Label(frame, text='Composition: ').grid(row=6, column=2, sticky='EW')
        self.e_compo = Entry(frame, textvariable=self.var_e_compo, width=15, state=NORMAL)
        self.e_compo.grid(row=6, column=3, sticky='EW', columnspan=2)

        self.use_sendto_AS_check = Checkbutton(frame, text='Send SMV path to autosolution server: ', variable=self.var_send_data_to_AS, command=self.toggle_use_AS)
        self.use_sendto_AS_check.grid(row=7, column=0, sticky='W')

        Label(frame, text='SMV files path: ').grid(row=8, column=0, sticky='EW')
        self.e_smvpath = Entry(frame, textvariable=self.var_e_smvpath, width=50, state=DISABLED)
        self.e_smvpath.grid(row=8, column=0, sticky='EW', columnspan=4)

        self.SendButton = Button(frame, text='Send', command=self.send_path_to_autosolution)
        self.SendButton.grid(row=8, column=4, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.pack(side='top', fill='x', padx=10, pady=10)

        Separator(frame, orient=HORIZONTAL).grid(row=9, columnspan=8, sticky='ew', pady=10)

        frame = Frame(self)

        Label(frame, text='Collect flatfield').grid(row=1, column=0, sticky='W')

        Label(frame, text='Frames').grid(row=1, column=1, sticky='W', padx=5)

        self.e_ff_frames = Entry(frame, textvariable=self.var_ff_frames, width=10)
        self.e_ff_frames.grid(row=1, column=2, sticky='EW')

        self.ff_darkfield = Checkbutton(frame, text='Darkfield', variable=self.var_ff_darkfield)
        self.ff_darkfield.grid(row=1, column=3, sticky='EW', padx=5)

        self.RunFlatfield = Button(frame, text='Run', command=self.run_flatfield_collection)
        self.RunFlatfield.grid(row=1, column=4, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.pack(side='top', fill='x', padx=10, pady=10)

        frame = Frame(self)

        self.resetTriggers = Button(frame, text='Report status', command=self.report_status)
        self.resetTriggers.grid(row=0, column=0, sticky='EW')

        self.resetTriggers = Button(frame, text='Close down', command=self.close_down)
        self.resetTriggers.grid(row=0, column=1, sticky='EW')

        self.resetTriggers = Button(frame, text='Reset triggers', command=self.reset_triggers)
        self.resetTriggers.grid(row=1, column=0, sticky='EW')

        self.openIPython = Button(frame, text='Open IPython shell', command=self.open_ipython)
        self.openIPython.grid(row=1, column=1, sticky='EW')

        self.resetTriggers = Button(frame, text='Empty queue', command=self.empty_queue)
        self.resetTriggers.grid(row=2, column=0, sticky='EW')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        frame.pack(side='bottom', fill='x', padx=10, pady=10)

    def init_vars(self):
        self.script_file = StringVar()
        self.scripts = {}
        self.scripts_drc = scripts_drc  # pathlib.Path object

        self.var_ff_frames = IntVar(value=100)
        self.var_ff_darkfield = BooleanVar(value=False)
        self.var_use_shelxt = BooleanVar(value=True)
        self.var_send_data_to_AS = BooleanVar(value=False)
        self.var_e_compo = StringVar(value='Si1 O2')
        self.var_e_sg = StringVar(value='')
        self.var_e_uc = StringVar(value='')
        self.var_e_smvpath = StringVar(value='')

    def kill_server(self):
        self.q.put(('autoindex', {'task': 'kill_server'}))
        self.triggerEvent.set()

    def start_server(self):
        self.q.put(('autoindex', {'task': 'start_server'}))
        self.triggerEvent.set()

    def register_server(self):
        self.q.put(('autoindex', {'task': 'register_server'}))
        self.triggerEvent.set()

    def kill_server_xdsVM(self):
        self.q.put(('autoindex_xdsVM', {'task': 'kill_server_xdsVM'}))
        self.triggerEvent.set()

    def start_server_xdsVM(self):
        compos = self.var_e_compo.get()
        unitcell = self.var_e_uc.get()
        spgr = self.var_e_sg.get()
        use_shelxt = self.var_use_shelxt.get()

        print(f'Use ShelXT: {use_shelxt}; Space group: {spgr}')

        self.q.put(('autoindex_xdsVM', {'task': 'start_server_xdsVM',
                                        'compos': compos,
                                        'unitcell': unitcell,
                                        'spgr': spgr,
                                        'use_shelxt': use_shelxt}))
        self.triggerEvent.set()

    def register_server_xdsVM(self):
        self.q.put(('autoindex_xdsVM', {'task': 'register_server_xdsVM'}))
        self.triggerEvent.set()

    def send_path_to_autosolution(self):
        path = self.var_e_smvpath.get()

        self.q.put(('autosolution_path', {'path': path}))
        self.triggerEvent.set()

    def scripts_combobox_update(self, event=None):
        for fn in self.scripts_drc.rglob('*.py'):
            self.scripts[fn.name] = fn
        self.e_script_file['values'] = list(self.scripts.keys())

    def scripts_combobox_add(self, fn):
        self.scripts[fn.name] = fn
        self.e_script_file['values'] = list(self.scripts.keys())

    def set_trigger(self, trigger=None, q=None):
        self.triggerEvent = trigger
        self.q = q

    def reset_triggers(self):
        self.triggerEvent.clear()
        print('>> trigger event has been reset.')

    def empty_queue(self):
        print(f'There are {self.q.qsize()} items left in the queue.')
        while not self.q.empty():
            job, kwargs = self.q.get()
            print(f'Flushed job: {job}->{kwargs}')

    def open_ipython(self):
        self.q.put(('debug', {'task': 'open_ipython'}))
        self.triggerEvent.set()

    def report_status(self):
        self.q.put(('debug', {'task': 'report_status'}))
        self.triggerEvent.set()

    def close_down(self):
        script = self.scripts_drc / 'close_down.py'
        # print(script, script.exists())
        if not script.exists():
            return IOError(f'No such script: {script}')
        self.q.put(('debug', {'task': 'run_script', 'script': script}))
        self.triggerEvent.set()

    def browse(self):
        fn = tkinter.filedialog.askopenfilename(parent=self.parent, title='Select Python script')
        if not fn:
            return
        fn = Path(fn).absolute()
        self.scripts_combobox_add(fn)
        self.script_file.set(fn)
        return fn

    def run_script(self):
        script = self.script_file.get()
        if script in self.scripts:
            script = self.scripts[script]
        self.q.put(('debug', {'task': 'run_script', 'script': script}))
        self.triggerEvent.set()

    def run_flatfield_collection(self):
        self.q.put(('flatfield', {'task': 'collect', 'frames': self.var_ff_frames.get(), 'collect_darkfield': self.var_ff_darkfield.get()}))
        self.triggerEvent.set()

    def toggle_use_shelxt(self):
        enable = self.var_use_shelxt.get()
        if enable:
            self.e_compo.config(state=NORMAL)
            self.e_sg.config(state=NORMAL)
            self.e_uc.config(state=NORMAL)
        else:
            self.e_compo.config(state=DISABLED)
            self.e_sg.config(state=DISABLED)
            self.e_uc.config(state=DISABLED)

    def toggle_use_AS(self):
        enable = self.var_send_data_to_AS.get()
        if enable:
            self.e_smvpath.config(state=NORMAL)
        else:
            self.e_smvpath.config(state=DISABLED)


def debug(controller, **kwargs):
    task = kwargs.pop('task')
    if task == 'open_ipython':
        ctrl = controller.ctrl
        from IPython import embed
        embed(banner1='\nAssuming direct control.\n')
    elif task == 'report_status':
        print(controller.ctrl)
    elif task == 'run_script':
        ctrl = controller.ctrl
        script = kwargs.pop('script')
        ctrl.run_script(script)


def autoindex(controller, **kwargs):

    task = kwargs.get('task')
    if task == 'start_server':
        import subprocess as sp
        # cmd = "start /wait cmd /c instamatic.dialsserver"
        cmd = f'start {SERVER_EXE}'
        controller.indexing_server_process = sp.call(cmd, shell=True)
        print(f'Indexing server `{SERVER_EXE}` started on {HOST}:{PORT}')
        controller.use_indexing_server = True
        print('Indexing server registered')
        return

    elif task == 'register_server':
        controller.use_indexing_server = True
        print('Indexing server registered')
        return

    elif task == 'run':
        payload = bytes(kwargs.get('path'))

    elif task == 'kill_server':
        payload = b'kill'

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print('Sending job to server...', end=' ')
        s.connect((HOST, PORT))
        s.send(payload)
        data = s.recv(BUFSIZE).decode()
        print(data)
        data = s.recv(BUFSIZE).decode()
        print(data)

    if task == 'kill':
        del controller.indexing_server_process


def autoindex_xdsVM(controller, **kwargs):

    task = kwargs.get('task')
    if task == 'start_server_xdsVM':
        import subprocess as sp

        compos = kwargs.get('compos')
        unitcell = kwargs.get('unitcell')
        spgr = kwargs.get('spgr')
        use_shelxt = kwargs.get('use_shelxt')

        cmd = f'start {VM_SERVER_EXE}'
        if use_shelxt:
            if compos:
                cmd += ' -shelxt -m '
                cmd += compos

                if unitcell:
                    cmd += ' -c '
                    cmd += unitcell

                if spgr:
                    cmd += ' -s '
                    cmd += spgr
            else:
                print('No composition information provided. SHELXT cannot run.')

        controller.indexing_server_process = sp.call(cmd, shell=True)
        print(f'Indexing server `{VM_SERVER_EXE}` starting on {VMHOST}:{VMPORT}')
        #controller.use_indexing_server_xds = True
        print('VM XDS Indexing server registered. Please wait for around 2 min before XDS server is ready.')
        print('Please refer to the server console for the current status of the server.')
        return

    elif task == 'register_server_xdsVM':
        #controller.use_indexing_server_xds = True
        print('VM XDS Indexing server registered')
        return

    elif task == 'run':
        payload = bytes(kwargs.get('path'))

    elif task == 'kill_server_xdsVM':
        payload = b'kill'

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print('Sending job to server...', end=' ')
        s.connect((VMHOST, VMPORT))
        s.send(payload)
        data = s.recv(BUFSIZE).decode()
        print(data)

    if task == 'kill':
        del controller.indexing_server_process


def autosolution_path(controller, **kwargs):
    import json

    path = kwargs.get('path')

    params = {'path': path}
    payload = json.dumps(params).encode('utf8')

    # Send to server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print(f'Sending string `{path}` to auto structure solution server...')
        s.connect((VMHOST, VMPORT))
        s.send(payload)
        data = s.recv(BUFSIZE).decode()
        print(data)

    print('Sent!')


module = BaseModule(name='debug', display_name='advanced', tk_frame=DebugFrame, location='bottom')
commands = {
    'debug': debug,
    'autoindex': autoindex,
    'autoindex_xdsVM': autoindex_xdsVM,
    'autosolution_path': autosolution_path,
}

if __name__ == '__main__':
    root = Tk()
    DebugFrame(root).pack(side='top', fill='both', expand=True)
    root.mainloop()
