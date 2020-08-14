# sample-book
Starter template for a scientific book written in LaTeX with build-scripts for producing PDF, HTML, ePub, mobi, et al. formats.


Technologies uses:
  - `softcover` the best build system for eBooks ever built
  - `Fabric` automation library in Python (think Makefile but written in Python)
  - `alvinwan/TexSoup` for parsing latex source into AST (used for source linting and formatting only)


## Book source structure

    book.tex
    chapters/
        chapter_01__intro.tex
        chapter_02__mainstuff.tex
        chapter_03__conclusion.tex
    figures/     (or images?)
        intro/
            someimg.png
            anotherimg.jpeg

You can assume the "build process" is happening in the root of the git repository
so you can use relative paths to figures, e.g. `figures/intro/someimg.png` and
they will be resolved correctly.


## Configs

  - `config/book.yml`: book metadata
  - `config/lang.yml`: i18n strings
  - `config/preamble.tex`: the latex `\documentclass` declaration, default=`\documentclass[14pt]{extbook}`
  - `latex_styles/softcover.sty`: main LaTeX header file
  - `latex_styles/custom.sty `: define additional macros, e.g. `\newcommand{\unitvec}[1]{\ensuremath{\hat #1}}`
  - `latex_styles/custom_pdf.sty`: same as the above but used only for LaTeX build pipeline


## Book build directories

  - `html` build directory for the HTML format
  - `epub` build directory for the epub format
  - `ebooks` output directory for .pdf, .epub, and .mobi formats
  - `99anssol` directory where exercises andswers and solutions are collected to
    be printed in the Answers and Solutions appendix. Only relevant when `\setboolean{SOLSINTHEBACK}{true}`.
  - `log` very detailed logging output you'll want to check when things break
