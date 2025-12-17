#  DM created on 17th Dec 2025
# https://docs.bayanat.org/en/install

# there was duplicate python3-pip in the original list
# don't need python3.12

# don't see why I need venv etc and pip as will be using uv
# git is there too.
# TODO - do again (revert from backup).. after I get a working build first
sudo apt install \
    build-essential \
    python3.12-dev \
    python3.12-venv \
    python3-pip \
    libjpeg8-dev \
    libzip-dev \
    libxml2-dev \
    libssl-dev \
    libffi-dev \
    libxslt1-dev \
    libmysqlclient-dev \
    libncurses5-dev \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    git \
    libimage-exiftool-perl \
    postgis \
    ffmpeg \
    redis-server


# https://tesseract-ocr.github.io/tessdoc/Installation.html
sudo apt install tesseract-ocr -y

# english installed by default
# sudo apt install tesseract-ocr-eng -y
sudo apt install tesseract-ocr-ara -y

sudo apt install nginx -y

# create non privileged user to run bayanat
sudo useradd -m bayanat -s /bin/bash

# Next, Postgres user with the same name should be created, along with the bayanat database and relevant extensions on the database:
sudo -u postgres createuser -d bayanat
sudo -u bayanat createdb bayanat
sudo -u postgres psql -d bayanat -c 'CREATE EXTENSION if not exists pg_trgm; CREATE EXTENSION if not exists postgis;'


sudo mkdir /bayanat/
sudo chown bayanat:bayanat /bayanat/

# switch to non priv use bayanat to continue installation
sudo su -l bayanat


git clone https://github.com/sjacorg/bayanat.git /bayanat/

# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

source $HOME/.local/bin/env

cd /bayanat

# do I really need to do this? install perhaps better?
uv venv
uv sync

# big dependencies.. enable for voice transscipriotns through OpenAI Whisper and OCR though Google Tesseract
uv sync --extra ai

# configure bayanat system
# n - native install
# just creates .env file from .env-sample
./gen-env.sh


export FLASK_APP=run.py
uv run flask create-db


# I had to specify the host as running on remote test server
# uv run flask run

# specify admin user
uv run flask run --host=0.0.0.0

# http://192.168.1.179:91/setup_wizard