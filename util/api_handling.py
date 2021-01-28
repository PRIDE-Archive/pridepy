#!/usr/bin/env python

import requests
import logging
from ratelimit import limits, sleep_and_retry


class Util:
    """
    This class contains all the utility methods
    """

    @staticmethod
    @sleep_and_retry
    @limits(calls=1000, period=50)
    def get_api_call(url, headers):
        """
        Given a url, this method will do a HTTP request and get the response
        :param url:PRIDE API URL
        :param headers: HTTP headers
        :return: Response
        """
        response = requests.get(url, headers)

        if (not response.ok) or response.status_code != 200:
            raise Exception('PRIDE API response: {}'.format(response.status_code))
        return response

    @staticmethod
    def update_api_call(url, headers, data):
        """
        Given a url, this method will do a HTTP update
        :param data: data in json format
        :param url: PRIDE API URL
        :param headers: HTTP headers
        :return: Response
        """

        response = requests.put(url, data=data, headers=headers)

        if (not response.ok) or response.status_code != 200:
            raise Exception('PRIDE API response: {}'.format(response.status_code))
        else:
            logging.debug(response)
