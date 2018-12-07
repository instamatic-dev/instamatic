### insteaDMatic v0.1.0: a DM-Script to collect continuous rotation electron diffraction data

Author: Stef Smeets (2018)  
URL: www.github.com/stefsmeets/instamatic

Thanks to Bin Wang and Maria Roslova for helping with the testing, and Thomas Thersleff for discussions about DM and the idea of using the image clone function.
The script is loosely based on an example by Dave Mitchell (http://www.dmscripting.com/example_running_a_thread_from_within_a_dialog.html)

The script has been tested on a FEI themisZ with OneView camera and a JEOL 2100 with Orius Camera.

This script helps with automatic data collection of continuous rotation electron diffraction (CRED) data using DigitalMicrograph.

It uses the 'live view' of the camera as a source of data. Every time the frame is updated, DM fires off an event. 
This scripts waits for this event and then clones the image. These data are equivalent to what can be obtained using the 'Record' function.
Therefore, the settings of the image collection (exposure, resolution, binsize, etc.) are controlled through the right-side panel in DM, outside the script.

The script allocates the memory for storing the images beforehand (defined by `buffer size`), and therefore sets the maximum number of frames that can be collected.
Data collection is interrupted when the buffer is full.

When `<Start>` is pressed, the script will wait for rotation to start. When rotation passes the `angle activation threshold` (0.2 degrees), data collection is initiated.
The rotation is controlled through an external script or by using the microscope tilt control.

Press `<Stop>` to interrupt data collection. It is also possible to interrupt the data collection automatically if the sample stops moving.

The work directory and experiment name define where the data are saved. The experiment number is updated automatically so that data are never overwritten.

Use instamatic/scripts/process_dm.py to convert the data to formats compatible with XDS/PETS/REDp/DIALS 
(www.github.com/stefsmeets/instamatic)

### Usage instructions:
1. Insert the camera in view mode (for Oneview, use 'In-situ Acquisition')
   - Set the exposure (i.e. 0.3 s) and press 'View'
   - For Oneview, set the diffraction mode for the acquisition (Click 'D')
   - Set the binsize and other processing parameters
2. Set the buffer size to the maximum number of frames to be collected (i.e. 1000)
3. Press `<Start>` to prime the script for data collection
   - The script will wait until rotation is initiated, and then start acquiring data
4. Press `<Stop>` to stop the data acquisition
   - Data acquisition will end  if the frame buffer is full
   - Data acquisition will end if the stage stops rotating (if set)
5. Data are stored to the `<work_directory>/<sample_directory>_#`
   - Experiment meta data are stored in the `cRED_log.txt` file
   - Images are stored in `.tiff` format in the `tiff` subdirectory
   - use `python instamatic/scripts/process_fei.py cRED_log.txt` to for data conversion
