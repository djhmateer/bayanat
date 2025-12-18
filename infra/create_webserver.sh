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

# I had to put in SECURE_COOKIES=False

export FLASK_APP=run.py
uv run flask create-db

# I had to specify the host as running on remote test server
# uv run flask run

# specify admin user
uv run flask run --host=0.0.0.0

# http://192.168.1.179:91/setup_wizard




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