import logging
import numpy as np
import time
import base64
import random
import socket
import selectors
import traceback
import types
import zmq
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse, StreamingHttpResponse
from .models import DimCameras, DimPerson
from server.libclient import Message

# Create loggers for code
logger = logging.getLogger("camera_functions")
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

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((ip, port)) == 0:
                s.shutdown(socket.SHUT_RDWR)
                s.close()
                logger.info("Port %s was closed for %s" % (port, ip))
    except Exception as e:
        logger.error("The check if port is beeing used failed for port %s: %s" % (port, e))

#-------------------------------------------------------------------------------
def create_new_socket(camera_id):
    ''' Create a new socket. '''

    # Import web port for selected camera
    port = DimCameras.objects.get(id=camera_id).web_socket
    logger.info("Creating a connection for camera %s and port %s." % (camera_id, port))

    # Check if port beeing used
    check_if_port_is_used(IP_ADRESS, port)

    for i in range(0,3):
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
