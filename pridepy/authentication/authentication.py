#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import sys
import requests


class Authentication:
    """
    This class holds authentication related methods including issuing and validating access token.
    """

    base_url = "https://www.ebi.ac.uk/pride/private/ws/archive/v2"

    def __init__(self):
        pass

    def get_token(self, username, password):
        """
        Get the PRIDE API token from EBI to access resources
        :param username: username (email)
        :param password: password
        :return: If authenticated, a token is returned
        """

        # get token to access the api
        url = self.base_url + "/login"
        headers = {"Content-type": "application/json", "Accept": "text/plain"}
        credentials = (
            '{"Credentials":{"username":"'
            + username
            + '", "password":"'
            + password
            + '"}}'
        )

        response = requests.post(url, data=credentials, headers=headers)

        if (not response.ok) or response.status_code != 200:
            logging.error("Failed to get the token for user {}".format(username))
            response.raise_for_status()
            sys.exit()
        else:
            token = response.text
        return token

    def validate_token(self, token):
        """
        Check if the token is valid and not expired
        :param token: Token
        :return: Return True if the token is valid and not expired: Otherwise returns False
        """
        url = self.base_url + "/token-validation"
        headers = {"Authorization": "Bearer " + token}

        response = requests.post(url, headers=headers)

        return (
            response.ok
            and response.status_code == 200
            and response.text == "Token Valid"
        )
