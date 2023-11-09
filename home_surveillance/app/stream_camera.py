import logging
import time
import base64
import random
import socket
import selectors
import traceback
import types
import zmq
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse, StreamingHttpResponse, HttpResponseRedirect
from .models import DimCameras, DimPerson
from server.libclient import Message

# Create loggers for code
logger = logging.getLogger("select_camera")
logger.setLevel(logging.INFO)
logger.propagate = False

# Create handler
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)

# Add handler to logger
logger.addHandler(consoleHandler)

# Set formatting to logger
formatter = logging.Formatter('%(asctime)s  %(name)s  %(levelname)s: %(message)s')
consoleHandler.setFormatter(formatter)

# GLOBAL VARS
MESSAGE_PORT = 8080
IP_ADRESS = "192.168.0.135"


################################################################################
# General functions
################################################################################
def import_camera_list(user_id):
    data = []
    cameras = DimCameras.objects.filter(user_id=user_id)
    for camera in cameras:
        temp_dict = {"id":camera.id, "user_id":camera.user_id, "camera_name":camera.camera_name,
                    "detection_status":camera.detection_status, "selected_status":camera.selected_status}
        data.append(temp_dict)
    return data

################################################################################
# Manage sockets
################################################################################
def create_request(message):
    ''' Create request in bytes '''

    return dict(
        type="binary/custom-client-binary-type",
        encoding="binary",
        content=message,
    )

#-------------------------------------------------------------------------------
def create_socket_connection(request):
    ''' Start socket connection '''

    try:
        sel = selectors.DefaultSelector()
        addr = (IP_ADRESS, MESSAGE_PORT)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.connect_ex(addr)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        message = Message(sel, sock, addr, request)
        sel.register(sock, events, data=message)
        logger.info("Starting connection to host %s through port %s." % addr)
        return sel
    except Exception as e:
        logger.error("Failed to start connection under select camera: %s." % e)
        return None

################################################################################
# Support functions for views
################################################################################
def check_if_port_is_used(ip, port: int) -> bool:
    ''' Check if the port is beeing used '''

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((ip, port)) == 0

#-------------------------------------------------------------------------------
def create_new_socket(camera_id):
    ''' Create a new socket. '''

    # Import web port for selected camera
    port = DimCameras.objects.get(id=camera_id).web_socket
    logger.info("Creating a connection for camera %s and port %s." % (camera_id, port))

    try:
        # Create the connection to recieve video stream
        context = zmq.Context()
        footage_socket = context.socket(zmq.SUB)
        footage_socket.setsockopt(socket.SO_REUSEADDR, 1)
        footage_socket.bind('tcp://*:%s' % port)
        footage_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        return footage_socket
    except Exception as e:
        logger.error("Failed to create socket on client side: %s" % e)
        time.sleep(10)

#-------------------------------------------------------------------------------
def gen(camera_id):
    ''' Function generating streaming frames. '''

    # Define parameters
    fps_limit = 4

    # Set up socket
    footage_socket = create_new_socket(camera_id)

    # Run streaming loop
    while True:
        start_time = time.time()
        try:
            frame = footage_socket.recv_string()
            img = base64.b64decode(frame)
        except Exception as e:
            logger.error("Camera %s: No frame recieved from socket under gen: %s" % (camera_id, e))
            break

        try:
            # Resize image and generate img to show in browser
            if img != None:
                yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n')

                # Keeping cameras at fixed FPS
                end_time = time.time() - start_time
                if end_time < (1/fps_limit):
                    diff = (1/fps_limit) - end_time
                    time.sleep(diff)

        except Exception as e:
            logger.error("Camera %s: Failed to convert image to jpg under gen: %s" % (camera_id, e))

#-------------------------------------------------------------------------------
def update_system_status(user_id, value):
    ''' Update system status '''
    
    try:
        person = DimPerson.objects.get(user_id=user_id)
        person.system_status = value
        person.save()
        logger.info("System status updated for user %s and was set to %s" % (user_id, value))
        return value
    except Exception as e:
        logger.error("Failed to update system status due to: %s" % e)
        return 0


################################################################################
# View functions
################################################################################
def camera(request, camera_id):
    ''' Function for creating StreamingHttpResponse for camera 1. '''

    try:
        # Create streaming object for selected camera     
        return StreamingHttpResponse(gen(camera_id),
                    content_type='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        logger.error("Camera stream failed due to: %s" % e)
        return HttpResponse(False, content_type='text/plain')
    
#------------------------------------------------------------------------------
def view_camera(request, camera_id):
    ''' Communicating with server script to start cameras based on user selections '''

    # Current user
    current_user = request.user.id

    # Get system status
    system_status = DimPerson.objects.get(user_id=current_user).system_status

    # Update camera status in database
    camera_list = DimCameras.objects.filter(user_id=current_user)
    id_list = [camera.id for camera in camera_list]
    DimCameras.objects.filter(id__in=id_list).update(selected_status=0)
    camera = DimCameras.objects.get(id=camera_id)
    camera.selected_status = 1
    camera.save()

    # Start connection
    msg = str("start") + "-" + str(current_user) + "-" + str(camera_id)
    bytes_msg = bytes(msg, encoding="utf-8")
    selection_request = create_request(bytes_msg)
    sel = create_socket_connection(selection_request)

    # Start loop for managing connection
    try:
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                message = key.data
                message.process_events(mask)
                try:
                    pass
                except Exception as e:
                    logger.error("Failed to send message to handle camera due to: %s" % e)
                    message.close()
            # Check for a socket being monitored to continue.
            if not sel.get_map():
                break
    except KeyboardInterrupt:
        logger.error("Caught keyboard interrupt, exiting.")
    finally:
        sel.close()

    # Create a dictionary of cameras to create camera list at home view
    data = import_camera_list(current_user)

    return render(request, "home.html", {"selected_camera":camera_id, "view":system_status, "data":data})
    
#------------------------------------------------------------------------------
def manage_system(request, task):
    ''' Main view for starting the camera system '''

    # Current user
    current_user = request.user.id

    # Manage system status
    if task == "start":
        system_status = update_system_status(current_user, 1)
    else:
        system_status = update_system_status(current_user, 0)
        
    # Loop through cameras and create messages
    selected_camera = DimCameras.objects.get(user_id=current_user, selected_status=1).id
    messages = []
    cameras = DimCameras.objects.filter(user_id=current_user, detection_status=1).values_list("id")
    for cam in cameras:
        messages.append(str(task) + "-" + str(current_user) + "-" + str(cam[0]))

    # Start connection
    msg = '|'.join(messages)
    bytes_msg = bytes(msg, encoding="utf-8")
    selection_request = create_request(bytes_msg)
    sel = create_socket_connection(selection_request)

    # Start loop for managing connection
    try:
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                message = key.data
                message.process_events(mask)
                try:
                    pass
                except Exception as e:
                    logger.error("Failed to send message to handle camera due to: %s" % e)
                    message.close()
            # Check for a socket being monitored to continue.
            if not sel.get_map():
                break
    except KeyboardInterrupt:
        logger.error("Caught keyboard interrupt, exiting.")
    finally:
        sel.close()

    # Create a dictionary of cameras to create camera list at home view
    camera_data = import_camera_list(current_user)
    
    return render(request, "home.html", {"selected_camera":selected_camera, "view":system_status, "data":camera_data})