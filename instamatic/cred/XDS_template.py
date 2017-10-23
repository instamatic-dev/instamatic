XDS_template = """
! XDS.INP file for Rotation Electron Diffraction - Hongyi and Hugo, version Feb.2017
!
! For definitions of input parameters, see: 
! http://xds.mpimf-heidelberg.mpg.de/html_doc/xds_parameters.html
!
! NOTE: Please convert the tiff files into SMV fomat using RED before processing
! Images are expected to be already corrected for spatial distortions.

! TimePix Detector Segment (Remove Cross)

SEGMENT= 2 255 2 255   ! Top left segment
DIRECTION_OF_SEGMENT_X-AXIS= 1.0 0.0 0.0
DIRECTION_OF_SEGMENT_Y-AXIS= 0.0 1.0 0.0
SEGMENT_ORGX=-2.18182
SEGMENT_ORGY=-2.18182
SEGMENT_DISTANCE=0.0

SEGMENT= 258 511 2 255  ! Top right segment
DIRECTION_OF_SEGMENT_X-AXIS= 1.0 0.0 0.0
DIRECTION_OF_SEGMENT_Y-AXIS= 0.0 1.0 0.0
SEGMENT_ORGX=-6.54545
SEGMENT_ORGY=-2.18182
SEGMENT_DISTANCE=0.0

SEGMENT= 2 255 258 511  ! Bottom left segment
DIRECTION_OF_SEGMENT_X-AXIS= 1.0 0.0 0.0
DIRECTION_OF_SEGMENT_Y-AXIS= 0.0 1.0 0.0
SEGMENT_ORGX=-2.18182
SEGMENT_ORGY=-6.54545
SEGMENT_DISTANCE=0.0

SEGMENT= 258 511 258 511  ! Bottom right segment
DIRECTION_OF_SEGMENT_X-AXIS= 1.0 0.0 0.0
DIRECTION_OF_SEGMENT_Y-AXIS= 0.0 1.0 0.0
SEGMENT_ORGX=-6.54545
SEGMENT_ORGY=-6.54545
SEGMENT_DISTANCE=0.0

! ********** Job control **********

!JOB= XYCORR INIT COLSPOT IDXREF
!JOB= DEFPIX XPLAN INTEGRATE CORRECT
!JOB= CORRECT

MAXIMUM_NUMBER_OF_JOBS=4
MAXIMUM_NUMBER_OF_PROCESSORS=4

! ********** Data images **********

NAME_TEMPLATE_OF_DATA_FRAMES= 0????.img   SMV
DATA_RANGE=           {data_begin:d} {data_end:d}
{exclude:s}
SPOT_RANGE=           {data_begin:d} {data_end:d}
BACKGROUND_RANGE=     {data_begin:d} {data_end:d}

! ********** Crystal **********

!SPACE_GROUP_NUMBER= 0
!UNIT_CELL_CONSTANTS=  10 20 30 90 90 90

!REIDX=  !Optional reindexing transformation to apply on reflection indices
FRIEDEL'S_LAW=TRUE

!phi(i) = STARTING_ANGLE + OSCILLATION_RANGE * (i - STARTING_FRAME)
STARTING_ANGLE= {starting_angle:0.2f}
STARTING_FRAME= 1

!MAX_CELL_AXIS_ERROR=         !0.03 is default
!MAX_CELL_ANGLE_ERROR=        !2.0  is default

!TEST_RESOLUTION_RANGE=    !for calculation of Rmeas when analysing the intensity data for space group symmetry in the CORRECT step.
!MIN_RFL_Rmeas=    !50 is default - used in the CORRECT step for identification of possible space groups.
!MAX_FAC_Rmeas=    !2.0 is default - used in the CORRECT step for identification of possible space groups.


! ************************************************
! ********** Detector & Beam parameters **********

! ********** Detector hardware **********

NX=512  NY=512  QX=0.0500  QY=0.0500  !Number and Size (mm) of pixels
OVERLOAD= 130000              !default value dependent on the detector used
TRUSTED_REGION= 0.0   1.4142  !default \"0.0 1.05\". Corners for square detector max \"0.0 1.4142\"
SENSOR_THICKNESS=0.30

! ********** Trusted detector region **********

! ??? VALUE_RANGE_FOR_TRUSTED_DETECTOR_PIXELS=    ! 6000 30000 is default, for excluding shaded parts of the detector.
!MINIMUM_ZETA=   !0.05 is default
 
INCLUDE_RESOLUTION_RANGE= {dmax:.2f} {dmin:.2f}

!Ice Ring exclusion, important for data collected using cryo holders
!EXCLUDE_RESOLUTION_RANGE= 3.93 3.87   !ice-ring at 3.897 Angstrom
!EXCLUDE_RESOLUTION_RANGE= 3.70 3.64   !ice-ring at 3.669 Angstrom
!EXCLUDE_RESOLUTION_RANGE= 3.47 3.41   !ice-ring at 3.441 Angstrom (Main)
!EXCLUDE_RESOLUTION_RANGE= 2.70 2.64   !ice-ring at 2.671 Angstrom
!EXCLUDE_RESOLUTION_RANGE= 2.28 2.22   !ice-ring at 2.249 Angstrom (Main)
!EXCLUDE_RESOLUTION_RANGE= 2.102 2.042 !ice-ring at 2.072 Angstrom - strong
!EXCLUDE_RESOLUTION_RANGE= 1.978 1.918 !ice-ring at 1.948 Angstrom - weak
!EXCLUDE_RESOLUTION_RANGE= 1.948 1.888 !ice-ring at 1.918 Angstrom - strong
!EXCLUDE_RESOLUTION_RANGE= 1.913 1.853 !ice-ring at 1.883 Angstrom - weak
!EXCLUDE_RESOLUTION_RANGE= 1.751 1.691 !ice-ring at 1.721 Angstrom - weak


! ********** Detector geometry & Rotation axis **********

DIRECTION_OF_DETECTOR_X-AXIS= 1 0 0
DIRECTION_OF_DETECTOR_Y-AXIS= 0 1 0

ORGX= {origin_x:.2f}    ORGY= {origin_y:.2f}       !Detector origin (pixels). Often close to the image center, i.e. ORGX=NX/2; ORGY=NY/2
DETECTOR_DISTANCE= {sign}{detdist:.2f}   ! can be negative. Positive because the detector normal points away from the crystal.

OSCILLATION_RANGE= {osangle:.2f}
!OSCILLATION_RANGE {calib_osangle:.2f} ! Calibrated value if above one is too far off

ROTATION_AXIS= {rot_x:.3f} {rot_y:.3f} {rot_z:.3f}    !cos(139) cos(49)  !in XDS.INP emailed: 0.078605 0.996888 -0.005940

! ********** Incident beam **********

X-RAY_WAVELENGTH= {wavelength:.4f}      !used by IDXREF
INCIDENT_BEAM_DIRECTION= 0 0 39.84  !used by IDXREF +CORRECT(?) ???? (REC. ANGSTROM)  !The vector points from the source towards the crystal

! ********** Background and peak pixels **********

!NBX=     NBY=                         !3 is default
BACKGROUND_PIXEL= 20                    !6.0 is default
STRONG_PIXEL= 2.5                      !3.0 is default
!MAXIMUM_NUMBER_OF_STRONG_PIXELS=      !1500000 is default
!MINIMUM_NUMBER_OF_PIXELS_IN_A_SPOT=   !6 is default         ?????
!SPOT_MAXIMUM-CENTROID=                !2.0 is default
SIGNAL_PIXEL= 6                        !3.0 is default

! ********************************
! ********** Refinement **********

 REFINE(IDXREF)=    BEAM AXIS       ORIENTATION CELL SEGMENT !POSITION 
 REFINE(INTEGRATE)= !POSITION BEAM AXIS       !ORIENTATION CELL
 REFINE(CORRECT)=   BEAM AXIS ORIENTATION CELL        !SEGMENT !POSITION 

! *********************************************
! ********** Processing Optimization **********

! ********** Indexing **********

 MINIMUM_FRACTION_OF_INDEXED_SPOTS= 0.25    !0.50 is default.
"""
