import base64
import cv2
import logging
import numpy as np
import requests
import socket
import time
import zmq
from datetime import datetime
from itertools import repeat
from functools import partial
from PIL import Image
from threading import Thread
from ultralytics import YOLO
import multiprocessing as mp
from camera import Camera
from home_surveillance.server.mysql_conn import MysqlConnection

# Create loggers for code
logger = logging.getLogger("worker")
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

# Load the YOLOv8 model
def import_model():
    return YOLO('yolov8m.pt')

class Worker(mp.Process):
    def __init__(self, user_id, camera_id, camera_queue):
        ''' Worker thread for performing the actual work, analyzing, saving and alarming '''

        # Specifying class specific parameters
        super(Worker, self).__init__()
        self.camera_id = camera_id
        self.camera_data = self.import_camera_data_from_sql()
        self.camera_detection_status = int(self.camera_data["detection_status"])
        self.camera_selected_status = int(self.camera_data["selected_status"])
        self.camera_queue = camera_queue
        self.host = "192.168.0.135"
        self.stopped = False
        self.user_id = user_id
        self.web_socket = self.camera_data["web_socket"]

        # Alarm statuses
        self.alarm_status = 0
        self.class_statuses = self.create_class_statuses()
        self.max_time_no_spots = 30

        # Create socket
        #self.check_if_port_is_used()
        self.footage_socket = self.create_socket()

        # Message user
        logger.info("Worker process started for user %s and camera %s." % (self.user_id, self.camera_id))

    #-------------------------------------------------------------------------------
    def __reduce__(self):
        ''' Here we return a tuple containing the class reference and initialization arguments. '''
        return (self.__class__, (self.user_id, self.camera_id, self.camera_queue))

    #-------------------------------------------------------------------------------
    def check_if_port_is_used(self):
        ''' Check if the port is beeing used '''

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((self.host, self.web_socket)) == 0:
                    s.close()
                    logger.info("Port %s was closed for %s" % (self.web_socket, self.host))
        except Exception as e:
            logger.error("The check if port is beeing used failed for port %s: %s" % (self.web_socket, e))

    #-------------------------------------------------------------------------------
    def close_socket(self):
        self.footage_socket.close()

    #-------------------------------------------------------------------------------
    def create_alarm_label(self):
        ''' Create label for alamr status to be shown on the camera feed '''

        status_label = None
        if self.alarm_status == 1:
            status_label = "Active"
        else:
            status_label = "Inactive"  
        return "Alarm status: %s" % status_label

    #-------------------------------------------------------------------------------
    def create_class_statuses(self):
        ''' Create a dict containing all classes and their statuses '''

        alarm_dict = {"person":{}, "bicycle":{}, "car":{}, "motorcycle":{}, "bus":{}, "truck":{}, "dog":{}, "horse":{}}
        for key in alarm_dict:
            alarm_dict[key]["timestamp"] = 0
            alarm_dict[key]["status"] = 0
        return alarm_dict

    #-------------------------------------------------------------------------------
    def create_socket(self):
        ''' Create a socket connection for streaming camera feed '''

        try:
            context = zmq.Context()
            footage_socket = context.socket(zmq.PUB)
            footage_socket.connect('tcp://localhost:%s' % self.web_socket)
            return footage_socket
        except Exception as e:
            logger.error("Failed to create socket due to: %s" % e)
            return None

    #-------------------------------------------------------------------------------
    def import_camera_data_from_sql(self):
        ''' Import camera data '''
        try:
            columns = ["camera_name", "rtsp_main", "domain", "port", "user_name", "password", "web_socket", "detection_status", "selected_status"]
            table = "app_dimcameras"
            where_statements = [("id", self.camera_id)]
            return MysqlConnection().query_data(columns, table, where_statements)[0]
        except Exception as e:
            logger.error("Failed to import camera data from sql: %s" % e)
            return None
        
    #-------------------------------------------------------------------------------
    def import_user_data_from_sql(self):
        ''' Import user data '''

        try:
            columns = ["account_type", "max_cameras", "push_token", "push_user", "user_id", "system_status"]
            table = "app_dimperson"
            where_statements = [("user_id", self.user_id)]
            return MysqlConnection().query_data(columns, table, where_statements)[0]
        except Exception as e:
            logger.error("Failed to import user data from sql: %s" % e)
            return None

    #-------------------------------------------------------------------------------
    def manage_camera_status(self, action):
        # If action was sent to activate camera
        if action == "activate":
            self.camera_selected_status = 1
        elif action == "inactivate":
            self.camera_selected_status = 0

    #-------------------------------------------------------------------------------
    def pushover_alert(self, spotted_class, first_image):
        ''' Message user when something has been spotted. '''

        try:
            settings = self.import_user_data_from_sql()
            priority = 1
            is_success, im_buf_arr = cv2.imencode(".jpg", first_image)
            r = requests.post("https://api.pushover.net/1/messages.json", data = {
              "token": settings["push_token"],
              "user": settings["push_user"],
              "message": "A %s has been spotted on camera %s with priority %s!" % (spotted_class, self.camera_data["camera_name"], priority),
              "priority": priority,
              "retry": 60,
              "expire": 180
            },
            files = {"attachment": ("image.jpg", im_buf_arr, "image/jpeg")}
            )
            logger.info("Camera %s: Pushover successfully delivered with priority %s" % (self.camera_id, priority))
        except Exception as e:
            logger.error("Camera %s: Pushover failed to deliver alarm message: %s" % (self.camera_id, e))

    #-------------------------------------------------------------------------------
    def reset_statuses(self):
        ''' Reset all alarm statuses that have not had any spots in a certain time period '''

        try:
            now = time.time()
            num_active_classes = 0
            # Loop through classes and check if class has been spotted within thresh or not.
            for key in self.class_statuses:
                if self.class_statuses[key]["status"] == 1:
                    num_active_classes += 1
                    time_diff = now - self.class_statuses[key]["timestamp"]
                    if time_diff >= self.max_time_no_spots:
                        self.class_statuses[key]["status"] = 0
                        num_active_classes -= 1
                        logger.info("Camera %s: Max thresh no spots reached for class %s" % (self.camera_id, key))                

            # If no class has been spotted, set global alarm level.
            if num_active_classes == 0:
                self.alarm_status = 0
                logger.info("Camera %s: No active classes, global alarm status set to 0." % self.camera_id)
        except Exception as e:
            logger.error("Failed to reset statuses due to: %s" % e)

    #-------------------------------------------------------------------------------
    def run(self):
        ''' Main loop for worker '''

        # Start camera stream
        logger.info("Starting camera thread for user %s and camera %s." % (self.user_id, self.camera_id))
        self.camera_stream = Camera(self, self.user_id, self.camera_id)
        self.camera_stream.daemon = True
        self.camera_stream.start()

        # Import model
        self.model = import_model()

        action = ""
        while not self.stopped:
            try:
                # Check if command was sent
                if not self.camera_queue.empty():
                    action = self.camera_queue.get()
                    logger.info("Command recieved for camera %s: %s" % (self.camera_id, action))

                # Manage camera status for when camera is activated or deactivated to be shown in browser
                self.manage_camera_status(action)
            except Exception as e:
                logger.error("Camera %s: Unable to retrieve camera status: %s" % (self.camera_id, e))

            # Calculating time
            start_time = time.time()  

            # Analyze image
            try:
                # Classes: 0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck, 16: dog, 17, horse
                results = self.model(self.camera_stream.latest_image, classes=[0, 1, 2, 3, 5, 7, 16, 17], conf=0.8, verbose=False)
                final_class_list = []
                for result in results:
                    if "(no detections)," not in result.verbose():
                        class_string = result.verbose().split(" ")[1]
                        final_class_list.append(class_string[0:len(class_string)-1])
            except Exception as e:
                logger.error("Camera %s: Failed to analyze the image from the camera feed: %s" % (self.camera_id, e))

            # Manage the result image adding labels to it
            try:
                if self.camera_detection_status == 1:
                    # Visualize the results
                    result_image = results[0].plot()
                    fps_label = "FPS: %.2f   Alarm status: %s" % ((1 / (time.time() - start_time)), self.alarm_status)
                    cv2.rectangle(result_image, (0, 0), (result_image.shape[1], 20), (0,0,0), -1)
                    cv2.putText(result_image, fps_label, (10, 15), cv2.FONT_HERSHEY_PLAIN, 0.85, (255, 255, 255), 1)
            except Exception as e:
                logger.error("Camera %s: Unable to transform the result image due to: %s" % (self.camera_id, e))

            # If camera is active to show image, send image through socket
            try:
                if self.camera_selected_status == 1:
                    self.send_image_through_socket(result_image)
            except Exception as e:
                logger.error("Camera %s: Failed to visualize the image due to: %s" % (self.camera_id, e))

            # Update alarm status, if off, set to active. If active, update timestamp.
            try:    
                if len(final_class_list) > 0:
                    for spotted_class in final_class_list:
                        if self.class_statuses[spotted_class]["status"] == 0:
                            self.class_statuses[spotted_class]["status"] = 1
                            self.class_statuses[spotted_class]["timestamp"] = time.time()
                            self.pushover_alert(spotted_class, result_image)
                            self.alarm_status = 1
                            logger.info("Camera %s: Status for %s set to active. User has been notified." % (self.camera_id, spotted_class))
                        else:
                            self.class_statuses[spotted_class]["timestamp"] = time.time()
                else:
                    if self.alarm_status == 1:
                        self.reset_statuses()
            except Exception as e:
                logger.error("Camera %s: Alarm status failed to update due to: %s" % (self.camera_id, e))

            # Stop the system
            try:
                if action == "stop":
                    self.camera_stream.stop()
                    self.camera_stream.join()
                    self.stopped = True
                    logger.info("Camera %s: Video thread has been successfully stopped." % self.camera_id)
            except Exception as e:
                logger.error("Camera %s: Failed to stop video thread due to: %s" % (self.camera_id, e))

    #-------------------------------------------------------------------------------
    def send_image_through_socket(self, image):
        encoded, buffer = cv2.imencode('.jpg', image)
        jpg_as_text = base64.b64encode(buffer)
        self.footage_socket.send(jpg_as_text)

    #--------------------------------------------------------------------------------
    def stop(self):
        ''' Stop video stream '''
        self.stopped = True
