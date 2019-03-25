/*
### insteaDMatic v0.2.0: a DM-Script to collect continuous rotation electron diffraction data

Author: Stef Smeets (2018)  
URL: www.github.com/stefsmeets/instamatic

Thanks to Bin Wang and Maria Roslova for helping with the testing, and Thomas Thersleff for discussions about DM and the idea of using the image clone function.
The script is loosely based on an example by Dave Mitchell (http://www.dmscripting.com/example_running_a_thread_from_within_a_dialog.html)

The script has been tested on a FEI themisZ with OneView camera and a JEOL 2100 with Orius Camera.

This script helps with automatic data collection of continuous rotation electron diffraction (CRED) data using DigitalMicrograph.

#### How it works:

It uses the 'live view' of the camera as a source of data. Every time the frame is updated, DM fires off an event. 
This scripts waits for this event and then clones the image. These data are equivalent to what can be obtained using the 'Record' function.
Therefore, the settings of the image collection (exposure, resolution, binsize, etc.) are controlled through the right-side panel in DM, outside the script.

The script allocates the memory for storing the images beforehand (defined by `buffer size`), and therefore sets the maximum number of frames that can be collected.
Data collection is interrupted when the buffer is full.

When `<Start>` is pressed, the script will wait for rotation to start. When rotation passes the `angle activation threshold` (0.2 degrees), data collection is initiated.
The rotation is controlled through an external script or by using the microscope tilt control.

Press `<Stop>` to interrupt data collection. It is also possible to interrupt the data collection automatically if the sample stops moving. This is done by enabling the checkbox. The script will check the current angle every `0.3` seconds (tuneable), and will interrupt the data collection if the difference equals `0`. After data collection is finished, the beam can be blanked automatically by checking the box.

The work directory and experiment name define where the data are saved. The experiment number is updated automatically so that data are never overwritten.

Make sure to set up the rotation axis (defined as the angle between the horizontal and the position of the rotation axis). The variable is defined as `calibrated_rotation_angle` at the top of the script. It can be calculated using PETS.

Use `instamatic/scripts/process_dm.py` to convert the data to formats compatible with XDS/DIALS/REDp/PETS
(www.github.com/stefsmeets/instamatic)

#### Usage instructions:
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
   - use `python instamatic/scripts/process_dm.py cRED_log.txt` to for data conversion

#### FEI only:
If you are running on a FEI machine, you can control the rotation directly from the dmscript
To do so, instamatic should be installed on the microscope computer. The communication is done through a utility called netcat (available from (available from https://joncraton.org/blog/46/netcat-for-windows/))

- Set the `use_temserver` toggle to `true` in the script
- Make sure you have run `instamatic.temserver_fei` on the microscope computer
- Set the location of software NETCAT on the camera PC (the one running DM) in the variable `netcat_path`
- Give the correct IP address and port for TEM Python server in the variable `server_host_address`
- Fill in the desired rotation angle and speed

*/

string progname = "insteaDMatic v0.2.0"
number true = 1, false = 0

// Setup rotation axis (deg)
// for themisZ/Oneview: -171.0; for 2100LaB6/Orius: 53.0; otherwise: 0.0
number calibrated_rotation_axis = -171.0

// Setup experiment variables
number default_activation_threshold = 0.2   // change in angle to start rotation
number default_buffersize = 1000            // the maximum number of frames that will be collected, because memory must be reserved in advance

// FEI only, to control rotation directly from the dmscript
number default_target_angle = 40            // default target angle for rotation
number default_rotspeed = 0.05              // rotation speed index (must be in the range 0.0 - 1.0)

number write_tiff_files = true              // write data to tiff format
number show_buffer = false                  // show the buffer during data collection
number keep_buffer_open = false             // open buffer / keep buffer open after data collection
number default_auto_stop = true             // Check the angle and stop data collection automatically, 
                                            // only works with the higher exposure times (>0.3s tested)
number default_auto_blank = false           // Automatically blank the beam after data collection

number verbose = false                      // Increase the verbosity, print some testing variables

number use_temserver = false                // Option to use TEM Python server to allow operation only from the camera computer

// Default NETCAT.exe directory
string netcat_path = "C:\\Users\\VALUEDGATANCUSTOMER\\Documents\\Bin\\Nmap\\ncat.exe"      // location of the netcat program for communication with the microscope computer
string server_host_address = "localhost 9999"                                              // IP + port of the microscope computer running `instamatic.temserver_fei

// Initialize other parameters
number top, left, bottom, right    // image selection (top, left, bottom, right)
image stream, buffer
number loop = false
number EventTimeout = 1.0
number check_angle_interval = 0.3  // If auto stop is enabled, check the angle every # s


// Get date formatted as yyyy-mm-dd
string get_date_string()
{
    number year, month, day, hour, minute, second, nanosecond
    DeconstructUTCDate( GetCurrentTime(), year, month, day, hour, minute, second, nanosecond )
    string date = year + "-" + format(month, "%02d") + "-" + format(day, "%02d")
    return date
}


// Setup default directory
// Don't ask...
string user_drc = PathExtractParentDirectory(PathExtractParentDirectory(PathExtractParentDirectory(GetApplicationDirectory(4, 0), 0), 0), 0)
string documents_drc = PathConcatenate(user_drc, "documents")
// string default_work_drc = PathConcatenate(PathConcatenate(documents_drc, "instamatic"), "work")
string default_work_drc = "C:\\instamatic\\work_"+get_date_string()
string default_sample_name = "experiment"

// Signal that fires when the live view is updated
Object DataValueChangedEvent = NewSignal(0)


// Helper print function
void Print(string message)
{
    Result(message + "\n")
}


Class ImageListener
// Listen to updates of the live stream. If the live view updates, set the DataValueChangedSignal
{
    Void DataValueChanged(object self, number e_fl, image img)
    {   
        if ( verbose )
        {
            string event_desc
            ImageGetEventMap().DeconstructEventFlags( e_fl, event_desc )
            Print(GetTime(1)+": Image message : " + event_desc + " 0x" + Binary(e_fl))
        }
        DataValueChangedEvent.SetSignal()
    }
}

string messagemap = "data_value_changed:DataValueChanged"
object objListener = Alloc(ImageListener)


// Uncomment these lines to test the script on an offline version of DM
// This will mimic the microscope API
// Use `simulate_stream.s` to generate a dummy live view
/*
number EMGetStageAlpha()  Return (random() - 0.5) * 70
number EMGetCameraLength()  Return 300
number EMGetSpotSize()  Return 3
number CameraGetActiveCameraID()  Return 0
string CameraGetName(number camid)  Return "Camera"
string EMGetMicroscopeName()  Return "TEM"
void CameraGetSize(number camid, number cam_res_x, number cam_res_y){
cam_res_x = 1024; cam_res_y = 1024; }
void CameraGetPixelSize(number camid, number phys_pixelsize_x, number phys_pixelsize_y){
phys_pixelsize_x = 0.015; phys_pixelsize_y = 0.015 ; }
void EMWaitUntilReady()  sleep(5)
number EMGetHighTension()  Return 200000
number EMHasBeamBlanker()  Return true
void EMSetBeamBlanked( number toggle )  toggle
*/


// If the beam blank api is not available (i.e. on Orius), uncomment these lines:
/*
number EMHasBeamBlanker()  Return false
void EMSetBeamBlanked( number toggle )  toggle
*/

Class Dialog_UI : UIFrame
{
    void DialogEnabled(object self, number toggle)
    {
        self.SetElementIsEnabled("start_button", toggle)
        self.SetElementIsEnabled("work_drc_field", toggle)
        self.SetElementIsEnabled("sample_name_field", toggle)
        self.SetElementIsEnabled("buffersize_field", toggle)
        self.SetElementIsEnabled("angle_activation_field", toggle)
        self.SetElementIsEnabled("start_button", toggle)
        
        self.SetElementIsEnabled("browse_button", toggle)
        self.SetElementIsEnabled("open_button", toggle)
        
        self.SetElementIsEnabled("stop_button", !toggle)
    }

    void stop_pressed(object self)
    {
        loop = false
    }

    void start_pressed(object self)
    {
        self.DialogEnabled(false)
        self.startthread("ExperimentTask")
        loop = true
    }

    void end_collection(object self)
    {
        self.DialogEnabled(true)

        number auto_blank
        self.DLGGetValue("CheckAutoBlank", auto_blank)

        // Automatically blank beam after data collection
        if ( auto_blank && EMHasBeamBlanker() )
        {
            print("Blanking beam")
            EMSetBeamBlanked( true )
        }
    }

    void open_directory_pressed(object self)
    {   
        string work_drc
        self.DLGGetValue("work_drc_field", work_drc)
        string cmd = "explorer " + work_drc
        Print(cmd)
        LaunchExternalProcessAsync(cmd)
    }

    void browse_directory_pressed(object self)
    {
        string directory
        if ( !GetDirectoryDialog("Select directory", documents_drc, directory) ) 
            return
        Print("Directory:" + directory)
        self.DLGValue("work_drc_field", directory)
    }
    
    // Set simple status message
    void SetStatus( object self, string message )
    {
        self.LookUpElement("status").DLGTitle( message )
    }
       
    // Stop the data collection when the sample stage stopped moving
    // This works well if started in a separate thread, but it hangs the GUI
    void stop_when_ready(object self)
    {
        EMWaitUntilReady()
        loop = false
    }

    void ExperimentTask( object self )
    // Main data collection task
    {
        self.SetStatus( "Preparing" )
        // Setup directory structure
        number sample_number = 1
        string sample_name, work_drc
        self.DLGGetValue("work_drc_field", work_drc)
        self.DLGGetValue("sample_name_field", sample_name)
        string exp_drc = PathConcatenate(work_drc, sample_name + "_" + sample_number)

        while ( DoesDirectoryExist( exp_drc ) )
        {
            sample_number += 1
            exp_drc = PathConcatenate(work_drc, sample_name + "_" + sample_number)
        }
        CreateDirectory( exp_drc )
        string data_drc = PathConcatenate(exp_drc, "tiff")
        CreateDirectory( data_drc )

        Print("Experiment directory: " + exp_drc)

        number auto_stop
        self.DLGGetValue("CheckAutoStop", auto_stop)
        print("Automatically stop data collection: " + auto_stop)

        number nframes
        self.DLGGetValue("buffersize_field", nframes)
        Print("Buffersize: " + nframes)
       
        // get front image(), this is the live stream
        try  stream := GetFrontImage()        
        catch
        {
            Print("Please open and select the live stream of the camera to start.")
            self.end_collection()
            self.SetStatus("Please open live stream!")
            return
        }
        
        stream.GetSelection( top, left, bottom, right )

        // Attach data value changed event to live stream
        number ListenerID = stream.ImageAddEventListener( objListener, messagemap )

        // clone selected portion (if any), this takes care of image data type and image calibration
        buffer := stream[].ImageClone()
        buffer.SetName( "Electron Diffraction Data (" + stream.GetName() + ")" )

        // prepare data stack, thrown an error if there is not enough memory
        try  buffer.ImageResize( 3, (right-left), (bottom-top), nframes )           
        catch {
            OKDialog( "There is not enough memory, please reduce the buffer size or image size." )
            self.end_collection()
            self.SetStatus("Not enough memory!")
            return
        }

        number xsize, ysize, zsize
        Get3DSize(buffer, xsize, ysize, zsize)

        // Show the buffer; TODO: make it show the latest updated frame
        if ( show_buffer )  showimage(buffer)

        number angle_activation_threshold
        self.DLGGetValue("angle_activation_field", angle_activation_threshold)

        number start_angle, angle_delta = 0

        number angle0 = EMGetStageAlpha()
        Print("Angle0: " + angle0 + " (threshold: " + angle_activation_threshold + ")")
        
        //Launch external process using netcat to talk to the Python TEMserver
        if ( use_temserver )
        {
            number rotation_speed, target_angle

            self.DLGGetValue("rotation_speed_field", rotation_speed)
            Print("Desired rotation speed index: " + rotation_speed)

            self.DLGGetValue("rotation_field", target_angle)
            Print("Targeted angle: " + target_angle)
        
            string externalcommand
            externalcommand += "cmd /c echo "
            externalcommand += target_angle + "," + rotation_speed
            externalcommand += "  | " +  netcat_path + " " + server_host_address

            LaunchExternalProcess(externalcommand)
        }
        
        while ( angle_delta < angle_activation_threshold )
        {
            sleep(0.1)  // sleep to prevent request spam (can cause dm to crash)
            start_angle = EMGetStageAlpha()
            angle_delta = abs(start_angle - angle0)
            self.SetStatus("Waiting (delta = " + angle_delta + ")")
        }

        number i = 0
        number t0, t1, delta
        number average
        
        number prev_angle = start_angle
        number current_angle
        number sum_delta = 0
              
        // Synchronize t_start / start_angle with the first frame
        WaitOnSignal( DataValueChangedEvent, EventTimeout, NULL )
        DataValueChangedEvent.resetSignal()

        number t_start = GetHighResTickCount()

        start_angle = EMGetStageAlpha()
        Print("Starting angle: " + start_angle)

        while ( loop )
        {
            t0 = GetHighResTickCount()

            // wait for the live view data to be updated
            // this prevents copying the data as it is being written (which results in tearing)
            WaitOnSignal( DataValueChangedEvent, EventTimeout, NULL )  
            DataValueChangedEvent.resetSignal()
            
            // After live view has been updated, copy frame to buffer
            // buffer[ icol, irow, i ] = stream[top, left, bottom, right]  // slow
            slice2(buffer, 0, 0, i, 0, xsize, 1, 1, ysize, 1) = stream  // fast
            
            t1 = GetHighResTickCount()
            delta = CalcHighResSecondsBetween(t0, t1)
      
            // increment frame number
            i += 1

            if ( auto_stop )
            // Check if the stage is still rotating
            {
                if ( sum_delta > check_angle_interval )
                {
                    current_angle = EMGetStageAlpha()
                    // Print(prev_angle + " -> " + current_angle)
                    if ( current_angle - prev_angle == 0 )
                    {
                        loop = False
                        Print("Rotation has ended")
                    }
                    prev_angle = current_angle
                    sum_delta = 0
                }
                else
                {
                    sum_delta += delta
                }
            }

            // Stop collection when buffer is full
            if ( i == nframes )
            {
                Print("Buffer full")
                loop = false
            }

            self.DLGSetProgress( "progress_bar", i/nframes )
            self.SetStatus( "Collecting frame " + i )
        }

        number t_end = GetHighResTickCount()
        number total_time = CalcHighResSecondsBetween(t_start, t_end)
        
        // Remove the listener
        stream.ImageRemoveEventListener(ListenerID)
        
        self.end_collection()

        nframes = i
        
        if ( show_buffer || keep_buffer_open )  showimage(buffer)

        // get experiment parameters 
        number end_angle = EMGetStageAlpha()
        number camera_length = EMGetCameraLength()
        number spot_size = EMGetSpotSize()
        number osc_angle = abs(end_angle - start_angle) / nframes
        number acquisition_time = total_time / nframes
        number total_angle = abs(end_angle - start_angle)
        number rotation_axis = calibrated_rotation_axis
        string timestamp = FormatTimeString(GetCurrentTime(), 34)  // 34 -> magic number for dateformat
 
        // Get pixelsize (calibration)
        number xdim = 0, ydim = 1
        number image_pixelsize_x = ImageGetDimensionScale(stream, xdim)
        number image_pixelsize_y = ImageGetDimensionScale(stream, ydim)
        string units_x = ImageGetDimensionUnitString(stream, xdim)
        string units_y = ImageGetDimensionUnitString(stream, xdim)

        // get image resolution
        number image_res_x = right - left
        number image_res_y = bottom - top

        // get camera and tem name
        number camid = CameraGetActiveCameraID()
        string camera_name = CameraGetName(camid)
        string tem_name = EMGetMicroscopeName()
        
        // Get the acceleration voltage (kV)
        number high_tension = EMGetHighTension() / 1000

        // get camera resolution 
        number cam_res_x, cam_res_y 
        CameraGetSize(camid, cam_res_x, cam_res_y)

        // get binning
        number binsize_x = cam_res_x / image_res_x 
        number binsize_y = cam_res_y / image_res_y

        // get physical pixelsize
        number phys_pixelsize_x, phys_pixelsize_y
        CameraGetPixelSize(camid, phys_pixelsize_x, phys_pixelsize_y)
        phys_pixelsize_x *= binsize_x  // correct for binning
        phys_pixelsize_y *= binsize_y

        // Get reported exposure time
        TagGroup tg = stream.ImageGetTagGroup()
        number exposure
        tg.TagGroupGetTagAsNumber("Acquisition:Parameters:High Level:Exposure (s)", exposure)

        // calculate rotation speed
        number rot_speed = osc_angle / acquisition_time

        // Construct log message
        string log_message = ""
        log_message += "Program: " + progname + "\n"
        log_message += "Microscope: " + tem_name + "\n" 
        log_message += "Camera: " + camera_name + "\n" 
        log_message += "High tension (kV): " + high_tension + "\n"
        log_message += "Data Collection Time: " + timestamp + "\n"
        log_message += "Time Period Start: " + format(t_start, "%f") + "\n"
        log_message += "Time Period End: " + format(t_end, "%f") + "\n"
        log_message += "Starting angle (deg): " + start_angle + "\n"
        log_message += "Ending angle (deg): " + end_angle +  "\n"
        log_message += "Rotation range (deg): " + (end_angle - start_angle) + "\n"
        log_message += "Exposure Time (s): " + exposure + "\n"
        log_message += "Acquisition time (s): " + acquisition_time + "\n"
        log_message += "Total time (s): " + total_time + "\n"
        log_message += "Spot Size: " + spot_size + "\n"
        log_message += "Camera length (mm): " + camera_length + "\n"
        log_message += "Image pixelsize x/y (" + units_x + "): " + image_pixelsize_x + " " + image_pixelsize_y + "\n"
        log_message += "Image resolution x/y (px): " + image_res_x + " " + image_res_y + "\n"
        log_message += "Image physical pixelsize x/y (um): " + phys_pixelsize_x + " " + phys_pixelsize_y + "\n"
        log_message += "Camera binning x/y: " + binsize_x + " " + binsize_y + "\n"
        log_message += "Rotation axis (deg): " + rotation_axis + "\n"
        log_message += "Oscillation angle (deg): " + osc_angle + "\n"
        log_message += "Rotation speed (deg/s): " + rot_speed + "\n"
        log_message += "Number of frames: " + nframes + "\n"
 
        // Print log message to console
        Print(log_message)
 
        // Print log message to file
        string fn = PathConcatenate(exp_drc, "cRED_log.txt")
        number f = CreateFileForWriting(fn)
        WriteFile(f, log_message)
        CloseFile(f)
        Print("Wrote file " + fn)
        
        // Write data as tiff files
        if ( write_tiff_files )
        {
            self.SetStatus( "Writing tiff files" )
            Print("Writing tiff files...")
            for (i=0; i<nframes; i++)
            {
                string out = PathConcatenate(data_drc, "image_" + format(i+1, "%05d"))
                //Print("Writing " + out + ".tif")
                image frame := slice2(buffer, 0, 0, i, 0, xsize, 1, 1, ysize, 1)
                SaveAsTiff(frame, out, 1)
                self.DLGSetProgress( "progress_bar", (i+1)/nframes )
            }
        }
        
        self.SetStatus("Data collection completed")
        Print("Data collection completed")
    }

    object init(object self)
    {
        return self
    }

    TagGroup CreateDialog_UI( object self )
    {
        number label_width = 20
        number entry_width = 15
        number button_width = 50

        TagGroup label
        TagGroup Dialog_UI = DLGCreateDialog("insteadmatic")
        
        // Create a box for the i/o parameters             
        TagGroup io_box_items
        TagGroup io_box = DLGCreateBox("Input/Output", io_box_items).DLGFill("XY")

        // Work directory field
        TagGroup work_drc_field
        label = DLGCreateLabel("Work directory:").DLGWidth(label_width)
        work_drc_field = DLGCreateStringField(default_work_drc).DLGIdentifier("work_drc_field").DLGWidth(entry_width*4)
        TagGroup work_drc_group = DLGGroupItems(label, work_drc_field).DLGTableLayout(2, 1, 0)
        
        // Sample name field
        TagGroup sample_name_field
        label = DLGCreateLabel("Experiment name:").DLGWidth(label_width)
        sample_name_field = DLGCreateStringField(default_sample_name).DLGIdentifier("sample_name_field").DLGWidth(entry_width*4)
        TagGroup sample_name_group = DLGGroupItems(label, sample_name_field).DLGTableLayout(2, 1, 0)

        // Buttons
        TagGroup open_button = DLGCreatePushButton("Open work directory", "open_directory_pressed").DLGWidth(button_width)
        TagGroup browse_button = DLGCreatePushButton("Select work directory..", "browse_directory_pressed").DLGWidth(button_width)
        TagGroup button_field = DLGGroupItems(open_button, browse_button).DLGTableLayout(2, 1, 0).DLGAnchor("East")

        TagGroup io_group = DLGGroupItems(work_drc_group, sample_name_group, button_field).DLGTableLayout(1, 3, 0)
        io_box_items.DLGAddElement(io_group)
        Dialog_UI.DLGAddElement(io_box)

        // Box for the CRED experiment
        TagGroup cred_box_items
        TagGroup cred_box = DLGCreateBox("Continuous Rotation Electron Diffraction", cred_box_items).DLGFill("XY")

        TagGroup angle_activation
        label = DLGCreateLabel("Angle activation threshold (deg):").DLGWidth(label_width*2)
        angle_activation = DLGCreateRealField(default_activation_threshold).DLGIdentifier("angle_activation_field").DLGWidth(entry_width)
        TagGroup activation_threshold_group = DLGGroupItems(label, angle_activation).DLGTableLayout(2, 1, 0)

        TagGroup buffersize_field
        label = DLGCreateLabel("Buffer size:").DLGWidth(label_width*2)
        buffersize_field = DLGCreateIntegerField(default_buffersize).DLGIdentifier("buffersize_field").DLGWidth(entry_width)
        TagGroup buffersize_group = DLGGroupItems(label, buffersize_field).DLGTableLayout(2, 1, 0)

        TagGroup autostop_check = DLGCreateCheckBox("Stop data collection when stage stops moving", default_auto_stop).DLGIdentifier("CheckAutoStop").DLGAnchor("West")
        TagGroup autoblank_check = DLGCreateCheckBox("Blank the beam after data collection", default_auto_blank).DLGIdentifier("CheckAutoBlank").DLGAnchor("West")
        
        TagGroup cred_group = DLGGroupItems(activation_threshold_group, buffersize_group).DLGTableLayout(1, 2, 0).DLGAnchor("West")
        cred_group = DLGGroupItems(cred_group, autostop_check, autoblank_check).DLGTableLayout(1,3,0).DLGAnchor("West")
        cred_box_items.DLGAddElement(cred_group)
        Dialog_UI.DLGAddElement(cred_box)
        
        if ( use_temserver )
        {    
            // box for TEM server
            TagGroup server_box_items
            TagGroup server_box = DLGCreateBox("Rotation control (via TEM server)", server_box_items).DLGFill("XY")
           
            TagGroup rotation_field
            label = DLGCreateLabel("Target alpha angle (deg):").DLGWidth(label_width*2)
            rotation_field = DLGCreateRealField(default_target_angle).DLGIdentifier("rotation_field").DLGWidth(entry_width)
            TagGroup rotation_group = DLGGroupItems(label, rotation_field).DLGTableLayout(2, 1, 0)
            
            TagGroup rotation_speed_field
            label = DLGCreateLabel("Rotation speed:").DLGWidth(label_width*2)
            rotation_speed_field = DLGCreateRealField(default_rotspeed).DLGIdentifier("rotation_speed_field").DLGWidth(entry_width)
            TagGroup rotspeed_group = DLGGroupItems(label, rotation_speed_field).DLGTableLayout(2, 1, 0)

            TagGroup server_group = DLGGroupItems(rotation_group, rotspeed_group).DLGTableLayout(1,2,0).DLGAnchor("West")
            server_box_items.DLGAddElement(server_group)
            Dialog_UI.DLGAddElement(server_box)
        }

        // Experiment control box
        TagGroup control_box_items
        TagGroup control_box = DLGCreateBox("Control", control_box_items).DLGFill("XY")
        TagGroup start_button = DLGCreatePushButton("Start", "start_pressed").DLGIdentifier("start_button").DLGWidth(button_width)
        TagGroup stop_button = DLGCreatePushButton("Stop", "stop_pressed").DLGIdentifier("stop_button").DLGWidth(button_width)
        
        // Create the button box and contents
        label = DLGCreateLabel("Ready...").DLGWidth(label_width*2).DLGIdentifier("status")
        taggroup controlgroup = DLGGroupItems(start_button, stop_button, label).DLGTableLayout(3, 1, 0).DLGAnchor("West").DLGExpand("X")
        control_box_items.DLGAddElement(controlgroup)
        Dialog_UI.DLGAddElement(control_box)
        
        TagGroup progress_bar = DLGCreateProgressBar( "progress_bar" ).DLGFill("X")
        Dialog_UI.DLGAddElement(progress_bar)
        
        taggroup footer = DLGCreateLabel("Usage instructions: see the script source!")
        Dialog_UI.DLGAddElement(footer)
        return Dialog_UI
    }

    // default object constructor
    Dialog_UI( object self )
    {
        loop = false
        self.super.init( self.CreateDialog_UI() )
        number dialogID = self.ScriptObjectGetID()
        Print("Dialog created with ID:" + dialogID)
    }

    // default object destructor
    ~Dialog_UI( object self )
    {
        number dialogID = self.ScriptObjectGetID()
        result("Dialog with ID: " + dialogID + " destroyed.\n")
    }

    // If the dialog is closed, the thread is stopped
    void abouttoclosedocument(object self)
    {
        if ( loop ) 
        {
            self.stop_pressed()
            result("Dialog has been closed - Thread terminated.\n")
        }
    }
}


// Contain the main script as a function. This will ensure all script objects are destructed properly
void main()
    {
        // Create the dialog
        Print("\n")
        
        object Dialog_UI = Alloc(Dialog_UI).init()
        Dialog_UI.Display("InsteaDMatic")
        Return
    }


main()
