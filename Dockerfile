FROM circleci/ruby:2.6.3-stretch-node-browsers-legacy
MAINTAINER Nick Merwin <nick@softcover.io>
LABEL company="Softcover, Inc."
LABEL version="1.0.0"

USER root

# ==============================================================================
# install deps
# ==============================================================================
RUN gem install -v 2.1.4 bundler
RUN apt-get update -qq && apt-get install -qy --no-install-recommends texlive-full texlive-fonts-recommended \
  texlive-latex-extra texlive-fonts-extra fonts-gfs-bodoni-classic inkscape ghostscript cabextract
RUN wget http://ftp.de.debian.org/debian/pool/contrib/m/msttcorefonts/ttf-mscorefonts-installer_3.6_all.deb \
  && dpkg -i ttf-mscorefonts-installer_3.6_all.deb
RUN wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sh
ENV PATH="${PATH}:/root"
RUN curl -O -L https://github.com/w3c/epubcheck/releases/download/v4.2.2/epubcheck-4.2.2.zip && unzip epubcheck-4.2.2.zip -d ~
RUN wget https://softcover-static.s3.amazonaws.com/Bodoni%2072%20Smallcaps%20Book.ttf && \
  cp 'Bodoni 72 Smallcaps Book.ttf' /usr/share/fonts/truetype/bodoni-classic \
  && fc-cache -fs

# ==============================================================================
# softcover gem
# ==============================================================================
RUN gem install softcover:1.6.4

# ==============================================================================
# Health check
# ==============================================================================
RUN softcover check

# ==============================================================================
# Ready to run
# ==============================================================================
RUN mkdir /book
WORKDIR /book

EXPOSE 4000
