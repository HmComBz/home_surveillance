import base64
import cv2
import logging
import socket
import time
import zmq
from threading import Thread
from home_surveillance.server.mysql_conn import MysqlConnection
from home_surveillance.app.security import encryption


# Create loggers for code
logger = logging.getLogger("camera")
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


class Camera(Thread):
    def __init__(self, camera_id):
        Thread.__init__(self, name=("Camera-%s" % camera_id))
        self.camera_id = camera_id
        self.camera_data = self.import_camera_data_from_sql()
        self.rtsp = self.generate_rtsp()
        self.fps_limit = 4
        self.web_port = self.camera_data["web_socket"]
        self.status = 1

        # Create socket
        self.footage_socket = self.create_socket()

        # Get the first frame and get the size of it
        try:
            self.stream = cv2.VideoCapture(self.rtsp)
            (self.grabbed, self.frame) = self.stream.read()
            res = self.frame.shape
            self.x_res = res[1]
            self.y_res = res[0]
            self.stopped = False
        except Exception as e:
            self.stopped = True
            logger.error("Error in capturing camera stream for camera %s: %s" % (self.camera_id, e))

    #-------------------------------------------------------------------------------
    def close_socket(self):
        self.footage_socket.close()

    #-------------------------------------------------------------------------------
    def create_socket(self):
        ''' Create a socket connection for streaming camera feed '''

        context = zmq.Context()
        socket = context.socket(zmq.PUB)
        socket.connect('tcp://localhost:%s' % self.web_port)
        return socket

    #-------------------------------------------------------------------------------
    def generate_rtsp(self):
        ''' Generate rtsp-stream from SQL data '''

        try:
            rtsp_main = self.camera_data["rtsp_main"]
            domain = self.camera_data["domain"]
            port = self.camera_data["port"]
            username = self.camera_data["user_name"]
            password = self.camera_data["password"]

            # Put together RTSP-stream
            return "rtsp://%s:%s@%s:%s%s" % (username, password, domain, port, rtsp_main)
        except Exception as e:
            logger.error("Camera %s: Generate rstp link failed under worker due to: %s" % (self.camera_id, e))
            return ""
        
    #-------------------------------------------------------------------------------
    def import_camera_data_from_sql(self):
        # Import data
        columns = ["rtsp_main", "domain", "port", "user_name", "password", "web_socket"]
        table = "app_dimcameras"
        where_statements = [("id", self.camera_id)]
        return MysqlConnection().query_data(columns, table, where_statements)[0]

    #-------------------------------------------------------------------------------    
    def resize_image(self, image, x, y):
        ''' Resizing image to fit the video boxes on the home page '''

        new_x = 0
        new_y = 0

        try:
            # Get size of image
            x_img = image.shape[1]
            y_img = image.shape[0]

            # Scale image after the smallest side of x and y
            if x_img >= y_img:
                if x_img >= x:
                    new_x = int((x / x_img) * x_img)
                    new_y = int((y_img / x_img) * new_x)
                else:
                    new_x = x_img
                    new_y = y_img
            else:
                if y_img >= y:
                    new_y = int((y / y_img) * y_img)
                    new_x = int((x_img / y_img) * new_y)
                else:
                    new_x = x_img
                    new_y = y_img
        except Exception as e:
            logger.error("Failed to convert x- and y-coordinates under resize image: %s." % e)

        # Resize image
        try:
            new_image = cv2.resize(image, (new_x, new_y), interpolation = cv2.INTER_AREA)
        except Exception as e:
            new_image = None
            logger.error("Failed to resize image under resize image: %s." % e)

        return new_image
    
    #-------------------------------------------------------------------------------
    def run(self):
        skip_counter = 0
        prev = 0

        while not self.stopped:
            # Get new frames
            time_elapsed = time.time() - prev
            (self.grabbed, self.frame) = self.stream.read()

            # If time elapsed is larger than frame rate
            if time_elapsed > (1 / self.fps_limit):
                prev = time.time()

                # Check if images is OK
                if self.grabbed:
                    try:
                        # Resize image and sent it through the socket
                        if self.status == 1:
                            new_image = self.resize_image(self.frame, 920, 700)
                            self.send_image_through_socket(new_image)
                    except Exception as e:
                        logger.error("Camera %s: No analyzed image was recieved under main loop: %s" % (self.camera_id, e))
                else:
                    skip_counter += 1

    #-------------------------------------------------------------------------------
    def send_image_through_socket(self, image):
        encoded, buffer = cv2.imencode('.jpg', image)
        jpg_as_text = base64.b64encode(buffer)
        self.footage_socket.send(jpg_as_text)
