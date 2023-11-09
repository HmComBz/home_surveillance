import os
from cryptography.fernet import Fernet

# GLOBAL VARS
KEY = os.getenv('RTSP_ENCRYPT_KEY')

'''
    All this is based on a key that is stored as a environmental variable in windows.
    Needs to be set on each server.
'''

def encrypt(string):
    ''' Function for encrypting a message '''

    # Convert string to bytes and encrypt it
    new_string = string.encode()
    f = Fernet(KEY)
    return f.encrypt(new_string).decode("utf-8")


def decrypt(string):
    ''' Function for decrypting a message '''

    # Decrypt string
    new_string = string.encode()
    f = Fernet(KEY)
    return f.decrypt(new_string).decode("utf-8")
