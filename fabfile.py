"""
Automation scripts for extract, pre-process, and building ePub from tex sources.
"""
from collections import defaultdict, namedtuple
import copy
from datetime import datetime
import json
import os
import re

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
SOURCE_MANIFEST = 'config/manifest.yml'
EXTRACTED_MANIFEST = 'sources/extracted/manifest.yml'
TRANSFROMED_MANIFEST = 'sources/transformed/manifest.yml'




# EXTRACT
################################################################################

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

            # graphics
            if name_matches(texnode, ['includegraphics']):
                imagerelpath = process_includegraphics(sourcedir, texnode)
                manifest['graphics'].append(imagerelpath)
            elif texnode.find('includegraphics'):
                igs = texnode.find_all('includegraphics')
                for ig in igs:
                    imagerelpath = process_includegraphics(sourcedir, ig)
                    if imagerelpath not in manifest['graphics']:
                        manifest['graphics'].append(imagerelpath)

            # exercie and problem solution streams
            if name_matches(texnode, EXERCISE_INCLUDES_LOOKUP.keys()):
                chN = str(texnode.string)
                filename = EXERCISE_INCLUDES_LOOKUP[texnode.name] + chN + '.tex'
                includerelpath =  os.path.join(EXERCISE_INCLUDES_DIR, filename)
                manifest['includes'].append(includerelpath)
            elif contains_names(texnode, EXERCISE_INCLUDES_LOOKUP.keys()):
                for includename in EXERCISE_INCLUDES_LOOKUP.keys():
                    includenodes = texnode.find_all(includename)
                    for includenode in includenodes:
                        chN = str(includenode.string)
                        filename = EXERCISE_INCLUDES_LOOKUP[includenode.name] + chN + '.tex'
                        includerelpath =  os.path.join(EXERCISE_INCLUDES_DIR, filename)
                        manifest['includes'].append(includerelpath)

            # Sanity check
            if name_matches(texnode, ['input']):
                print('ERROR: there should not be any input commands in stream')
    # save
    manifest_str = yaml.dump(manifest, default_flow_style=False, sort_keys=False)
    # print(manifest_str)
    with open(SOURCE_MANIFEST, 'w') as yamlfile:
        yamlfile.write(manifest_str)
    puts(green('Manifest saved to config/manifest.yml; plz inspect and edit.'))
    return manifest


@task
def extract(manifest=SOURCE_MANIFEST):
    """
    Read the source `manifest` and copy all the source files to `extracted/`.
    The `sourcefiles` for each chapter are combiend to form single-file chapters.
    """
    manifest = yaml.safe_load(open(manifest))
    sourcedir = manifest['sourcedir']
    destdir = os.path.join('sources', 'extracted')
    local('rm -rf ' + destdir)
    if not os.path.exists(destdir):
        os.makedirs(destdir, exist_ok=True)
    allsourcefiles_set = set()

    def combine_chapters(sourcedir, chapters, destdir, prefix=''):
        newchapters = []
        for i, chapter in enumerate(chapters):
            newchapter = {'title': chapter['title'], 'label': chapter['label']}
            chnum = '{:02d}'.format(i+1)
            label = chapter['label']
            cleanlabel = label.split(':')[1] if ':' in label else label
            chapterfilename = prefix + chnum + '_' + cleanlabel + '.tex'
            chapterpath = os.path.join(destdir, chapterfilename)
            with open(chapterpath, 'w') as chf:
                for sourcefile in chapter['sourcefiles']:
                    sourcepath = os.path.join(sourcedir, sourcefile)
                    with open(sourcepath) as srcf:
                        sourcetext = srcf.read()
                    chf.write(sourcetext)
                    # duplicate checks
                    if sourcefile in allsourcefiles_set:
                        puts(red('ERROR: sourcefile ' + sourcefile + ' multiply included'))
                    allsourcefiles_set.add(sourcefile)
            newchapter['sourcefiles'] = [chapterfilename]
            newchapters.append(newchapter)
        return newchapters

    extractedmanifest = {
        'sourcedir': destdir,
        'frontmatter': {'chapters': []},
        'mainmatter': {'chapters': []},
        'backmatter': {'chapters': []},
        'includes': [],
        'graphics': []
    }

    # frontmatter
    fchapters = manifest['frontmatter']['chapters']
    newfchapters = combine_chapters(sourcedir, fchapters, destdir, prefix='00_')
    extractedmanifest['frontmatter']['chapters'] = newfchapters

    # mainmatter
    mchapters = manifest['mainmatter']['chapters']
    newmchapters = combine_chapters(sourcedir, mchapters, destdir, prefix='')
    extractedmanifest['mainmatter']['chapters'] = newmchapters

    # backmatter
    bchapters = manifest['backmatter']['chapters']
    newbchapters = combine_chapters(sourcedir, bchapters, destdir, prefix='99_')
    extractedmanifest['backmatter']['chapters'] = newbchapters

    # includes
    for includerelpath in manifest['includes']:
        sourcepath = os.path.join(sourcedir, includerelpath)
        destpath = os.path.join(destdir, includerelpath)
        ensure_containing_dir_exists(destdir, includerelpath)
        local('cp {} {}'.format(sourcepath, destpath))
        assert os.path.exists(destpath), 'file missing ' + destpath
        if includerelpath not in extractedmanifest['includes']:
            extractedmanifest['includes'].append(includerelpath)
        else:
            puts(red('WARNING: file ' + includerelpath  + ' multiply included'))

    # graphics
    for imagerelpath in manifest['graphics']:
        sourcepath = os.path.join(sourcedir, imagerelpath)
        destpath = os.path.join(destdir, imagerelpath)
        ensure_containing_dir_exists(destdir, imagerelpath)
        local('cp {} {}'.format(sourcepath, destpath))
        assert os.path.exists(destpath), 'graphics file missing ' + destpath
        if imagerelpath not in extractedmanifest['graphics']:
            extractedmanifest['graphics'].append(imagerelpath)

    # book main file (for testing)
    maintexpath = os.path.join(destdir, 'extracted_mainfile_tester.tex')
    with open(maintexpath, 'w') as mainf:
        mainf.write(r"""\documentclass[10pt]{book}
                        \title{Extracted test main file}
                        % put headers here plz
                        \begin{document}
                    """)
        mainf.write("\n\\frontmatter\n\n")
        for chapter in extractedmanifest['frontmatter']['chapters']:
            mainf.write('\\input{' + chapter['sourcefiles'][0] + '}\n')
        mainf.write("\n\\mainmatter\n\n")
        for chapter in extractedmanifest['mainmatter']['chapters']:
            mainf.write('\\input{' + chapter['sourcefiles'][0] + '}\n')
        mainf.write("\n\\appendix\n\n")
        for chapter in extractedmanifest['backmatter']['chapters']:
            mainf.write('\\input{' + chapter['sourcefiles'][0] + '}\n')
        mainf.write("\n\\end{document}\n")

    # write extracted manifest
    extractedmanifest_str = yaml.dump(extractedmanifest, default_flow_style=False, sort_keys=False)
    with open(EXTRACTED_MANIFEST, 'w') as yamlfile:
        yamlfile.write(extractedmanifest_str)
    puts(green('Book source files extracted and combined into ' + destdir))





# TRANSFORM
################################################################################

@task
def transform(extractedmanifest=EXTRACTED_MANIFEST):
    """
    Transforms all the LaTeX source code of all the files in `extractedmanifest`
    to Softcover-compatible macros and writes output to `sources/transformed/`.
    """
    extractedmanifest = yaml.safe_load(open(extractedmanifest))
    sourcedir = extractedmanifest['sourcedir']
    destdir = os.path.join('sources', 'transformed')
    local('rm -rf ' + destdir)
    if not os.path.exists(destdir):
        os.makedirs(destdir, exist_ok=True)

    # the transformed sourcefiles are the same (only graphics paths will change)
    transformedmanifest = copy.deepcopy(extractedmanifest)
    transformedmanifest['sourcedir'] = destdir
    transformedmanifest['graphics'] = []


    # collect a list of all the .tex source files that need to be transformed
    allsourcefiles = []
    for part in ['frontmatter', 'mainmatter', 'backmatter']:
        for chapter in extractedmanifest[part]['chapters']:
            assert len(chapter['sourcefiles']) == 1, 'unexpected num. of sourcefiles'
            allsourcefiles.extend(chapter['sourcefiles'])
    allsourcefiles.extend(extractedmanifest['includes'])

    tansformations = [
        transform_remove_index_commands,
        transform_figure_captions,
        transform_pdf_graphics,
        transform_includes_noext,
        transform_tables,
        transform_aquote,
    ]
    for relpath in allsourcefiles:
        # read in
        sourcepath = os.path.join(sourcedir, relpath)
        soup = TexSoup.TexSoup(open(sourcepath).read(), skip_envs=('verbatimtab', 'code'))

        # run the soup-transforming pipeline
        for tansformation in tansformations:
            soup = tansformation(soup, extractedmanifest, transformedmanifest)

        # write out
        ensure_containing_dir_exists(destdir, relpath)
        destpath = os.path.join(destdir, relpath)
        with open(destpath, 'w') as outf:
            outf.write(str(soup))

        # in-place cleanup
        inplace_cleanup(destdir, relpath)

    # write transformed manifest
    transformedmanifest_str = yaml.dump(transformedmanifest, default_flow_style=False, sort_keys=False)
    with open(TRANSFROMED_MANIFEST, 'w') as yamlfile:
        yamlfile.write(transformedmanifest_str)
    puts(green('Book source files transformed and saved to ' + destdir + '/'))


def transform_remove_index_commands(soup, extractedmanifest, transformedmanifest):
    """
    Get rid of \index and \emphindexdef commands.
    """
    indexs = soup.find_all('index')
    for index in indexs:
        index.delete()
    emphindexdefs = soup.find_all('emphindexdef')
    for emphindexdef in emphindexdefs:
        emphindexdef.name = 'emph'
    return soup


def transform_figure_captions(soup, extractedmanifest, transformedmanifest):
    """
    Softcover expectes figure labels to be found inside figure captions.
    """
    figures = soup.find_all('figure')
    for figure in figures:
        if figure.caption is None:
            print('WARNING: unexpected figure with no caption.')
            print(str(figure))
        if figure.caption and figure.label:
            figure.caption.args[0].append(figure.label)
            figure.label.delete()
    return soup


def transform_tables(soup, extractedmanifest, transformedmanifest):
    """
    Make tables and wraptable environments Softcover compatible.
    """
    # Chapters overview wraptable in noBSmathphys book
    wraptables = soup.find_all('wraptable')
    for wraptable in wraptables:
        'precalc' in ' '.join(wraptable.text)
        wraptable.name = 'table'
        wraptable.args = wraptable.args[3:]

    def find_index_of(array, obj):
        """
        Find index within `array`==parent.expr.all for insert-before operations.
        Note basic `__eq__` doesn't work so using str() for equality comparison.
        """
        for i, objati in enumerate(array):
            if str(objati) == str(obj):
                return i
        return None

    for table in soup.find_all('table'):
        table_text = ' '.join(table.text)

        if 'Quantum' in table_text:
            # LINEAR ALGEBRA QUANTUM MODELS TABLE
            # 1. pull out text blocks in front of table
            frameds = table.find_all('framed')
            for framed in frameds:
                table_idx = find_index_of(soup.expr.all, table)
                newnodes = []
                for child in framed.children:
                    newnodes.append(child.copy())
                    newnodes.append('\n')
                newnodes.extend(['\n', '\n'])
                soup.insert(table_idx, *newnodes)
            # 2. get caption and label
            caption = table.caption.copy()
            label = table.label.copy()
            caption.args[0].append(label)
            # 3. clear children
            for ch in table.children:
                table.remove(ch)
            # 4. add an eempty tabular
            tabular = TexSoup.TexSoup(r"\begin{tabular}{c}\end{tabular}").tabular
            table.append(tabular)
            table.append('\n')
            # 5. add back the caption
            table.append(caption)
            table.append('\n')

        elif 'Correspondences' in table_text:
            # LINEAR ALGEBRA INTRODUCTION TABLE
            align = table.find('align*')
            table_idx = find_index_of(soup.expr.all, table)
            soup.insert(table_idx, align.copy())
            soup.insert(table_idx+1, '\n')
            # 2. add an empty inner tabular so Softcover lookups won't fail
            tabular = TexSoup.TexSoup(r"\begin{tabular}{c}\end{tabular}").tabular
            table.append(tabular)
            table.append('\n')
            # 3. move label inside caption like we do for figures
            table.caption.args[0].append(table.label)
            table.label.delete()
            # 4. cleanup
            table.remove(table.shadebox)

        elif 'input' in table_text and 'output' in table_text:
            # FUNCTIONS INPUT-OUTPUT EXAMPLES TABLE
            # 1. move the align* to in front of the table
            align = table.find('align*')
            table_idx = find_index_of(soup.expr.all, table)
            soup.insert(table_idx, align.copy())
            soup.insert(table_idx+1, '\n')
            table.remove(align)
            # 2. add an empty inner tabular so Softcover lookups won't fail
            tabular = TexSoup.TexSoup(r"\begin{tabular}{c}\end{tabular}").tabular
            table.append(tabular)
            # 3. move label inside caption like we do for figures
            table.caption.args[0].append(table.label)
            table.label.delete()

        elif '359.761' in table_text or 'Conic' in table_text or 'PageRank' in table_text:
            # ELLIPSE, CONICS SUMMARY, and PAGE RANK TABLES
            # 1.extact useful stuff
            longtable = table.longtable.copy()
            if '@{}' in longtable.args[0].string:
                longtable.args[0].string = longtable.args[0].string.replace('@{}', '')
            caption = table.caption.copy()
            label = table.label.copy()
            # 2. clear children
            for ch in table.children:
                table.remove(ch)
            # 3. add the useful stuff back in
            table.insert(2, longtable)
            caption.args[0].append(label)
            table.insert(4, caption)

        elif 'XOR' in table_text:
            # XOR TRUTH TABLE (LINEAR ALGEBRA)
            table.caption.args[0].append(table.label)
            table.label.delete()

        elif 'Fourier' in table_text:
            # FOURIER TABLE (LINEAR ALGEBRA BOOK)
            longtable = table.tabularx.copy()
            longtable.args[0] = longtable.args[1]
            del longtable.args[1]
            longtable.name = 'longtable'
            if '@{}' in longtable.args[0].string:
                longtable.args[0].string = longtable.args[0].string.replace('@{}', '')
            caption = table.caption.copy()
            label = table.label.copy()
            # 2. clear children
            for ch in table.children:
                table.remove(ch)
            # 3. add the useful stuff back in
            table.insert(0, '\n\n')
            table.insert(2, longtable)
            caption.args[0].append(label)
            table.insert(6, caption)

    if soup.chapter and str(soup.chapter.string) == 'Notation':
        bracegroups = []
        for child in soup.children:
            if hasattr(child, 'name') and child.name == 'BraceGroup':
                if child.tabularx:
                    bracegroups.append(child)

        for bracegroup in bracegroups:
            bracegroup_idx = find_index_of(soup.expr.all, bracegroup)
            tabularx = bracegroup.tabularx.copy()
            tabularx.args[0] = tabularx.args[1]
            del tabularx.args[1]
            tabularx.name = 'longtable'
            alignspec = tabularx.args[0].string
            if '@{}' in alignspec:
                alignspec = alignspec.replace('@{}', '')
            if 'p' in alignspec:
                alignspec = re.sub('p\{.*?\}', 'l', alignspec)
            tabularx.args[0].string = alignspec
            soup.insert(bracegroup_idx, tabularx)
            soup.insert(bracegroup_idx+1, '\n\n')
            bracegroup.delete()

    elif soup.chapter and str(soup.chapter.string) == 'Formulas':
        # remove numbering
        for align in soup.find_all('align'):
            align.name = 'align*'
        for equation in soup.find_all('equation'):
            equation.name = 'equation*'
        # other cleanup
        for DStrut in soup.find_all('DStrut'):
            DStrut.delete()
        for ds in soup.find_all('ds'):
            ds.name = 'displaystyle'
        for efrac in soup.find_all('efrac'):
            efrac.name = 'frac'

    elif soup.chapter and 'Constants' in str(soup.chapter.string):
        for tabularx in soup.find_all('tabularx'):
            tabularx.args[0] = tabularx.args[1]
            del tabularx.args[1]
            tabularx.name = 'longtable'
            alignspec = tabularx.args[0].string
            if '@{}' in alignspec:
                alignspec = alignspec.replace('@{}', '')
            if 'p' in alignspec:
                alignspec = re.sub('p\{.*?\}', 'l', alignspec)
            tabularx.args[0].string = alignspec

    return soup


def transform_includes_noext(soup, extractedmanifest, transformedmanifest):
    """
    Softcover's input command automatically adds tha .tex extention so must edit
    all \input statemnts to remove the `.tex` extensio for this to work.
    """
    inputs = soup.find_all('input')
    for input in inputs:
        includerelpath = str(input.string)
        includerelpath_noext = includerelpath.replace('.tex', '')
        input.string = includerelpath_noext
    return soup


def transform_pdf_graphics(soup, extractedmanifest, transformedmanifest):
    """
    Replace .pdf includegraphics paths with .png (when .png version exists),
    or convert .pdf figure to .jpg format (used for concept maps).
    """
    sourcedir = extractedmanifest['sourcedir']
    destdir = transformedmanifest['sourcedir']

    igs = soup.find_all('includegraphics')
    for ig in igs:
        if isinstance(ig.args[0], TexSoup.data.BraceGroup):
            imagerelpath = str(ig.args[0].string)
            igargnum = 0
        else:
            imagerelpath = str(ig.args[1].string)
            igargnum = 1

        # create containing folder in destdir (will be needed by all code paths)
        ensure_containing_dir_exists(destdir, imagerelpath)

        if imagerelpath.endswith('.pdf'):
            # PDF includes must be renamed
            imagerelpath_png = imagerelpath.replace('.pdf', '.png')

            if os.path.exists(os.path.join(sourcedir, imagerelpath_png)):
                # .png file already exists, just need to copy over the file
                imagesrcpath_png = os.path.join(sourcedir, imagerelpath_png)
                imagedestpath_png = os.path.join(destdir, imagerelpath_png)
                if not os.path.exists(imagedestpath_png):
                    local('cp {} {}'.format(imagesrcpath_png, imagedestpath_png))
                ig.args[igargnum].string = imagerelpath_png
                newimagerelpath = imagerelpath_png

            else:
                # no .png file exists, so we'll convert the .pdf file to .jpg
                imagesrcpath = os.path.join(sourcedir, imagerelpath)
                imagerelpath_jpg = imagerelpath.replace('.pdf', '.jpg')
                imagedestpath = os.path.join(destdir, imagerelpath_jpg)
                if not os.path.exists(imagedestpath):
                    print('Converting', imagesrcpath, 'to', imagedestpath)
                    cmd = 'convert -density 452 '
                    cmd += ' -define pdf:use-cropbox=true '  # via https://stackoverflow.com/a/25387099
                    cmd += imagesrcpath
                    cmd += ' -background white '
                    cmd += ' -alpha remove '
                    cmd += ' -resize 25% '
                    cmd += ' -quality 90 '
                    cmd += imagedestpath
                    local(cmd)
                ig.args[igargnum].string = imagerelpath_jpg
                newimagerelpath = imagerelpath_jpg

        else:
            # non-PDF graphics are OK, just need to copy over the file
            imagesrcpath = os.path.join(sourcedir, imagerelpath)
            imagedestpath = os.path.join(destdir, imagerelpath)
            if not os.path.exists(imagedestpath):
                local('cp {} {}'.format(imagesrcpath, imagedestpath))
            newimagerelpath = imagerelpath

        # final verificaiton...
        assert os.path.exists(os.path.join(destdir, newimagerelpath)), 'missing ' + newimagerelpath
        if newimagerelpath not in transformedmanifest['graphics']:
            transformedmanifest['graphics'].append(newimagerelpath)

    return soup


def transform_aquote(soup, extractedmanifest, transformedmanifest):
    """
    Restructure `aquote` (attribution quote) environemts to be regular `quote`.
    """
    aquotes = soup.find_all('aquote')
    for aquote in aquotes:
        attribution = aquote.args[0].string
        aquote.args[1].append(' --- ')
        aquote.args[1].append(attribution)
        del aquote.args[0]
        aquote.name = 'quote'
    return soup


def inplace_cleanup(transformeddir, relpath):
    """
    Process the tex file at `relpath` using a Perl search-and-replace script.
    """
    print('Cleaning up file', relpath)
    filepath = os.path.join(transformeddir, relpath)
    local('./scripts/cleanup.pl ' + filepath)



# LOAD
################################################################################

@task
def load(transformedmanifest=TRANSFROMED_MANIFEST):
    """
    Transforms all the LaTeX source code of all the files in `extractedmanifest`
    to Softcover-compatible macros and writes output to `sources/transformed/`.
    """
    transformedmanifest = yaml.safe_load(open(transformedmanifest))
    sourcedir = transformedmanifest['sourcedir']
    bookdir = os.path.abspath('.')
    imagesdir = os.path.join(bookdir, 'images')
    # chaptersdir = os.path.join(bookdir, 'chapters')
    book_info = yaml.safe_load(open(os.path.join('config', 'book.yml')))
    mainfilename = book_info['filename']

    # includes
    for includerelpath in transformedmanifest['includes']:
        srcpath = os.path.join(sourcedir, includerelpath)
        destpath = os.path.join(bookdir, includerelpath)
        ensure_containing_dir_exists(bookdir, includerelpath)
        local('cp {} {}'.format(srcpath, destpath))

    # graphics
    for imagerelpath in transformedmanifest['graphics']:
        srcpath = os.path.join(sourcedir, imagerelpath)
        destpath = os.path.join(imagesdir, imagerelpath)
        ensure_containing_dir_exists(imagesdir, imagerelpath)
        local('cp {} {}'.format(srcpath, destpath))

    # copy-over book chapters and simultaneously build the book mainfile
    mainfilenametex = mainfilename + '.tex'
    if os.path.exists(mainfilenametex):
        local('cp {} {}'.format(mainfilenametex, mainfilenametex + '.bak'))

    with open(mainfilenametex, 'w') as mainf:

        title = book_info.get('title', mainfilename)
        subtitle = book_info.get('subtitle')
        if not subtitle:
            subtitle = '$\;$'
        author = book_info.get('author', '')
        date = datetime.now().strftime("%B %d, %Y")
        preamble = LATEX_MAINFILE_DOC_PREAMBLE % (title, subtitle, author, date)
        mainf.write(preamble)

        for chapter in transformedmanifest['frontmatter']['chapters']:
            sourcefile = chapter['sourcefiles'][0]
            srcpath = os.path.join(sourcedir, sourcefile)
            destrelpath = os.path.join('chapters', sourcefile)
            ensure_containing_dir_exists(bookdir, destrelpath)
            local('cp {} {}'.format(srcpath, destrelpath))
            mainf.write('\\include{' + destrelpath.replace('.tex', '') + '}\n')

        mainf.write("\n\n\\mainmatter\n\n")
        for chapter in transformedmanifest['mainmatter']['chapters']:
            sourcefile = chapter['sourcefiles'][0]
            srcpath = os.path.join(sourcedir, sourcefile)
            destrelpath = os.path.join('chapters', sourcefile)
            ensure_containing_dir_exists(bookdir, destrelpath)
            local('cp {} {}'.format(srcpath, destrelpath))
            mainf.write('\\include{' + destrelpath.replace('.tex', '') + '}\n')

        mainf.write("\n\\backmatter\n\n")
        for chapter in transformedmanifest['backmatter']['chapters']:
            sourcefile = chapter['sourcefiles'][0]
            srcpath = os.path.join(sourcedir, sourcefile)
            destrelpath = os.path.join('chapters', sourcefile)
            ensure_containing_dir_exists(bookdir, destrelpath)
            local('cp {} {}'.format(srcpath, destrelpath))
            mainf.write('\\include{' + destrelpath.replace('.tex', '') + '}\n')

        mainf.write("\n\\end{document}\n")
        puts(green('Book mainfile written to ' + mainfilenametex))

    puts(green('Book loaded into chapters/, images/, problems/, and 99anssol/'))


LATEX_MAINFILE_DOC_PREAMBLE = r"""
\documentclass[10pt]{book}
\usepackage{latex_styles/softcover}

\title{%s}
\subtitle{%s}
\author{%s}
\date{%s}


\begin{document}

\includepdf{images/cover.pdf}

\maketitle

\frontmatter
\tableofcontents

"""



# ARCHIVE
################################################################################

ARCHIVES_DIR = "/Users/ivan/Projects/Minireference/ePub/archives"

@task
def archive(bookdir='.', ebooksdir='ebooks'):
    """
    Save a backup copy of the files in ebooks/ directory to ePub/archives/ dir.
    """
    bookdir = os.path.abspath(bookdir)
    assert os.path.exists(os.path.join(bookdir, ebooksdir)), 'ebooks/ not found'
    book_info = yaml.safe_load(open(os.path.join(bookdir, 'config', 'book.yml')))
    bookname = book_info['filename']
    date_str = datetime.now().strftime("%Y%m%d")
    destdir = os.path.join(ARCHIVES_DIR, bookname, date_str)
    if not os.path.exists(destdir):
        os.makedirs(destdir, exist_ok=True)
    archived_filenames = []
    for ext in ['.epub', '.mobi']:
        filename = bookname + ext
        sourcepath = os.path.join(bookdir, ebooksdir, filename)
        if os.path.exists(sourcepath):
            destpath = os.path.join(destdir, filename)
            local('cp {} {}'.format(sourcepath, destpath))
            archived_filenames.append(filename)
        else:
            puts(yellow('Did not find ebook ' + sourcepath))
    puts(green('Archived ' + str(archived_filenames) + ' to ' + destdir))

    


# SOFTCOVER INSIDE DOCKER COMMANDS
################################################################################

DOCKER_IMAGE_NAME = 'softcover-docker'

@task
def dbuildimage():
    dlocal('docker build -t {} .'.format(DOCKER_IMAGE_NAME))

@task
def dbuild(format=None, options=''):
    if format is None:
        format = 'all'
    if 'DOCKER_HOST' in env:
        # we need to transfer contents of current directory to docker host
        remote_host_path = copy_local_dir_to_docker_host_dir('.')
        host_path = remote_host_path
    else:
        host_path = os.path.abspath(os.path.curdir)
    cmd = 'docker run -v {host_path}:/book {image} sc build:{format} {options}'.format(
        host_path=host_path, image=DOCKER_IMAGE_NAME, format=format, options=options)
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




# UTILS
################################################################################

def name_matches(texnode, names):
    """
    Returns True if `texnode`'s name is on one of the names in `names`.
    """
    if hasattr(texnode, 'name') and texnode.name in names:
        return True
    else:
        return False


def contains_names(texnode, names):
    """
    Returns True if `texnode` (env or BraceGroup) contains one of the `names`.
    """
    verdict = False
    for name in names:
        if texnode.find(name):
            verdict = True
            break
    return verdict


def latexpand(sourcedir, mainfilename):
    """
    Process the latex document `mainfilename` and expand `\input`s statements.
    Returns a list of `TexLine` named tuples that are used by `extractmanifest`.
    """
    TexLine = namedtuple('TexLine', ['parent', 'relpath', 'texnode'])

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
                childdoc = TexSoup.TexSoup(open(includepath).read(), skip_envs=('verbatimtab', 'code'))
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
                    childdoc = TexSoup.TexSoup(open(includepath).read(), skip_envs=('verbatimtab', 'code'))
                    latexpand_recursive(childdoc, texlines, relpath=childrelpath, parentrelpath=relpath)
            else:
                #  C: regular non-include lines
                texlines.append(TexLine(parentrelpath, relpath, texnode))
        return texlines

    mainpath = os.path.join(sourcedir, mainfilename)
    print('reading ', mainfilename)
    soup = TexSoup.TexSoup(open(mainpath).read(), skip_envs=('verbatimtab', 'code'))
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


def ensure_containing_dir_exists(destdir, relpath):
    dirname = os.path.dirname(relpath)
    destdirpath = os.path.join(destdir, dirname)
    if not os.path.exists(destdirpath):
        os.makedirs(destdirpath, exist_ok=True)



