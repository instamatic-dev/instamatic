import fabio
import os
import datetime
import logging
from Tkinter import *
import numpy as np
import glob
import time
from instamatic.formats import write_tiff
import ImgConversion

class cRED_experiment(object):
    def __init__(self, ctrl,expt,camtyp,t,path=None,log=None):
        super(cRED_experiment,self).__init__()
        self.ctrl=ctrl
        self.path=path
        self.expt=expt
        self.logger=log
        self.camtyp=camtyp
        self.t=t
        
    def report_status(self):
        self.image_binsize=self.ctrl.cam.default_binsize
        self.magnification=self.ctrl.magnification.get()
        self.image_spotsize=self.ctrl.spotsize
        
        self.diff_binsize=self.image_binsize
        self.diff_exposure=self.expt
        self.diff_brightness=self.ctrl.brightness
        self.diff_spotsize=self.image_spotsize
        print ("Output directory:\n{}".format(self.path))
        print "Imaging     : binsize = {}".format(self.image_binsize)
        print "              exposure = {}".format(self.expt)
        print "              magnification = {}".format(self.magnification)
        print "              spotsize = {}".format(self.image_spotsize)
        print "Diffraction : binsize = {}".format(self.diff_binsize)
        print "              exposure = {}".format(self.diff_exposure)
        print "              brightness = {}".format(self.diff_brightness)
        print "              spotsize = {}".format(self.diff_spotsize)        
        
    def start_collection(self):
        
        curdir = os.path.dirname(os.path.realpath(__file__))
        
        flatfield=fabio.open(os.path.join(curdir,'flatfield_tpx_2017-06-21.tiff'))
        data=flatfield.data
        newdata=np.zeros([512,512],dtype=np.ushort)
        newdata[0:256,0:256]=data[0:256,0:256]
        newdata[256:,0:256]=data[260:,0:256]
        newdata[0:256,256:]=data[0:256,260:]
        newdata[256:,256:]=data[260:,260:]
        flatfield=newdata
        
        pxd={'15': 0.00838, '20': 0.00623, '25': 0.00499, '30': 0.00412, '40': 0.00296, '50': 0.00238, '60': 0.00198, '80': 0.00148}
        a0=self.ctrl.stageposition.a
        a=a0
        ind_set=[]
        ind=10001
        ind_set.append(ind)
        
        self.pathtiff=os.path.join(self.path,"tiff")
        self.pathsmv=os.path.join(self.path,"SMV")
        self.pathred=os.path.join(self.path,"RED")
        
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        if not os.path.exists(self.pathtiff):
            os.makedirs(self.pathtiff)
        if not os.path.exists(self.pathsmv):
            os.makedirs(self.pathsmv)
        if not os.path.exists(self.pathred):
            os.makedirs(self.pathred)
        
        self.logger.info("Data recording started at: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.logger.info("Data saving path: {}".format(self.path))
        self.logger.info("Data collection exposure time: {} s".format(self.expt))
        camlen = int(self.ctrl.magnification.get())/10
        self.logger.info("Data collection camera length: {} cm".format(camlen))
        self.logger.info("Data collection spot size: {}".format(self.ctrl.spotsize))
        
        if self.camtyp == 1:
            while abs(a-a0)<0.5:
                a=self.ctrl.stageposition.a
                if abs(a-a0)>0.5:
                    break
            print "Data Recording started."
            self.startangle=a
            
            self.ctrl.cam.block()
            
            while not self.t.is_set():
                self.ctrl.getImage(self.expt,1,out=os.path.join(self.pathtiff,"{}.tiff".format(ind)),header_keys=None)
                ind=ind+1
                #self.root.update()
            self.ctrl.cam.unblock()
            self.endangle=self.ctrl.stageposition.a
            ind_set.append(ind)
            
        else:
            self.startangle=a
            camlen=30
            flatfield=np.random.rand(1024,1024)
            self.ctrl.cam.block()
            while not self.t.is_set():
                self.ctrl.getImage(self.expt,1,out=os.path.join(self.pathtiff,"{}.tiff".format(ind)),header_keys=None)
                print (self.ctrl.stageposition.a)
                print ("Generating random images...")
                time.sleep(self.expt)
                ind=ind+1
                #self.root.update()
            self.ctrl.cam.unblock()
            self.endangle=self.startangle+10
            ind_set.append(ind)
        
        self.ind=ind
        
        self.logger.info("Data collected from {} degree to {} degree.".format(self.startangle,self.endangle))
        
        listing=glob.glob(os.path.join(self.pathtiff,"*.tiff"))
        numfr=len(listing)
        osangle=(self.endangle-self.startangle)/numfr
        if osangle>0:
            self.logger.info("Oscillation angle: {}".format(osangle))
        else:
            self.logger.info("Oscillation angle: {}".format(-osangle))
        
        self.logger.info("Pixel size and actual camera length updated in SMV file headers for DIALS processing.")
        
        buf=ImgConversion.ImgConversion(expdir=self.path)
        pb=buf.TiffToIMG(self.pathtiff,self.pathsmv,str(camlen),self.startangle,osangle)
        pxs=pxd[str(camlen)]
        buf.ED3DCreator(self.pathtiff,self.pathred,pxs,self.startangle,self.endangle)
        buf.MRCCreator(self.pathtiff,self.pathred,header=buf.mrc_header,pb=pb)
        
        RA=-38.5
        buf.XDSINPCreator(self.pathsmv,self.ind,self.startangle,20,0.8,pb,str(camlen),osangle,RA)
        self.logger.info("XDS INP file created as usual.")

        print "Data Collection and Conversion Done."