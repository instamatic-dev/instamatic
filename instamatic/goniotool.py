from pywinauto import Application

GONIOTOOL_EXE = "C:\JEOL\TOOL\GonioTool.exe"
DEFAULT_SPEED = 12


class GonioToolWrapper(object):
    """docstring for GonioToolWrapper"""
    def __init__(self, arg):
        super(GonioToolWrapper, self).__init__()
        
        self.app = Application().start(GONIOTOOL_EXE)
        input("Press <ENTER> to continue...")  # delay for password, TODO: automate
        self.startup()

    def startup(self):
        self.f1rate = self._app.TMainForm["f1/rate"] 
        
        self.f1 = app.TMainForm.f1
        self.rb_cmd = f1.CMDRadioButton
        self.rb_tkb = f1.TKBRadioButton
        self.set_button = f1.SetButton
        self.get_button = f1.GetButton

        self.click_get_button()
        self.click_cmd()
        
        self.edit = app.TMainForm.f1.Edit7

    def closedown(self)
        self.set_rate(DEFAULT_SPEED)
        self.click_tkb()
        # TODO: close the program

    def list_f1rate(self):
        self.f1rate.print_control_identifiers()

    def list_f1(self):
        self.f1.print_control_identifiers()

    def click_get_button(self):
        self.getbutton.click()

    def click_set_button(self):
        self.setbutton.click()

    def click_tkb(self):
       self.rb_tkb.click()

    def click_cmd(self):
       self.rb_cmd.click()

    def set_rate(speed: int):
        assert isinstance(speed, int)
        assert 0 < speed <= 12

        s = self.edit.select()
        s.set_text(speed)
        self.click_set_button()


if __name__ == '__main__':
    gt = GonioTool()

    from IPython import embed
    embed()