import libserver
import logging
import selectors
import socket
import sys
import time
import multiprocessing as mp
from worker import Worker
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
# Server class
####################################################################################
class Server():
    def __init__(self):
        self.active_camera_id = None
        self.camera_workers = {}
        self.camera_queues = {}
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
    def add_new_stream(self, user_id, camera_id):
        ''' Start a new camera and store it in active camera dictionary '''

        status = self.check_if_camera_exists(camera_id)
        if status == False:
            try:
                self.active_camera_id = camera_id
                self.camera_queues[camera_id] = mp.Queue()
                self.camera_workers[camera_id] = Worker(user_id, camera_id, self.camera_queues[camera_id])
                self.camera_workers[camera_id].daemon = True
                self.camera_workers[camera_id].start()
            except Exception as e:
                logger.error("Camera %s failed to start for user %s due to: %s" % (camera_id, user_id, e))
        else:
            logger.info("Camera %s is already active." % camera_id)


    #-------------------------------------------------------------------------------
    def check_if_camera_exists(self, camera_id):
        ''' Check if camera is allready active '''

        try:
            if camera_id in self.camera_workers.keys():
                return True
            else:
                return False
        except Exception as e:
            logger.error("Check if camera is active failed: %s" % e)
            return False

    #-------------------------------------------------------------------------------
    def convert_tuple_to_string(self, tuple):
        return "(" + ",".join(tuple) + ")"

    #-------------------------------------------------------------------------------
    def close_old_stream(self, camera_id):
        ''' Close active camera '''

        try:
            self.camera_queues[camera_id].put("stop")
            logger.info("Camera %s closed successfully." % camera_id)
        except Exception as e:
            logger.error("Camera %s failed to stop due to: %s" % (camera_id, e))

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

    #--------------------------------------------------------------------------------
    def create_user_camera_dict(self, user_list):
        user_dict = {}
        for user in user_list:
            user_dict[user] = []
        return user_dict

    #-------------------------------------------------------------------------------
    def first_startup_check(self):
        ''' Check if system is set to active '''

        # Import user data
        user_list = self.get_users_with_system_active()

        # Import camera data
        if len(user_list) > 0:
            user_camera_dict = self.import_user_camera_data(user_list)

            # Start cameras
            for user_id in user_camera_dict:
                for camera_id in user_camera_dict[user_id]:
                    logger.info("At startup: Starting camera %s for user %s." % (camera_id, user_id))
                    self.add_new_stream(user_id, camera_id)

    #-------------------------------------------------------------------------------
    def get_camera_selection_status(self, camera_id):
        ''' Check if camera is selected to be shown '''

        query = """ SELECT system_status FROM app_dimcameras
                    WHERE camera_id = %s;
                """ % camera_id
        try:
            return MysqlConnection().custom_query_data(query)[0]
        except Exception as e:
            logger.error("Unable to import active user list from MySQL: %s" % e)

    #-------------------------------------------------------------------------------
    def import_user_camera_data(self, user_list):
        ''' Get a list of all cameras with active status for all users with active system '''

        str_tuple = self.convert_tuple_to_string(user_list)
        query = """ SELECT id, user_id FROM app_dimcameras
                    WHERE user_id IN %s
                    AND detection_status = 1;
                """ % str_tuple

        user_dict = self.create_user_camera_dict(user_list)
        try:
            results = MysqlConnection().custom_query_data(query)
            for r in results:
                user_dict[str(r[1])].append(str(r[0]))
            return user_dict
        except Exception as e:
            logger.error("Unable to import active camera list from MySQL: %s" % e)
            return user_dict

    #-------------------------------------------------------------------------------
    def get_users_with_system_active(self):
        ''' Import complete list of users that has system_status set to 1 '''

        query = """ SELECT user_id FROM app_dimperson
                    WHERE system_status = 1;
                """
        try:
            results = MysqlConnection().custom_query_data(query)
            list_of_users = []
            for r in results:
                list_of_users.append(str(r[0]))
            return tuple(list_of_users)
        except Exception as e:
            logger.error("Unable to import active user list from MySQL: %s" % e)

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
    def reset_active_camera_settings(self):
        ''' Set all statuses to non active of all cameras '''

        try:
            camera_list = list(self.camera_workers.keys())
            for camera_id in camera_list:
                self.camera_queues[camera_id].put("inactivate")
        except Exception as e:
            logger.error("Failed to reset active camera statuses due to: %s" % e)

    #-------------------------------------------------------------------------------
    def run(self):
        ''' Main server script '''

        # Check if system is set to active
        self.first_startup_check()

        # Create a socket
        sel = self.create_socket()

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
                            logger.info("Messsage recieved from client: %s" % msg)
                            # View function, action/camera_id, user_id
                            category, selection, current_user = msg.split('-')
                            if category == "view":
                                camera_status = self.check_if_camera_exists(selection)
                                if camera_status == False:
                                    self.add_new_stream(current_user, selection)
                                self.reset_active_camera_settings()
                                self.camera_queues[selection].put("activate")
                                message.close()
                            elif category == "manage":
                                if selection == "start":
                                    self.start_system(current_user)
                                    message.close()
                                elif selection == "stop":
                                    self.stop_system(current_user)
                                    self.update_system_status(0, current_user)
                                    message.close()
                        except Exception as e:
                            logger.error("Error in retrieving message for starting cameras due to: %s" % e)
                            message.close()
        except Exception as e:
            logger.error("Server main script failed due to: %s" % e)
        except KeyboardInterrupt:
            logger.error("Caught keyboard interrupt, exiting.")
        finally:
            sel.close()

    #-------------------------------------------------------------------------------
    def start_system(self, user_id):
        ''' When user presses the start button, start all cameras with status active'''

        # Import camera data
        user_camera_dict = self.import_user_camera_data([user_id])

        # Start cameras
        for camera_id in user_camera_dict[user_id]:
            self.add_new_stream(user_id, camera_id)

    #-------------------------------------------------------------------------------
    def stop_system(self, user_id):
        ''' When user presses the stop button, stop all cameras with status active'''

        # Import camera data
        user_camera_dict = self.import_user_camera_data([user_id])
        # Stop cameras
        for camera_id in user_camera_dict[user_id]:
            self.close_old_stream(camera_id)

    #-------------------------------------------------------------------------------
    def update_system_status(self, system_status, user_id):
        ''' Updating system status '''

        try:
            table = "app_dimperson"
            data = [("system_status", system_status)]
            where_statements = [("id", user_id)]
            MysqlConnection().update_data(table, data, where_statements)
            logger.info("System status was set to %s for user %s." % (system_status, user_id))
        except Exception as e:
            logger.error("Failed to update system status for user %s: %s" % (user_id, e))


if __name__ == '__main__':
    server = Server()
    server.run()
