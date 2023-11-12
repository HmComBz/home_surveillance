import os
import cv2
import sys
import copy
import numpy as np
import time
import logging
import math
import statistics
import socket
from datetime import datetime
from itertools import repeat
from functools import partial
from threading import Thread
from PIL import Image
import multiprocessing as mp
from camera import Camera

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
        self.stop_queue = mp.Queue(1)
        self.stopped = False
        self.user_id = user_id

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
                if not self.stop_queue.empty():
                    stop_status = self.stop_queue.get()
                    if stop_status == True:
                        self.camera_stream.stop()
                        self.camera_stream.join()
                        self.stopped = True
                        logger.info("Camera %s: Video thread has been successfully stopped." % self.camera_id)
            except Exception as e:
                logger.error("Camera %s: Failed to stop video thread due to: %s" % (self.camera_id, e))