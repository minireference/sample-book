"""
Automation scripts for extract, pre-process, and building ePub from tex sources.
"""
from collections import defaultdict, namedtuple
import json
import os

from more_itertools import peekable
import TexSoup
import yaml

from fabric.api import env, task, local, sudo, run, settings
from fabric.api import get, put, require
from fabric.colors import red, green, blue, yellow
from fabric.context_managers import cd, prefix, show, hide, shell_env
from fabric.contrib.files import exists, sed, upload_template
from fabric.utils import puts


# DOCKER HOST INFO
################################################################################
env.hosts = ['192.168.0.105']
env.user = 'ivan'
env.password = os.environ.get('SUDO_PASSWORD')
env.DOCKER_HOST = "ssh://ivan@192.168.0.105"




# LATEX SOURCE PRE-PROCESSING
################################################################################
IGNORE_RELPATHS = ['00_frontmatter/copyright.tex', 'index/allsees.tex']
END_MATTER_STARTS = ['End matter', 'Conclusion']
CHAPTER_COMMAND_NAMES = ['chapter', 'softchapter', 'mycenteredheading']
EXERCISE_INCLUDES_DIR = '99anssol'
EXERCISE_INCLUDES_LOOKUP = {
    'showExerciseAnswers': 'eanswers_',
    'showExerciseSolutions': 'esolutions_',
    'showProblemAnswers': 'answers_',
    'showProblemSolutions': 'solutions_',
}

TexLine = namedtuple('TexLine', ['relpath', 'texnode'])


def latexpandonce(sourcedir, mainfilename):
    """
    Process the latex document `mainfilename` and expand one level of `\input`s.
    Returns a list of `TexLine` named tuples that are used by `extractmanifest`.
    """
    mainpath = os.path.join(sourcedir, mainfilename)
    print('reading ', mainfilename)
    soup = TexSoup.TexSoup(open(mainpath).read(), skip_envs=('verbatimtab',))
    doc = soup.document  # skip preamble
    texlines = []
    for texnode in doc.children:
        if hasattr(texnode, 'name') and texnode.name == 'input':
            # try:
                # an include of another file
                relpath = str(texnode.string)
                print('  - reading', relpath)
                includepath = os.path.join(sourcedir, relpath)
                assert os.path.exists(includepath), 'missing input file ' + includepath
                subsoup = TexSoup.TexSoup(open(includepath).read(), skip_envs=('verbatimtab',))
                for subtexnode in subsoup.children:
                    texlines.append(TexLine(relpath, subtexnode))
            # except (TypeError, EOFError) as e:
            #     print(e)
        else:
            # non-include line
            texlines.append(TexLine(mainfilename, texnode))
    return texlines

def name_matches(texnode, names):
    """
    Returns True if `texnode`'s name is on one of the names in `names`.
    """
    if hasattr(texnode, 'name') and texnode.name in names:
        return True
    else:
        return False

@task
def extractmanifest(mainpath):
    """
    Extract the book manifest YAML from the LaTex source file at `mainpath` and
    save it to `config/manifest.yml` for further processing and fine tuning.
    """
    sourcedir, mainfilename = os.path.split(mainpath)
    manifest = {
        'sourcedir': sourcedir,
        'frontmatter': {'chapters': []},
        'mainmatter': {'chapters': []},
        'backmatter': {'chapters': []},
        'includes': [],
        'graphics': []
    }
    ignore_relpaths = IGNORE_RELPATHS + [mainfilename]

    # starting with frontmatter...
    current_chapters = manifest['frontmatter']['chapters']
    current_chapter = None
    texlines = latexpandonce(sourcedir, mainfilename)
    peekable_texlines = peekable(texlines)
    for texline in peekable_texlines:
        relpath = texline.relpath
        texnode = texline.texnode
        if hasattr(texnode, 'name') and texnode.name == 'mainmatter':
            # switch to mainmatter
            current_chapters = manifest['mainmatter']['chapters']
            current_chapter = None
        if name_matches(texnode, CHAPTER_COMMAND_NAMES) and str(texnode.string) in END_MATTER_STARTS:
            # switch to backmatter
            current_chapters = manifest['backmatter']['chapters']
            current_chapter = None
        if name_matches(texnode, CHAPTER_COMMAND_NAMES):
            chapter_dict = {
                'title': str(texnode.string),
                'label': None,
                'sourcefiles': [relpath],
            }
            # Look ahead to check if there is a \label command
            nextlines = peekable_texlines[0:2]
            for nextline in nextlines:
                if hasattr(nextline, 'name') and nextline.name == 'label':
                    chapter_dict['label'] = str(nextline.string)
                    break
            if chapter_dict['label'] is None:
                chapter_dict['label'] = chapter_dict['title'].replace(' ', '_') \
                    .replace(',', '_').replace('.', '_')
            current_chapters.append(chapter_dict)
            current_chapter = chapter_dict
        else:
            # filename extraction
            if current_chapter is None and relpath not in ignore_relpaths:
                print('skipping line ', str(texline.texnode)[0:30] + '...', 'in', relpath)
            elif relpath not in current_chapter['sourcefiles'] and relpath not in ignore_relpaths:
                current_chapter['sourcefiles'].append(relpath)
            #
            # other extractions
            if name_matches(texnode, ['includegraphics']):
                manifest['graphics'].append(str(texnode.includegraphics.string))
            elif name_matches(texnode, ['figure', 'exercise', 'problem']):
                ig = texnode.find('includegraphics')
                if isinstance(ig.args[0], TexSoup.data.BraceGroup):
                    imagerelpath = ig.args[0].string
                else:
                    imagerelpath = ig.args[1].string
                manifest['graphics'].append(str(imagerelpath))
            elif name_matches(texnode, ['input']):
                manifest['includes'].append(str(texnode.string))
            elif name_matches(texnode, EXERCISE_INCLUDES_LOOKUP.keys()):
                chN = str(texnode.string)
                filename = EXERCISE_INCLUDES_LOOKUP[texnode.name] + chN + '.tex'
                includerelpath =  os.path.join(EXERCISE_INCLUDES_DIR, filename)
                manifest['includes'].append(includerelpath)
    # save
    manifest_str = yaml.dump(manifest, default_flow_style=False, sort_keys=False)
    # print(manifest_str)
    with open('config/manifest.yml', 'w') as yamlfile:
        yamlfile.write(manifest_str)
    puts(green('Manifest saved to config/manifest.yml; plz inspect and edit.'))
    return manifest



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

