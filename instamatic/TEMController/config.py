specifications = {
    "feg": {
        "MAGNIFICATIONS": (250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000, 200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000),
        "MAGNIFICATION_MODES": {"mag1": 2000, "lowmag":250},
        "CAMERALENGTHS": (150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 3500, 4000, 4500) # mm
    },
    "lab6":{
        "MAGNIFICATIONS": (50, 60, 80, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 80000, 100000, 120000, 150000, 200000, 250000, 300000, 400000, 500000, 600000, 800000, 1000000, 1200000, 1500000, 2000000),
        "MAGNIFICATION_MODES": {"mag1": 2500, "lowmag":50},
        "CAMERALENGTHS": (150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 2500, 3000, 3500, 4000, 4500) # mm
    }
}

# lowmag
# pixel dimensions from calibration in Digital Micrograph (ORIUS LaB6)
# x,y dimensions of 1 pixel in micrometer
lowmag_pixeldimensions = {
50:      (0.895597,  0.895597),
80:      (0.559748,  0.559748),
100:     (0.447799,  0.447799),
150:     (0.298532,  0.298532),
200:     (0.223899,  0.223899),
250:     (0.179119,  0.179119),
300:     (0.149266,  0.149266),
400:     (0.111949,  0.111949),
500:     (0.089559,  0.089559),
600:     (0.074633,  0.074633),
800:     (0.055974,  0.055974),
1000:    (0.044779,  0.044779),
1200:    (0.037316,  0.037316),
1500:    (0.029853,  0.029853),
2000:    (0.020800,  0.020800),
2500:    (0.016640,  0.016640),
3000:    (0.013866,  0.013866),
5000:    (0.008320,  0.008320),
6000:    (0.006933,  0.006933),
8000:    (0.005200,  0.005200),
10000:   (0.004160,  0.004160),
12000:   (0.003466,  0.003466),
15000:   (0.002773,  0.002773)
}

# mag1
# pixel dimensions from calibration in Digital Micrograph (ORIUS LaB6)
# x,y dimensions of 1 pixel in micrometer
mag1_dimensions = {
2500:    (0.01629260*2048, 0.01629260*2048),
3000:    (0.01339090*2048, 0.01339090*2048),
4000:    (0.00987389*2048, 0.00987389*2048),
5000:    (0.00782001*2048, 0.00782001*2048),
6000:    (0.00647346*2048, 0.00647346*2048),
8000:    (0.00481518*2048, 0.00481518*2048),
10000:   (0.00390216*2048, 0.00390216*2048),
12000:   (0.00328019*2048, 0.00328019*2048),
15000:   (0.00264726*2048, 0.00264726*2048),
20000:   (0.00200309*2048, 0.00200309*2048),
25000:   (0.00161106*2048, 0.00161106*2048),
30000:   (0.00136212*2048, 0.00136212*2048),
40000:   (0.00102159*2048, 0.00102159*2048),
50000:   (0.00081727*2048, 0.00081727*2048),
60000:   (0.00068106*2048, 0.00068106*2048),
80000:   (0.00051080*2048, 0.00051080*2048),
100000:  (0.00040864*2048, 0.00040864*2048),
120000:  (0.00034053*2048, 0.00034053*2048),
150000:  (0.00027242*2048, 0.00027242*2048),
200000:  (0.00020432*2048, 0.00020432*2048),
250000:  (0.00016345*2048, 0.00016345*2048),
300000:  (0.00013621*2048, 0.00013621*2048),
400000:  (0.00010216*2048, 0.00010216*2048),
500000:  (0.00008173*2048, 0.00008173*2048),
600000:  (0.00006811*2048, 0.00006811*2048),
800000:  (0.00005109*2048, 0.00005109*2048),
1000000: (0.00004086*2048, 0.00004086*2048),
1500000: (0.00002724*2048, 0.00002724*2048),
2000000: (0.00002043*2048, 0.00002043*2048)
}
# rough factor to convert values above to rough timepix equivalent numbers
# 4.0 for the reduction in pixelsize, and 1.4 for the additional scaling of the pixels
# timepix_dimensions = orius_dimensions / timepix_conversion_factor
timepix_conversion_factor = 4.0*1.4

# Diffraction mode
# Pixel dimensions for different camera lengths with parallel beam
# Calibration by Wei Wan (RED) for Orius LaB6
# x,y dimensions for 1 pixel, 1/XX Angstrom^-1
diffraction_pixeldimensions = {
  150 : 0.02942304,     # extrapolated from 600
  200 : 0.02206728,     # extrapolated from 600
  250 : 0.017653824,    # extrapolated from 600
  300 : 0.01471152,     # extrapolated from 600
  400 : 0.01103364,     # extrapolated from 600
  500 : 0.008826912,    # extrapolated from 600
  600 : 0.00735576,
  800 : 0.00544891,
  1000: 0.004202,
  1200: 0.0036496,
  1500: 0.00285546,
  2000: 0.00213076,
  2500: 0.00169945,
  3000: 0.00141621,
  3500: 0.0012139,
  4000: 0.00106216  
}

# calibration values for the scaling of the diffraction pattern when convergent beam is used
# To calibrate: Change brightness, adjust diffraction focus, take diffraction pattern
# use logpolar cross correlation to find scaling between parameters
# scaling = a * (difffocus - c) + b
diffraction_pixelsize_fit_parameters = [ -3.72964471e-05,  -1.00023069e+00,   7.36028832e+04]


# output from instamatic.calibrate_stage_mag1
# this is the rotation angle of the camera with regards to the stage xy directions
# it is related to the direction of the ROTATION AXIS in RED // chi in Snapkit
camera_rotation_vs_stage_xy = -0.71 # radians
