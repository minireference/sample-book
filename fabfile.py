"""
Automation scripts for exporting, processing, and building ePub from tex source.
"""
from collections import defaultdict
import json
import os
import time
import yaml

from fabric.api import env, task, local, sudo, run, settings
from fabric.api import get, put, require
from fabric.colors import red, green, blue, yellow
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.contrib.files import exists, sed, upload_template
from fabric.utils import puts


# DOCKER HOST
################################################################################
env.hosts = ['192.168.0.105']
env.user = 'ivan'
env.password = os.environ.get('SUDO_PASSWORD')
env.DOCKER_HOST = "ssh://ivan@192.168.0.105"


# SOFTCOVER INSIDE DOCKER COMMANDS
################################################################################
DOCKER_IMAGE_NAME = 'softcover-docker'

@task
def dbuildimage():
    dlocal('docker build -t {} .'.format(DOCKER_IMAGE_NAME))

@task
def dbuild(format=None):
    if format is None:
        format = 'all'
    if 'DOCKER_HOST' in env:
        # we need to transfer contents of current directory to docker host
        remote_host_path = copy_local_dir_to_docker_host_dir('.')
        host_path = remote_host_path
    else:
        host_path = os.path.abspath(os.path.curdir)
    cmd = 'docker run -v {host_path}:/book {image} sc build:{format}'.format(
        host_path=host_path, image=DOCKER_IMAGE_NAME, format=format)
    dlocal(cmd)
    print(green('Build successful'))
    if 'DOCKER_HOST' in env:
        get_ebooks_from_docker_host_dir(remote_host_path, format)
        print(green('Book(s) in format ' + format + ' pulled to local dir.'))

@task
def dserver():
    cwd = os.path.abspath(os.path.curdir)
    cmd = 'docker run -v {cwd}:/book -p 4000:4000 {image} sc server'.format(
        cwd=cwd, image=DOCKER_IMAGE_NAME)
    dlocal(cmd)




# FWD DOCKER COMMANDS TO REMOTE HOST
################################################################################

@task
def dlocal(command):
    """
    Execute the `command` (srt) on the remote docker host `env.DOCKER_HOST`.
    If `env.DOCKER_HOST` is not defined, execute `command` on the local docker.
    Docker remote execution via SSH requires remote host to run docker v18+.
    """
    if 'DOCKER_HOST' in env:
        with shell_env(DOCKER_HOST=env.DOCKER_HOST):
            local(command)  # this will run the command on remote docker host
    else:
        local(command)      # this will use local docker (if installed)



# DOCKER COMMANDS
################################################################################

@task
def dlogs(container, options=''):
    cmd = 'docker logs '
    cmd += options
    cmd += ' {}'.format(container)
    dlocal(cmd)

@task
def dps(options=''):
    cmd = 'docker ps '
    cmd += options
    dlocal(cmd)

@task
def dshell(container):
    cmd = 'docker exec -ti {} /bin/bash'.format(container)
    dlocal(cmd)

@task
def dexec(container, command, options='-ti'):
    cmd = 'docker exec '
    cmd += options
    cmd += ' {} bash -c \'{}\''.format(container, command)
    dlocal(cmd)

@task
def dsysprune(options=''):
    cmd = 'docker system prune -f '
    cmd += options
    dlocal(cmd)



# DOCKER COMPOSE COMMANDS
################################################################################

@task
def dclogs(options=''):
    cmd = 'docker-compose logs '
    cmd += options
    dlocal(cmd)

@task
def dcbuild(service='', options=''):
    cmd = 'docker-compose build '
    cmd += options
    cmd += '  ' + service
    dlocal(cmd)

@task
def dcup(options='-d'):
    cmd = 'docker-compose up '
    cmd += options
    dlocal(cmd)

@task
def dcdown(options=''):
    cmd = 'docker-compose down '
    cmd += options
    dlocal(cmd)


# DOCKER HOST VOLUME HELPERS
################################################################################

DOCKER_HOST_VOLUMES_BASE_DIR = '/storage/volumes'
EXCLUDE_DIRS = ['venv', 'Code', 'fabfile.py', '.git', '.DS_Store']

@task
def copy_local_dir_to_docker_host_dir(localpath):
    """
    Transfer contents of local dir to the remote docker host under `/volumes`.
    """
    realpath = os.path.realpath(localpath)
    dirname = os.path.split(realpath)[1]
    archivename = dirname + '.tgz'
    # cleanup
    archivelocalpath = os.path.join('/tmp', archivename)
    if os.path.exists(archivelocalpath):
        os.remove(archivelocalpath)
    if not exists(DOCKER_HOST_VOLUMES_BASE_DIR):
        sudo('mkdir -p ' + DOCKER_HOST_VOLUMES_BASE_DIR)
        sudo('chmod go+rwx ' + DOCKER_HOST_VOLUMES_BASE_DIR)
    archiveremotepath = os.path.join(DOCKER_HOST_VOLUMES_BASE_DIR, archivename)
    if exists(archiveremotepath):
        sudo('rm -f ' + archiveremotepath)
    remotepath = os.path.join(DOCKER_HOST_VOLUMES_BASE_DIR, dirname)
    if exists(remotepath):
        sudo('rm -rf ' + remotepath)
    # local archive...
    exclude_str = ''
    for exlcude_dir in EXCLUDE_DIRS:
        exclude_str += " --exclude='{}'".format(exlcude_dir)
    local('tar {} -czf {} .'.format(exclude_str, archivelocalpath))
    put(archivelocalpath, archiveremotepath)
    local('rm ' + archivelocalpath)
    # ...and remote unarchive
    with cd(DOCKER_HOST_VOLUMES_BASE_DIR):
        run('mkdir ' + dirname)
        run('tar -xzf {} -C {}'.format(archiveremotepath, dirname))
        run('rm ' + archiveremotepath)
    assert exists(remotepath)
    print(green('Local dir ' + localpath + ' copied to ' + remotepath + ' on host.'))
    return remotepath


@task
def get_ebooks_from_docker_host_dir(remotepath, format):
    """
    Transfer contents of local dir to the remote docker host under `/volumes`.
    """
    book_info = yaml.safe_load(open(os.path.join('config', 'book.yml')))
    filename = book_info['filename']

    if format == 'all':
        formats = ['epub', 'mobi', 'pdf', 'html']
    else:
        formats = [format]

    for format in formats:
        if format == 'html':
            remotehtmldirpath = os.path.join(remotepath, 'html/*')
            get(remotehtmldirpath, 'html/')
        else:
            remotefilepath = os.path.join(remotepath, 'ebooks', filename + '.' + format)
            localfilepath = os.path.join('ebooks', filename + '.' + format)
            get(remotefilepath, localfilepath)

