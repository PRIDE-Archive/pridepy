#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import requests

"""
This script mainly holds authentication related methods
"""

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

def getToken(username, password):
    """
    Get AAP token from EBI USI to access resources
    :param username: username (email)
    :param password: password
    :return: If authenticated, a token is returned
    """
    token = ""

    # get token to access the api
    url = base_url + "getAAPToken?username=" + username + "&password=" + password
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

    response = requests.post(url, headers=headers)

    if (not response.ok) or response.status_code != 200:
        response.raise_for_status()
        sys.exit()
    else:
        token = response.text
    return token

def validateToken(token):
    '''
    Check if the token is valid and not expired
    :param token: Token
    :return: Return True if the token is valid and not expired: Otherwise returns False
    '''
    url = base_url + "tokentest"
    headers = {'Authorization': 'Bearer ' + token}

    response = requests.post(url, headers=headers)

    return response.ok and response.status_code == 200 and response.text == 'Token Valid'
