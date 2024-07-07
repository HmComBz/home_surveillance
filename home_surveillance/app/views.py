import logging
import socket
import sys
import time
import traceback
from django.shortcuts import render, redirect
from django.http.response import HttpResponse, StreamingHttpResponse
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from server.libclient import Message
from .models import DimCameras, DimPerson
from app import camera_functions

# Create loggers for code
logger = logging.getLogger("views")
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


#------------------------------------------------------------------------------
@login_required
def main(request):
    # Current user
    current_user = request.user.id

    # Import camera list
    selected_camera = 0
    data = []
    system_status = DimPerson.objects.get(user_id=current_user).system_status
    cameras = DimCameras.objects.filter(user_id=current_user)
    for camera in cameras:
        temp_dict = {"id":camera.id, "user_id":camera.user_id, "camera_name":camera.camera_name,
                     "detection_status":camera.detection_status, "selected_status":camera.selected_status}
        data.append(temp_dict)
        if camera.selected_status == 1:
            selected_camera = str(camera.id)
    return render(request, "home.html", {"selected_camera":selected_camera, "system_status":system_status, "data":data})

#------------------------------------------------------------------------------
@login_required
def history(request, view):
    return render(request, "history.html", {"view":view})

#------------------------------------------------------------------------------
def about(request):
    return render(request, "about.html")

#------------------------------------------------------------------------------
def camera(request, camera_id):
    ''' Function for creating StreamingHttpResponse for camera 1. '''

    try:
        # Create streaming object for selected camera
        return StreamingHttpResponse(camera_functions.gen(camera_id),
                    content_type='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        logger.error("Camera stream failed due to: %s" % e)
        return HttpResponse(False, content_type='text/plain')

#------------------------------------------------------------------------------
def include_camera(request, camera_id):
    # Current user
    current_user = request.user.id

    # Get system status
    system_status = DimPerson.objects.get(user_id=current_user).system_status

    # Set status to include camera in the camera system
    camera_obj = DimCameras.objects.get(id=camera_id)
    camera_obj.detection_status = 1
    camera_obj.save()

    # Create a dictionary of cameras to create camera list at home view
    data = camera_functions.import_camera_list(current_user)

    return render(request, "home.html", {"selected_camera":camera_id, "system_status":system_status, "data":data})

#------------------------------------------------------------------------------
def exclude_camera(request, camera_id):
    # Current user
    current_user = request.user.id

    # Get system status
    system_status = DimPerson.objects.get(user_id=current_user).system_status

    # Set status to include camera in the camera system
    camera_obj = DimCameras.objects.get(id=camera_id)
    camera_obj.detection_status = 0
    camera_obj.save()

    # Create a dictionary of cameras to create camera list at home view
    data = camera_functions.import_camera_list(current_user)

    return render(request, "home.html", {"selected_camera":camera_id, "system_status":system_status, "data":data})

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
    msg = "view-" + str(camera_id) + "-" + str(current_user)
    bytes_msg = bytes(msg, encoding="utf-8")
    selection_request = camera_functions.create_request(bytes_msg)
    sel = camera_functions.create_socket_connection(selection_request)

    # Start loop for managing connection
    try:
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                message = key.data
                try:
                    message.process_events(mask)
                    message.close()
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
    data = camera_functions.import_camera_list(current_user)

    return render(request, "home.html", {"selected_camera":camera_id, "system_status":system_status, "data":data})

#------------------------------------------------------------------------------
def manage_system(request, task):
    ''' Main view for starting the camera system. All cameras with status active will be
        started automatically when users starts the system '''

    # Current user
    current_user = request.user.id

    # Manage system status
    if task == "start":
        system_status = camera_functions.update_system_status(current_user, 1)
    else:
        system_status = camera_functions.update_system_status(current_user, 0)

    # Start connection
    msg = "manage-" + str(task) + "-" + str(current_user)
    bytes_msg = bytes(msg, encoding="utf-8")
    selection_request = camera_functions.create_request(bytes_msg)
    sel = camera_functions.create_socket_connection(selection_request)

    # Start loop for managing connection
    try:
        while True:
            events = sel.select(timeout=1)
            for key, mask in events:
                message = key.data
                try:
                    message.process_events(mask)
                    message.close()
                    logger.info("Message sent to server to %s cameras for user %s." % (task, current_user))
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

    return redirect(main)
