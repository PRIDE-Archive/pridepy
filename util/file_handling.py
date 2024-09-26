#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging


class FileHanding:
    """
    This script mainly holds files handing related methods
    """

    @staticmethod
    def save_file(out_filename, content):
        """
        This method writes the content to the output file
        :param out_filename: full path of the output file
        :param content:
        :return:
        """

        try:
            text_file = open(out_filename, "w")
            text_file.write(content)
            text_file.close()
        except FileNotFoundError as file_write_error:
            logging.error(file_write_error)

    def wrap_with_ms_run_metadata(self, filename):
        """
        This wraps the JSON object with the MSRunMetadata wrapper to make the JSON object compatible with the PRIDE API
        :param filename:
        :return:
        """
        self.line_prepender(filename, '{"MSRunMetadata":')
        self.line_postpender(filename, "}")

    @staticmethod
    def line_prepender(filename, prefix):
        """
        This method adds a prefix to the beginning of the file
        :param filename: Filename
        :param prefix: The prefix content that needs to be added
        :return:
        """
        try:
            with open(filename, "r+") as editing_file:
                content = editing_file.read()
                editing_file.seek(0, 0)
                editing_file.write(prefix.rstrip("\r\n") + content)
        except FileNotFoundError as file_write_error:
            logging.error(file_write_error)

    @staticmethod
    def line_postpender(filename, sufix):
        """
        This method adds a sufix to the end of the file
        :param filename: Filename
        :param sufix: The sufix content that needs to be added
        :return:
        """
        try:
            with open(filename, "a") as editing_file:
                editing_file.write(sufix)
        except FileNotFoundError as file_write_error:
            logging.error(file_write_error)
