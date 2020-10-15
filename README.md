Sample Book
===========
Starter template for a scientific book written in LaTeX with build-scripts for
producing PDF, HTML, ePub, and mobi eBook formats.

Technologies uses:
  - `softcover` the best build system for eBooks ever built
  - `Fabric` automation library in Python (think Makefile but written in Python)
  - `alvinwan/TexSoup` for parsing latex source into AST (used for source linting and formatting only)


## Install

```bash
# 1. create a Python virtualenv (required for pygments code highliting)
virtualenv -p python2.7 venv2
source venv2/bin/activate


# 2. install Ruby v2.6.3 so we don't have to use system-ruby
rvm install ruby-2.6.3
```


## Build (local)

```bash
# make sure we're running the right Pythons and Rubies
source venv2/bin/activate
rvm use ruby-2.6.3

softcover check   # make sure sytem all requirements are installed
sofcover build    # builds HTML, ePub, mobi, and PDF
```


## Docker build (local)

Assuming docker installed on your machine you can built the image using:
```bash
docker build -t softcover-docker .
```

Then build html book from this project, by mounting the current directory under
the `/book` directory inside the container:
```bash
docker run -v $PWD:/book softcover-docker sc build:html
```

To start the softcover live-updating server, run the command
```bash
docker run -v $PWD:/book -p 4000:4000 softcover-docker sc server
```


## Install fabric

```bash
virtualenv -p python3.6 venv
source venv/bin/activate
pip install -r requirements.txt
```

## Docker build using Fabric (local or remote)

Edit the constants at the top of `fabfile.py` to specify access credentials to a
machine that has docker installed.

Build the docker image that contains softcover:
```bash
fab dbuildimage
```

Build the ePub format:
```bash
fab dbuild:epub
```



## Book sources (minireference LaTeX)
Before we can the `softcover` framework to build the ePub and mobi formats for
our book, we must first extract the source code and perform some preprocessing
steps to make sure the .tex source is in the format expected by Softcover.

You can automatically generate a draft book manifest file using the command:
```bash
fab extractmanifest:"/Users/ivan/Projects/Minireference/MATHPHYSbook/noBSguideMath.tex"
```

The book manifest `config/manifest.yml` format has the following structure:
```yaml
---
sourcedir: "/Users/ivan/Projects/Minireference/MATHPHYSbook"
frontmatter:
  chapters:
    - title: Concept maps
      label: concept_maps
      sourcefiles:
        - "00_frontmatter/concept_map.tex"
    - title: Preface
      label: sec:preface
      sourcefiles:
        - 00.preface.tex
    - title: Introduction
      label: sec:introduction
      sourcefiles:
        - "00.introduction.tex"
mainmatter:
  chapters:
    - title: Numbers, variables, and equations
      label: chapter:equations
      sourcefiles:
        - 01_math/01.solving_equations.tex
        - 01_math/02.numbers.tex
        - ...
    - title: Algebra
      label: chapter:algebra
      sourcefiles:
        - 01_math/05.basic_rules_of_algebra.tex
        - 01_math/06.solving_quadratic_equations.tex
        - ...
backmatter:   # not implemented yet (just add as a regular chapter)
includes:     # .tex files included in one of the sourcefiles
graphics:     # the contents of all includegraphics commands (prefer png)
  - figures/math/circle-centered-at-h-k.png
  - figures/math/polar/empty_coordinate_system_polar.png
  - ...
```

This manifest provides all the info needed to extract the relevant source files,
transform them into softcover-compatible LaTeX markup, and load them into the
`chapters/` directory, where they will be picked up by the softcover build step.

All three these steps can be performed using:
```bash
fab extract transform load
```




## Book structure (softcover LaTeX)

    sample-book.tex
    chapters/
        preface.tex
        chapter_01__intro.tex
        chapter_02__mainstuff.tex
        chapter_03__conclusion.tex
    images/
        cover.jpg           # book cover to be used for ePub and mobi builds
        cover.pdf           # book cover to be used for the PDF build
        figures/
            someimg.png
            anotherimg.jpeg

You can assume the "build process" is happening in the root of the git repository
so you can use relative paths to figures, e.g. `images/figures/someimg.png` and
they will be resolved correctly.


## Configs

  - `config/book.yml`: book metadata
  - `config/lang.yml`: i18n strings
  - `config/preamble.tex`: this file is only used to get the latex `documentclass` declaration.
     The actual `documentclass` declaration used for `build:pdf` is whatever is in `sample-book.tex`.
  - `latex_styles/softcover.sty`: main LaTeX header file that defines the LaTeX macros and styles
     and includes the other config files below.
  - `latex_styles/custom.sty `: define additional macros, e.g. `\newcommand{\unitvec}[1]{\ensuremath{\hat #1}}`.
     These macros will be available in all build pipelines.
  - `latex_styles/custom_pdf.sty`: same as the above but used only for LaTeX build pipeline



## Book build directories

  - `html` build directory for the HTML format. 
    - `html/images` is a symlink to the `images/` directory in the project root.
  - `epub` build directory for the epub format
  - `ebooks` output directory for .pdf, .epub, and .mobi formats
  - `99anssol` directory where exercises answers and solutions are collected to
    be printed in the Answers and Solutions appendix. Only relevant when `\setboolean{SOLSINTHEBACK}{true}`.
  - `log` very detailed logging output you'll want to check when things break


## Exercises and problems

### Definitions

  - Exercise = easy question with numbering contiguous throughout chapter, e.g. `E{chapter}.{ecounter}`.
  - Problem = harder end-of-chapter problem, labelled `P{chapter}.{pcounter}`.


### Exercise formatting

  - each exercise section starts an `{exercises}{chNUM}` where `chNUM` is some filename  (e.g. ch2)
  - each exercise environment contains
    - question text
    - one or more {hint} environments
    - an {eanswer} environment (optional)
    - an {esolution} environment (optional)


### Problems formatting

  - each problems section starts an `{problems}{CHNUM}` where CHNUM is some filename  (e.g. ch2)
  - each problem environment contains
    - question text
    - one or more {hint} environments
    - an {answer} environment (optional)
    - an {solution} environment (optional)

