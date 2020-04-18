ARG TAG
FROM continuumio/miniconda3

USER root
RUN  apt-get update && apt install libgl1-mesa-glx --yes

# install packages for chromium
RUN apt-get update && \
    apt-get install -yq --no-install-recommends \
    libasound2 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 \
    libexpat1 libfontconfig1 libgcc1 libgconf-2-4 libgdk-pixbuf2.0-0 libglib2.0-0 libgtk-3-0 libnspr4 \
    libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 \
    libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 \
    libnss3

RUN mkdir /home/distributed
RUN mkdir /home/distributed/api

RUN conda update conda
RUN conda config --append channels conda-forge
RUN conda install "python>=3.7" pip

ADD https://raw.githubusercontent.com/compute-tooling/compute-studio/master/distributed/requirements.txt home/distributed

WORKDIR /home/distributed
# install packages here
# install packages necessary for celery, dask, and creating screenshots
RUN pip install -r requirements.txt
RUN conda install -c conda-forge lz4
RUN conda install -c conda-forge jinja2 pyppeteer && pyppeteer-install

ARG TITLE
ARG OWNER
ARG REPO_URL
ARG RAW_REPO_URL
ARG BRANCH=master

# Install necessary packages, copying files, etc.
######################
# Bump to trigger build
ARG BUILD_NUM=0

ADD ${RAW_REPO_URL}/${BRANCH}/cs-config/install.sh /home
RUN cat /home/install.sh
RUN bash /home/install.sh

# Bump to trigger re-install of source, without re-installing dependencies.
ARG INSTALL_NUM=0
RUN pip install "git+${REPO_URL}.git@${BRANCH}#egg=cs-config&subdirectory=cs-config"
ADD ${RAW_REPO_URL}/${BRANCH}/cs-config/cs_config/tests/test_functions.py /home
RUN pip install cs-kit
# RUN py.test /home/test_functions.py -v -s
######################

ARG SIM_TIME_LIMIT

# Just grab files from c/s repo for now
RUN mkdir /home/cs_workers
ADD cs_workers /home/cs_workers
ADD setup.py /home
RUN cd /home/ && pip install -e .

WORKDIR /home

COPY scripts/celery_sim.sh /home
COPY scripts/celery_io.sh /home

RUN conda install -c conda-forge "pyee<6"
