############################################################
# Dockerfile to build python
# Version 1.0.0
# By: Suresh Hewapathirana
############################################################

# Base docker image with Ubuntu
FROM python:3

################## BEGIN INSTALLATION ######################

RUN apt-get update
RUN apt-get install -y build-essential wget
##################### INSTALLATION END #####################

COPY . /
RUN cd /

RUN pip install -r requirements.txt
ENV PATH=$PATH:/