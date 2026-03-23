#  DM created on 17th Dec 2025 and updated on 12th March 2026
# https://docs.bayanat.org/deployment/installation.html

# there was duplicate python3-pip in the original list
# don't need python3.12

# don't see why I need venv etc and pip as will be using uv
# git is there too.
# sudo apt install \
#     build-essential \
#     python3.12-dev \
#     python3.12-venv \
#     python3-pip \
#     libjpeg8-dev \
#     libzip-dev \
#     libxml2-dev \
#     libssl-dev \
#     libffi-dev \
#     libxslt1-dev \
#     libmysqlclient-dev \
#     libncurses5-dev \
#     postgresql \
#     postgresql-contrib \
#     libpq-dev \
#     git \
#     libimage-exiftool-perl \
#     postgis \
#     ffmpeg \
#     redis-server

sudo apt install -y python3-dev libpq-dev redis-server postgresql postgresql-contrib postgis libgdal-dev uwsgi libimage-exiftool-perl


# https://tesseract-ocr.github.io/tessdoc/Installation.html
sudo apt install tesseract-ocr -y

# english installed by default
# sudo apt install tesseract-ocr-eng -y
# arabic I think
# sudo apt install tesseract-ocr-ara -y

sudo apt install nginx -y

# create non privileged user to run bayanat
# sudo useradd -m bayanat -s /bin/bash

# create system user without a password login ie cannot login using a password
# common for running services
sudo adduser --disabled-password bayanat


# Next, Postgres user with the same name should be created, along with the bayanat database and relevant extensions on the database:
sudo -u postgres createuser -d bayanat
# create db and assign ownership
sudo -u postgres createdb -O bayanat bayanat

sudo -u postgres psql -d bayanat -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d bayanat -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# DEV DB
PGPASSWORD='password' psql -U bob
CREATE DATABASE bayanat;
# connect to bayanat db
\c bayanat
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
# END DEV DB

sudo mkdir /bayanat/
sudo chown bayanat:bayanat /bayanat

# exiftool needed before uv sync (pyexifinfo checks for it during build)
sudo apt-get install -y libimage-exiftool-perl

sudo -u bayanat -i
cd /bayanat
# git clone https://github.com/sjacorg/bayanat.git /bayanat/
git clone https://github.com/djhmateer/bayanat.git /bayanat/

# install uv.. 
# same command to update
# 0.10.11 on 17th Mar 2026
curl -LsSf https://astral.sh/uv/install.sh | sh

source $HOME/.local/bin/env

cd /bayanat

uv sync

# big dependencies ie a few GB.. enable for voice transcriptions through OpenAI Whisper and OCR though Google Tesseract
uv sync --extra ai

# configure bayanat system
# n - native install
# just creates .env file from .env-sample
bash gen-env.sh

#DEV
POSTGRES_USER=bob
POSTGRES_PASSWORD=password 
#END DEV

uv run flask create-db  

# creates admin user - can just do this in flask run next
# uv run flask install

# DEV
config.json - web setup to false
# spins up on http://127.0.0.1:5000
uv run flask run

uv run python sample_data/sample_data_minimal_reset.py    
# END DEV

# I had to put in SECURE_COOKIES=False into the .env so didn't get error about csrf tokens not matching

# as running on remote server had to do this rather than 127.0.0.1
# remember to be as user bayanat if not already
sudo -u bayanat -i
uv run flask run --host=0.0.0.0

# http://192.168.1.179:91/setup_wizard

## DELETE DB and start again
# logged in as dave
sudo -u postgres psql -c "DROP DATABASE bayanat;"
sudo -u postgres createdb -O bayanat bayanat
sudo -u postgres psql -d bayanat -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d bayanat -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

sudo -u bayanat -i 
uv run flask create-db

# do I need this? does setup_wizard do it?
# uv run flask import-data

# just creates an admin user
# admin, zp..22!!
# uv run flask install

# setup_complete to false
vim config.json

sudo -u bayanat -i 
cd /bayanat
uv run flask run --host=0.0.0.0



## run as a service
sudo vim /etc/systemd/system/bayanat.service

[Unit]
Description=UWSGI instance to serve Bayanat
After=syslog.target
[Service]
User=bayanat
Group=bayanat
WorkingDirectory=/bayanat
EnvironmentFile=/bayanat/.env
ExecStart=/bayanat/.venv/bin/uwsgi --ini uwsgi.ini
Restart=always
KillSignal=SIGQUIT
Type=notify
StandardError=syslog
NotifyAccess=all
[Install]
WantedBy=multi-user.target


# there is a uwsgi.ini file in the bayanat directory already
# had to change to 0.0.0.0 from 127.0.0.1 to access from test server
sudo systemctl enable --now bayanat.service
sudo systemctl disable bayanat.service
sudo systemctl status bayanat.service


## nginx
## don't need this on test server but try anyway!
# have put this on my main reverse proxy
sudo vim /etc/nginx/conf.d/bayanat.conf

server {
    listen 80;
    server_name example.com;
    client_max_body_size 100M;
    root /bayanat;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location /static {
        alias /bayanat/enferno/static;
        expires max;
    }

    # deny access to git and dot files
    location ~ /\. {
        deny all;
        return 404;
    }

    # deny direct access to script and sensitive files
    location ~* \.(pl|cgi|py|sh|lua|log|md5)$ {
        return 444;
    }

    location / {
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        proxy_set_header X-Forward-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_buffering off;
        proxy_pass http://127.0.0.1:5000;
    }
}

sudo systemctl enable --now nginx.service

## celery
# this is a distributed task queue to handle background tasks outside of the main web reqeest and to run scheduled jobs
# minimum of 2 workers and max of 5
# potential problem with -B option to run beat scheduler in same process as worker (risk of dupe jobs)
sudo vim /etc/systemd/system/bayanat-celery.service

[Unit]
Description=Bayanat Celery Service
After=network.target
[Service]
User=bayanat
Group=bayanat
WorkingDirectory=/bayanat
Environment="PATH=/bayanat/.venv/bin:/usr/bin"
EnvironmentFile=/bayanat/.env
ExecStart=/bayanat/.venv/bin/celery  -A enferno.tasks worker --autoscale 2,5 -B
[Install]
WantedBy=multi-user.target

sudo systemctl enable --now bayanat-celery.service


## TO RECREATE
# as user dave or a priv user

# Drop and recreate the database
sudo -u bayanat dropdb bayanat
sudo -u bayanat createdb bayanat
sudo -u postgres psql -d bayanat -c 'CREATE EXTENSION if not exists pg_trgm; CREATE EXTENSION if not exists postgis;'

# switch to bayanat user
sudo su -l bayanat

# recreate the db
export FLASK_APP=run.py
uv run flask create-db

# step4 - do it manually
uv run flask import-data