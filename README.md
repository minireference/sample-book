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
virtualenv -p python2.7 venv

# 2. install Ruby v2.6.3 so we don't have to use system-ruby
rvm install ruby-2.6.3
```


## Build

```bash
# make sure we're running the right Pythons and Rubies
source venv/bin/activate
rvm use ruby-2.6.3

softcover check   # make sure sytem all requirements are installed
sofcover build    # builds HTML, ePub, mobi, and PDF
```


## Docker build

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

## Book source structure

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

  - Exercise = easy question with numbering contiguous throughout chapter e.g. E{chapter}.{counter}
  - Problem = harder end-of-chapter problem 


### Exercise formatting

  - each exercise section starts an `{exercises}{CHNUM}` where CHNUM is some filename  (e.g. ch2)
  - each exercise envoronment contains
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


