import json
import pickle
import socket
from datetime import datetime as dt
import threading
from exceptions import *
import os
import sys


class Log(object):
    def __get_time(self):
        return dt.now().time().strftime("%H:%M:%S.%f")[:-3]

    def log(self, message):
        '''Logs normal messages like communications and such, adding the time at the beginning.'''
        sys.stdout.write("{time} - MESSAGE - {message}".format(
            time=self.__get_time(), message=message))

    def log_error(self, error):
        '''Logs error messages by adding the time.'''
        sys.stderr.write("{time} - ERROR - {error}".format(
            time=self.__get_time(), error=error))


class Connection(Log):
    def create(self):
        '''Returns a socket object.'''
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            self.log_error(
                "There was an error while creating the socket object.")
            return None
        else:
            self.log("Connection created successfully.\n")
            return sock

    def close_sock(self, sock):
        '''Closes a socket object. Return True if the operation was successfull, otherwise False.'''
        try:
            sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        except:
            self.log_error("Error while closing the session.")
            return False
        else:
            self.log("Session closed successfully.")
            return True


class ClientSession(Connection):
    def __init__(self, host, port, directory):
        '''Creates a Client Session. Client Sessions are used to receive the updated data.'''
        self.sock = self.create()
        if not isinstance(host, str) or not isinstance(port, int) or port <= 0:
            raise TypeError("Host or port have invalid values.")
        self.host, self.port, self.directory = host, port, directory

    def open(self):
        '''Connects to the host.'''
        try:
            self.sock.connect((self.host, self.port))
        except:
            raise ConnectionError("Connection to the host failed.")
        else:
            self.log("Connection created correctly.")

    def listen(self):
        '''Starts updating the data using a daemon thread. Can be stopped by calling the returned function.'''
        try:
            t = threading.Thread(target=self.__client, args=())
            t.daemon = True
            t.start()
        except:
            raise SessionError("Failed to start a thread.")
        return self.stop

    def stop(self):
        '''Stops updating the data and closes the thread.'''
        if not os.path.exists("data/communication.lf"):
            raise SessionError("Failed to locate the communication file.")
        with open("data/communication.lf", "wb") as f:
            pickle.dump({"active": False}, f)

    def __client(self):
        self.__check_dir()
        if not self.__conn_request():
            raise ConnectionError("Connection request rejected by the host.")
        while True:
            if self.__check_stop():
                self.log("Connection stopped.")
                break
            try:
                self.sock.send("req.active".encode())
                data = self.sock.recv(1024)
            except:
                raise ConnectionError("Communication with the server failed.")
            if not data:
                self.log_error("No data received. Stopping the connection.")
                break
            if data == "req.failed":
                self.log_error(
                    "Failed to retrieve data from the server. Stopping the connection")
                break
            with open(self.directory, "w") as f:
                json.dump(json.loads(data), f)

    def __conn_request(self):
        try:
            self.sock.send("req".encode())
        except:
            raise ConnectionError(
                "Failed to request the connection to the server.")
        try:
            if self.sock.recv(1024) == "y":
                return True
            else:
                return False
        except:
            raise ConnectionError(
                "Failed to receive response for the connection request. Defaulted to rejected")

    def __check_stop(self):
        if not os.path.exists("data/communication.lf"):
            raise SessionError("Failed to locate the communication file.")
        with open("data/communication.lf", "rb") as f:
            return not pickle.load(f)["active"]

    def __check_dir(self):
        if not os.path.exists(self.directory):
            raise SessionError("Target file doesn't exist.")
        if "data" not in os.listdir():
            os.mkdir("data")
        if not os.path.exists("data/communication.lf"):
            with open("data/communication.lf", "wb") as f:
                pickle.dump({"active": True}, f)

    def close(self):
        '''Closes the ClientSession object.'''
        try:
            self.close_sock(self.sock)
        except:
            raise SessionError("Failed to close the session.")


class ServerSession(Connection):
    def __init__(self):
        '''Creates a Server Session. Server Sessions are used to update the data and send it to the client.'''
        self.sock = self.create()
        self.bound = None

    def open(self, update_function, accept=True):
        '''Connects to the ports.'''
        if not callable(update_function):
            raise SessionError("Object passed is not callable.")
        try:
            self.sock.bind(("", 80))
            self.sock.listen(1)
        except:
            raise SessionError("Session opening operations failed.")
        self.update = update_function
        self.acc = accept

    def listen(self):
        '''Starts listening, updating and responding to a client.'''
        try:
            t = threading.Thread(target=self.__server, args=())
            t.daemon = True
            t.start()
        except:
            raise ConnectionError("Failed to start the thread.")
        return self.stop

    def stop(self):
        '''Stops the current exchange of data.'''
        with open("data/communication.lf", "wb") as f:
            pickle.dump({"active": False}, f)

    def __check_dir(self):
        if "data" not in os.listdir():
            os.mkdir("data")
        if not os.path.exists("data/communication.lf"):
            with open("data/communication.lf", "wb") as f:
                pickle.dump({"active": True}, f)

    def __check_stop(self):
        with open("data/communication.lf", "rb") as f:
            return not pickle.load(f)["active"]

    def __server(self):
        self.__check_dir()
        actions = {
            "req": self.__respond,
            "req.active": self.__request
        }
        while True:
            if self.__check_stop():
                self.log("Connection stopped.")
                break
            try:
                conn, addr = self.sock.accept()
                if not self.bound:
                    self.bound = addr
                else:
                    if addr != self.bound:
                        self.log("Request received from other client.")
                        continue
                self.log("Request received from '{}'".format(str(addr)))
                data = conn.recv(1024).decode()
            except:
                raise ConnectionError("Failed to received data.")
            if data is None or data not in actions.keys():
                self.log("SESSION PAUSED.")
                break
            try:
                actions[data](conn)
            except:
                raise ConnectionError("Failed to respond to the request.")
        self.bound = None

    def __respond(self, conn):
        self.log("Request Type : connection")
        try:
            conn.send("y".encode() if self.acc else "n".encode())
            self.log("Responded correctly to connection request.")
        except:
            self.log_error("Failed to send response to connection request.")

    def __request(self, conn):
        self.log("Request Type : data")
        try:
            req = self.update()
        except:
            self.log_error("Failed to update data.")
            try:
                conn.send("req.failed".encode())
            except:
                raise ConnectionError(
                    "Failed to send 'Failed update' response.")
            else:
                self.log("'Failed update' communication sent correctly.")
        else:
            self.log("Data updated correctly.")
            try:
                conn.send(json.dumps(req))
            except:
                raise ConnectionError(
                    "Failed to send 'Completed update' response.")
            else:
                self.log("'Completed update' response sent correctly.")

    def close(self):
        '''Closes the session.'''
        self.close_sock(self.sock)
