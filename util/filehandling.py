#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

"""
This script mainly holds files handing related methods
"""

def saveFile(out_filename, content):
    '''
    This method writes the content to the output file
    :param out_filename: full path of the output file
    :param content:
    :return:
    '''
    try:
        text_file = open(out_filename, "w")
        text_file.write(content)
        text_file.close()
    except FileNotFoundError as file_write_error:
        print(file_write_error)