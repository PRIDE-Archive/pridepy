#!/usr/bin/env python
import requests
from ratelimit import limits, sleep_and_retry

class APIUtil:
    """
    This class contains all the utility methods
    """
    @staticmethod
    @sleep_and_retry
    @limits(calls=1000, period=50)
    def call_api(url, headers):
        """
        Given a url, this method will do a HTTP request and get the renponse
        :param headers: HTTP headers
        :return: Response
        """
        response = requests.get(url)

        if (not response.ok) or response.status_code != 200:
            raise Exception('PRIDE API response: {}'.format(response.status_code))
        return response