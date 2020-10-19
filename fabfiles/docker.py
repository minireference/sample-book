import os
import yaml

from fabric.api import env, task, local, sudo, run, settings
from fabric.api import get, put, require
from fabric.colors import red, green, blue, yellow
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.contrib.files import exists, sed, upload_template
from fabric.utils import puts



# PROVISION DOCKER ON REMOTE HOST
################################################################################

@task
def install_docker():
    """
    Install docker on remote host following the instructions from the docs:
    https://docs.docker.com/engine/install/debian/#install-using-the-repository
    """
    with settings(warn_only=True), hide('stdout', 'stderr', 'warnings'):
        sudo('apt-get -qy remove docker docker-engine docker.io containerd runc')
    with hide('stdout'):
        sudo('apt-get update -qq')
        sudo('apt-get -qy install apt-transport-https ca-certificates curl gnupg-agent software-properties-common')
    sudo('curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -')
    sudo('add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable"')
    with hide('stdout'):
        sudo('apt-get update -qq')
        sudo('apt-get -qy install docker-ce docker-ce-cli containerd.io')
    sudo('usermod -aG docker {}'.foramt(env.user))  # add user to `docker` group
    # docker-compose opens >10 SSH sessions, hence we need to up default value
    # via https://github.com/docker/compose/issues/6463#issuecomment-458607840
    sudo("sed -i 's/^#MaxSessions 10/MaxSessions 30/' /etc/ssh/sshd_config")
    sudo('service sshd restart')
    print(green('Docker installed on ' + env.host))


@task
def uninstall_docker(deep=False):
    """
    Uninstall docker using instructions from the official Docker docs:
    https://docs.docker.com/engine/install/debian/#uninstall-docker-engine
    """
    deep = (deep and deep.lower() == 'true')  # defaults to False
    with hide('stdout'):
        sudo('apt-get -qy purge docker-ce docker-ce-cli containerd.io')
        if deep:
            sudo('rm -rf /var/lib/docker')
            sudo('rm -rf /var/lib/containerd')
    print(green('Docker uninstalled from ' + env.host))




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
EXCLUDE_DIRS = ['venv', 'venv2', 'Code', 'fabfile.py', '.git', '.DS_Store']

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
    local('COPYFILE_DISABLE=true tar {} -czf {} .'.format(exclude_str, archivelocalpath))
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

