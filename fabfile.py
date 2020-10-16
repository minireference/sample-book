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

from fabfiles.docker import dlocal, dlogs, dps, dshell, dexec, dsysprune
from fabfiles.docker import dclogs, dcbuild, dcup, dcdown
from fabfiles.docker import copy_local_dir_to_docker_host_dir
from fabfiles.docker import get_ebooks_from_docker_host_dir
from fabfiles.docker import install_docker, uninstall_docker



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

TexLine = namedtuple('TexLine', ['parent', 'relpath', 'texnode'])


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
    texlines = latexpand(sourcedir, mainfilename)
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
                if name_matches(nextline.texnode, ['label']):
                    chapter_dict['label'] = str(nextline.texnode.string)
                    break
            if chapter_dict['label'] is None:
                # fallback set label based on title
                chapter_dict['label'] = chapter_dict['title'].lower() \
                    .replace(' ', '_').replace(',', '_').replace('.', '_')
            current_chapters.append(chapter_dict)
            current_chapter = chapter_dict
        else:
            # filename extraction
            if current_chapter is None:
                print('skipping line ', str(texline.texnode)[0:30] + '...', 'in', relpath)
            elif relpath not in current_chapter['sourcefiles'] \
                and relpath not in ignore_relpaths \
                and texline.parent == mainfilename:  # only first-level inputs go into manifest
                current_chapter['sourcefiles'].append(relpath)
            elif texline.parent != mainfilename \
                and relpath != mainfilename \
                and relpath not in manifest['includes']:
                # found a new include file
                manifest['includes'].append(relpath)

            # other extractions
            if name_matches(texnode, ['includegraphics']):
                imagerelpath = process_includegraphics(sourcedir, texnode)
                manifest['graphics'].append(imagerelpath)
            elif texnode.find('includegraphics'):
                igs = texnode.find_all('includegraphics')
                for ig in igs:
                    imagerelpath = process_includegraphics(sourcedir, ig)
                    manifest['graphics'].append(imagerelpath)
            elif name_matches(texnode, EXERCISE_INCLUDES_LOOKUP.keys()):
                chN = str(texnode.string)
                filename = EXERCISE_INCLUDES_LOOKUP[texnode.name] + chN + '.tex'
                includerelpath =  os.path.join(EXERCISE_INCLUDES_DIR, filename)
                manifest['includes'].append(includerelpath)
            elif name_matches(texnode, ['input']):
                print('ERROR: there should not be any input commands in stream')
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







# UTILS FOR extractmanifest TASK
################################################################################

def name_matches(texnode, names):
    """
    Returns True if `texnode`'s name is on one of the names in `names`.
    """
    if hasattr(texnode, 'name') and texnode.name in names:
        return True
    else:
        return False


def latexpand(sourcedir, mainfilename):
    """
    Process the latex document `mainfilename` and expand `\input`s statements.
    Returns a list of `TexLine` named tuples that are used by `extractmanifest`.
    """

    def latexpand_recursive(doc, texlines, relpath, parentrelpath):
        """
        Recustively process the node `doc` append its lines to texlines (list).
        """
        for texnode in doc.children:
            if name_matches(texnode, ['input']):
                # A: regular includes
                childrelpath = str(texnode.string)
                if childrelpath in IGNORE_RELPATHS:
                    print("    Skipping input relpath", childrelpath)
                    continue
                print('  - reading', childrelpath)
                includepath = os.path.join(sourcedir, childrelpath)
                assert os.path.exists(includepath), 'missing input file ' + includepath
                childdoc = TexSoup.TexSoup(open(includepath).read(), skip_envs=('verbatimtab',))
                latexpand_recursive(childdoc, texlines, relpath=childrelpath, parentrelpath=relpath)
            elif texnode.find('input'):
                # B: deep includes: input statements in environment or BraceGroup
                texlines.append(TexLine(parentrelpath, relpath, texnode))
                inputs = texnode.find_all('input')
                for input in inputs:
                    childrelpath = str(input.string)
                    if childrelpath in IGNORE_RELPATHS:
                        print("    Skipping input relpath", childrelpath)
                    print('  - reading deep include', childrelpath)
                    includepath = os.path.join(sourcedir, childrelpath)
                    assert os.path.exists(includepath), 'missing deep input file ' + includepath
                    childdoc = TexSoup.TexSoup(open(includepath).read(), skip_envs=('verbatimtab',))
                    latexpand_recursive(childdoc, texlines, relpath=childrelpath, parentrelpath=relpath)
            else:
                #  C: regular non-include lines
                texlines.append(TexLine(parentrelpath, relpath, texnode))
        return texlines

    mainpath = os.path.join(sourcedir, mainfilename)
    print('reading ', mainfilename)
    soup = TexSoup.TexSoup(open(mainpath).read(), skip_envs=('verbatimtab',))
    doc = soup.document  # skip preamble
    texlines = []
    latexpand_recursive(doc, texlines, relpath=mainfilename, parentrelpath=None)
    return texlines


def process_includegraphics(sourcedir, includegraphics):
    """
    Extract the figure relpath and replace .pdf with .png version if available.
    """
    if isinstance(includegraphics.args[0], TexSoup.data.BraceGroup):
        imagerelpath = str(includegraphics.args[0].string)
    else:
        imagerelpath = str(includegraphics.args[1].string)
    if imagerelpath.endswith('.pdf'):
        imagerelpath_png = imagerelpath.replace('.pdf', '.png')
        if os.path.exists(os.path.join(sourcedir, imagerelpath_png)):
            imagerelpath = imagerelpath_png
    assert os.path.exists(os.path.join(sourcedir, imagerelpath)), 'no ' + imagerelpath
    return imagerelpath
