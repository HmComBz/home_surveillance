import base64
import cv2
import logging
import numpy as np
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


class Worker(mp.Process):
    def __init__(self, user_id, camera_id):
        ''' Worker thread for performing the actual work, analyzing, saving and alarming '''

        # Specifying class specific parameters
        super(Worker, self).__init__()
        self.camera_id = camera_id
        self.camera_data = self.import_camera_data_from_sql()
        self.stop_queue = mp.Queue(1)
        self.stopped = False
        self.user_id = user_id
        self.web_port = self.camera_data["web_socket"]

        # Create socket
        self.footage_socket = self.create_socket()

        # Load the YOLOv8 model
        self.model = YOLO('yolov8m.pt')

    #-------------------------------------------------------------------------------
    def close_socket(self):
        self.footage_socket.close()

    #-------------------------------------------------------------------------------
    def create_socket(self):
        ''' Create a socket connection for streaming camera feed '''

        try:
            context = zmq.Context()
            socket = context.socket(zmq.PUB)
            socket.connect('tcp://localhost:%s' % self.web_port)
            return socket
        except Exception as e:
            logger.error("Failed to create socket due to: %s" % e)
            return None
    
    #-------------------------------------------------------------------------------
    def import_camera_data_from_sql(self):
        # Import data
        try:
            columns = ["rtsp_main", "domain", "port", "user_name", "password", "web_socket"]
            table = "app_dimcameras"
            where_statements = [("id", self.camera_id)]
            return MysqlConnection().query_data(columns, table, where_statements)[0]
        except Exception as e:
            logger.error("Failed to import camera data from sql: %s" % e)
            return None

    #------------------------------------------------------------------------------
    def run(self):
        ''' Main loop for worker '''

        # Start camera stream
        self.camera_stream = Camera(self, self.user_id, self.camera_id)
        self.camera_stream.daemon = True
        self.camera_stream.start()
        logger.info('Camera %s: Camera handling thread started.' % self.camera_id)

        while not self.stopped:
            try:
                # Analyze image
                results = self.model(self.camera_stream.latest_image, conf=0.8)

                # Visualize the results
                annotated_frame = results[0].plot()

                # Send analyzed image through socket
                self.send_image_through_socket(annotated_frame)

                # Stop the system
                if not self.stop_queue.empty():
                    stop_status = self.stop_queue.get()
                    if stop_status == True:
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