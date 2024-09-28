#!/usr/bin/env python

import requests
import logging
from ratelimit import limits, sleep_and_retry
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Util:
    """
    This class contains all the utility methods
    """

    @staticmethod
    @sleep_and_retry
    @limits(calls=1000, period=50)
    def get_api_call(url, headers=None):
        """
        Given a url, this method will do a HTTP request and get the response
        :param url:PRIDE API URL
        :param headers: HTTP headers
        :return: Response
        """
        response = requests.get(url, headers=headers)

        if (not response.ok) or response.status_code != 200:
            raise Exception("PRIDE API call {} response: {}".format(url, response.status_code))
        return response

    @staticmethod
    @sleep_and_retry
    @limits(calls=1000, period=50)
    def post_api_call(url, headers=None, data=None):
        """
        Given a url, this method will do a HTTP request and get the response
        :param url:PRIDE API URL
        :param headers: HTTP headers
        :param data: HTTP data
        :return: Response
        """

        response = requests.post(url, headers=headers, json=data)

        if (not response.ok) or response.status_code != 200:
            raise Exception("PRIDE API response: {}".format(response.status_code))
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
            raise Exception("PRIDE API response: {}".format(response.status_code))
        else:
            logging.debug(response)

    @staticmethod
    def create_session_with_retries():
        session = requests.Session()
        retry_strategy = Retry(
            total=5,  # Retry up to 5 times
            backoff_factor=2,  # Exponential backoff: wait 2^i seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP codes
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
