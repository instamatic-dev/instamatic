from instamatic import config
from instamatic.camera.camera_server import ServerCam

camera_id = config.camera.name


if __name__ == "__main__":
    ## Usage: 
    ##    First run cam_server.py (or `instamatic.camserver.exe`)
    ##    Second, run cam_client.py
    
    cam = ServerCam(camera_id)

    from IPython import embed
    embed()
