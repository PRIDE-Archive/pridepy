#!/usr/bin/env python
import re
import sys

import httpx
import requests
import logging
from ratelimit import limits, sleep_and_retry
from requests.adapters import HTTPAdapter
from tqdm import tqdm
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
            raise Exception(
                "PRIDE API call {} response: {}".format(url, response.status_code)
            )
        return response

    @staticmethod
    @sleep_and_retry
    @limits(calls=1000, period=50)
    async def stream_response_to_file(out_file, total_records, regex_search_pattern, url, headers=None):
        # Initialize the progress bar
        with tqdm(total=total_records, unit_scale=True) as pbar:
            async with httpx.AsyncClient() as client:
                # Use a GET request with stream=True to handle streaming responses
                async with client.stream("GET", url, headers=headers) as response:
                    # Check if the response is successful
                    response.raise_for_status()
                    try:
                        with open(out_file, 'w') as cfile:
                            # Iterate over the streaming content line by line
                            async for line in response.aiter_lines():
                                if line:  # Avoid printing empty lines (common with text/event-stream)
                                    cfile.write(line + "\n")
                                    # Check if the pattern exists in the string
                                    if re.search(regex_search_pattern, line):
                                        pbar.update(1)  # Update progress bar by 1 for each detection
                    except PermissionError as e:
                        print("[ERROR] No permissions to write to:", out_file)
                        sys.exit(1)

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
