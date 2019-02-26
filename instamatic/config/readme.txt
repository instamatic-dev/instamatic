global.yaml
    microscope: name of the microscope calibration file (in ./microscope/) use
    camera: name of the camera file (in ./camera/) to use
    calibration: name of the calibration file (in ./calibration) to use
    
    use_tem_server: use the tem server with the given host/port below. If instamatic cannot find the tem server, it will start a new temserver in a subprocess. The tem server can be started using 'instamatic.temserver.exe'. This helps to isolate the microscope communication. Instamatic will connect to the server via sockets. The main advantage is that a socket client can be run in a thread, whereas a COM connection makes problems if it is not in main thread. 
    tem_server_host: Set this to 'localhost' if the TEM server is run locally. To make a remote connection, use '0.0.0.0' on the server, and the ip address on the client.
    tem_server_port: the server port, default: 8088
    
    indexing_server_exe: After data are collected, the path where the data are saved can be sent to this program via a socket connection for automated data processing. Available are the dials indexing server (instamatic.dialsserver.exe) and the xds indexing server (instamatic.xdsserver.exe)
    indexing_server_host: IP to use for the indexing server, same as above.
    indexing_server_port: Port to use for the indexing server, default: 8089
    dials_script: The script that is run when the dials indexing server is used.
    
    cred_relax_beam_before_experiment: Relax the beam before a CRED experiment (for testing only), default: false
    cred_track_stage_positions: Track the stage position during a CRED experiment (for testing only), default: false

calibration/calibration_name.yaml
    name: Name of the camera interface to use
    diffraction_pixeldimensions: 
        Give here a list of camera lengths (as reported by the TEM) and the corresponding pixel dimensions in reciprocal angstrom, separated by a ':', for example:
          250: 0.0040
          300: 0.0050
    lowmag_pixeldimensions:
        Give here the magnification and pixel dimensions (x and y) for the lowmag mode in micrometer, for example:
          1000: [0.044779, 0.044779]
          1200: [0.037316, 0.037316]
    mag1_camera_dimensions:
        Give here the magnification and pixel dimensions of the entire camera in micrometer, for exmaple:
          8000: [9.86148864, 9.86148864]
         10000: [7.99162368, 7.99162368]

camera/camera_name.yaml:
    calib_beamshift: Set up the grid and stepsize for the calibration of the beam shift in SerialED, for example:
        {gridsize: 5, stepsize: 500}
    calib_directbeam: Set up the grid and stepsize for the calibration of the direct beam in diffraction mode, for example:
      BeamShift: {gridsize: 5, stepsize: 300}
      DiffShift: {gridsize: 5, stepsize: 300}
    correction_ratio: Set the correction ratio for the cross pixels in the Timepix detector, default: 3
    default_binsize: Set the default binsize, default: 1
    default_exposure: Set the default exposure in seconds, i.e. 0.02
    dimensions: Give the dimensions of the camera at binning 1, for example: [516, 516]
    dynamic_range: Give the maximum counts of the camera, for example: 11800
    name: Give the name of the camera to connect to, for example: timepix
    physical_pixelsize: The physical size of a pixel in micrometer, for example: 0.055
    possible_binsizes: Give here a list of possible binnings, for example: [1] or [1, 2, 4]
    camera_rotation_vs_stage_xy: In radians, give here the rotation of the position of the rotation axis with respect to the horizontal. Corresponds to the rotation axis in RED and PETS, for example: -2.24
    stretch_amplitude: Use instamatic.stretch_correction to characterize the lens distortion. The numbers here are used to calculate the XCORR/YCORR maps. The amplitude is the percentage difference between the maximum and minimum eigenvectors of the ellipsoid, i.e. if the amplitude is 2.43, eig(max)/eig(min) = 1.0243
    stretch_azimuth: The azimuth is gives the direction of the maximum eigenvector with respect to the horizontal X-axis (pointing right) in degrees, for example: 83.37

microscope/microscope_name.yaml
This file holds all the specifications of the microscope as necessary. It is important to set up the camera lengths, magnifications, and magnification_modes

    name: name of the microscope interface to use
    wavelength: The wavelength of the microscope in ansgtroms, i.e. for 200kv: 0.025080
    cameras: The cameras that area accessible on this microscope (obsolete)
    specifications:
        Give here the accessible camera lengths and magnifications of the microscope
      CAMERALENGTHS: [150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200,
        1500, 2000, 2500, 3000, 3500, 4000, 4500]
      MAGNIFICATIONS: [50, 60, 80, 100, 150, 200, 250, 300, 400, 500, 600,
        800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000,
        15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000,
        200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000,
        2000000]
    
        Magnification modes tells instamatic when to switch between mag1 and lowmag modes, i.e. where lowmag    starts and where mag1 starts
      MAGNIFICATION_MODES: {
        lowmag: 50, 
        mag1: 2500 }
    
        Here the rotation speeds can be calibrated. This is only used to correct the rotation speeds collected  during CRED if necessary. 
      rotation_speeds: {
        fine: [ 0.114, 0.45, 1.126 ], 
        coarse: [ 0.45, 1.8, 4.5 ] }    