import libserver
import logging
import selectors
import socket
import sys
import time
import traceback
import types
import multiprocessing as mp
from threading import Thread
from camera import Camera
from home_surveillance.server.mysql_conn import MysqlConnection

# Create loggers for code
logger = logging.getLogger("server")
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


####################################################################################
# Maintenance class for managing cameras
####################################################################################
class Maintenance(mp.Process):
    def __init__(self, parent):
        super(Maintenance, self).__init__()
        self.job_queue = mp.Queue()
        self.parent = parent

    #-------------------------------------------------------------------------------
    def add_new_camera(self, camera_id):
        ''' Start a new camera and store it in active camera dictionary '''

        status = self.check_if_camera_exists(camera_id)
        if status == False:
            self.active_camera_id = camera_id
            camera = Camera(camera_id)
            camera.daemon = True
            camera.start()
            self.parent.camera_streams[camera_id] = camera
            logger.info("Camera %s started." % camera_id)

    #-------------------------------------------------------------------------------
    def check_if_camera_exists(self, camera_id):
        ''' Check if camera is allready active '''

        if camera_id in self.parent.camera_streams.keys():
            return True
        else:
            return False

    #-------------------------------------------------------------------------------
    def close_old_camera(self, camera_id):
        ''' Close active camera '''

        try:
            print(self.parent.camera_streams)
            self.parent.camera_streams[camera_id].stopped = True
            self.parent.camera_streams[camera_id].join()
            del self.parent.camera_streams[camera_id]
        except Exception as e:
            logger.error("Camera %s failed to stop due to: %s" % (camera_id, e))

    #-------------------------------------------------------------------------------
    def run(self):
        ''' Run maintenance main loop for handling cameras '''    
        
        while True:
            # If que is not empty, proceed with start/close of camera
            if not self.job_queue.empty():
                data = self.job_queue.get()
                task, current_user, camera_id = data.split('-')
                if task == "start":
                    self.add_new_camera(camera_id)
                    logger.info("%s camera %s for user %s." % (task, camera_id, current_user))
                elif task == "stop":
                    pass
                else:
                    pass
            

####################################################################################
# Server class
####################################################################################
class Server():
    def __init__(self):
        self.active_camera_id = None
        self.camera_streams = {}
        self.host = "192.168.0.135"
        self.port = 8080
        self.stopped = False

    #-------------------------------------------------------------------------------
    def accept_wrapper(self, sel, sock):
        ''' Verify the connection and accept it '''

        try:
            conn, addr = sock.accept()  # Should be ready to read
            conn.setblocking(False)
            message = libserver.Message(sel, conn, addr)
            sel.register(conn, selectors.EVENT_READ, data=message)
            logger.info("Accepted connection from host %s through port %s." % addr)
        except Exception as e:
            logger.error("The accept wrapper failed due to: %s" % e)

    #-------------------------------------------------------------------------------
    def create_socket(self):
        ''' Create a socket '''

        try:
            sel = selectors.DefaultSelector()
            lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            lsock.bind((self.host, self.port))
            lsock.listen()
            lsock.setblocking(False)
            sel.register(lsock, selectors.EVENT_READ, data=None)
            logger.info("Listening on %s at port %s." % (self.host, self.port))
            return sel
        except Exception as e:
            logger.error("Failed to create socket due to: %s" % e)

    #-------------------------------------------------------------------------------
    def import_current_camera_selection_status_sql(self):
        ''' Generate rtsp-stream from SQL data '''

        try:
            # Import data
            columns = ["id", "selected_status"]
            table = "app_dimcameras"
            where_statements = [("selected_status", 1)]
            camera = MysqlConnection().query_data(columns, table, where_statements)[0]
            return camera["id"]    
        except Exception as e:
            logger.error("Failed to import selected status from sql: %s" % e)
            return False
    
    #-------------------------------------------------------------------------------
    def run(self):
        ''' Main server script '''

        # Create a socket
        sel = self.create_socket()

        # Start maintenance thread managing cameras
        self.maintenance = Maintenance(self)
        self.maintenance.daemon = True
        self.maintenance.start()

        try:
            while not self.stopped:
                events = sel.select(timeout=None)
                for key, mask in events:
                    if key.data is None:
                        self.accept_wrapper(sel, key.fileobj)
                    else:
                        message = key.data
                        try:
                            message.process_events(mask)
                            msg = message.request.decode('utf-8')
                            msg_list = msg.split("|")
                            for m in msg_list:
                                action, current_user, camera_id = m.split('-')
                                if action == "start": 
                                    self.maintenance.add_new_camera(camera_id)
                                    logger.info("Camera %s for user %s put in to queue." % (camera_id, current_user))
                                elif action == "stop":
                                    self.maintenance.close_old_camera(camera_id)
                                    logger.info("Camera %s for user %s was closed." % (camera_id, current_user))
                        except Exception as e:
                            logger.error("Error in retrieving message for starting cameras due to: %s" % e)
                            message.close()
        except KeyboardInterrupt:
            logger.error("Caught keyboard interrupt, exiting.")
        finally:
            sel.close()


if __name__ == '__main__':
    server = Server()
    server.run()
