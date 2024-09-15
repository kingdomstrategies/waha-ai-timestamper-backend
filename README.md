# TimestampAudio.com Backend by Waha

[TimeStampAudio.com](https://timestampaudio.com) generates timing data from any audio and corresponding text file combination, in the over [1,100 languages](https://dl.fbaipublicfiles.com/mms/misc/language_coverage_mms.html) supported by [Meta's MMS ASR model](https://ai.meta.com/blog/multilingual-model-speech-recognition/), outputting the results in JSON and SRT format.


This repo is for the backend of our [web app](https://timestampaudio.com) , which should be run on a GPU connected server, either local or cloud-based.


## Requirements:

The MMS models are quite GPU intensive, and so should be run on a GPU-attached server. We experimented with both [Google Compute](https://cloud.google.com/compute/docs/gpus) GPUs (Nvidia T4) and [LambaLabs](https://lambdalabs.com/) (Nvidia A10) GPU VPSs, with positive result.



## Installation:

These instructions will expect that the service will be running on a GPU-attached VPS, as described above (tested on Ubuntu 24.04 VPS). It also expects a level of competency in Linux server administration, and a subdomain with a DNS `A` record already pointing to the back-end VPS .


### VPS setup

First, install updates for the fresh Ubuntu VPS:

```sh
sudo apt-get update ; sudo apt-get upgrade 
```

\
Then, make sure that dependencies are installed:

```sh
sudo apt-get install ffmpeg sox nginx tmux certbot python3-certbot-nginx
```

\
Next, if your VPS doesn't come pre-installed with GPU drivers, you'll need to add those now. This will be dependent on your hardware. [This tutorial](https://www.cherryservers.com/blog/install-cuda-ubuntu) for Ubuntu 22.04 will point you in the right direction. 

\
After this, you'll want to setup your firewall. [This tutorial](https://www.digitalocean.com/community/tutorials/how-to-set-up-a-firewall-with-ufw-on-ubuntu) on `ufw` should get you most of the way. The API will need to run on SSL to avoid getting an `Access Control Check` error on the front end. Because of that, you'll want to use `sudo ufw allow "Nginx HTTPS"`, as well as making sure that `OpenSSH` is enabled. (Also, be sure that your VPS provider's firewall is allowing HTTPS traffic, as many don't by default.

\
At this point you'll want to set up Nginx. Add an Nginx conf file like below to your `/etc/nginx/sites-available/` directory. We called the file `api`.

```api`
server {
        server_name [YOUR_SERVER_SUBDOMAIN];

        location / {
                proxy_pass http://localhost:8000;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
        }
}
```

Then, symbolic link your available site to your enabled site, test the nginx config's syntax, and get Nginx running:

```
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl restart nginx
```

Then, [add an SSL certificate](https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-22-04) so we can get HTTPS:

```sh
 sudo certbot --nginx -d [YOUR_SERVERS_SUBDOMAIN]
```

At this point, we can enable the service.

#### Starting the Service


Start by cloning this repository to the VPS, and navigating to that directory:

```
git clone git@github.com:kingdomstrategies/waha-ai-timestamper-backend.git
cd waha-ai-timestamper-backend
```

At this point, you'll want to open a `tmux` session:

```
tmux
```

Then, set up a Python virtual environment and activate it.

```
python3 -m venv venv
source venv/bin/activate
```

Install your Python requirements:

```
python3 -m pip install -r requirements.txt
```

Then, set up a server with `gunicorn`:


```
gunicorn --workers 2 --bind 0.0.0.0:8000 main:app
```


You'll want to chose your number of `--workers` based off of the amount of vRAM your GPU has. For this service, you can run roughly _one worker per 3.6 GB of vRAM_ (so, we could safely run 6 `--workers` simultaneously on our 24 GB GPU).

Once you run the `gunicorn` command, you can disconnect from your `tmux` session by pressing `Ctrl+b`, and then `d`.


Your backend should now be set up!


