FROM circleci/ruby:2.6-bullseye-node-browsers-legacy
LABEL maintainer="ivan@minireference.com"
LABEL company="Minireference Co."
LABEL version="1.1.2"

USER root


# ==============================================================================
# install deps
# ==============================================================================
RUN gem install -v 2.1.4 bundler
RUN echo 'deb http://deb.debian.org/debian bullseye-backports main' > /etc/apt/sources.list.d/backports.list
RUN apt-get update -qq \
  && apt-get -t bullseye-backports install -qy --no-install-recommends "inkscape" \
  && apt-get install -qy --no-install-recommends \
      texlive-xetex texlive-latex-recommended texlive-latex-extra \
      texlive-lang-english texlive-lang-french texlive-lang-cyrillic \
      texlive-science texlive-pictures latexdiff \
      texlive-fonts-recommended texlive-fonts-extra fonts-gfs-bodoni-classic \
      ghostscript \
      cabextract \
  && rm -rf /var/lib/apt/lists/*
RUN wget http://ftp.de.debian.org/debian/pool/contrib/m/msttcorefonts/ttf-mscorefonts-installer_3.6_all.deb \
  && dpkg -i ttf-mscorefonts-installer_3.6_all.deb
RUN wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sh
ENV PATH="${PATH}:/root"
RUN curl -O -L https://github.com/w3c/epubcheck/releases/download/v4.2.2/epubcheck-4.2.2.zip \
  && unzip epubcheck-4.2.2.zip -d /root
RUN wget https://softcover-static.s3.amazonaws.com/Bodoni%2072%20Smallcaps%20Book.ttf && \
  cp 'Bodoni 72 Smallcaps Book.ttf' /usr/share/fonts/truetype/bodoni-classic \
  && fc-cache -fs

# TODO install optipng
RUN echo "TODO apt install optipng and make use of it..."

# ==============================================================================
# Install miniref versions of softcover and polytexnic
# ==============================================================================
RUN cd /root \
  && git clone https://github.com/minireference/softcover.git \
  && cd softcover \
  && git checkout miniref \
  && bundle install \
  && bundle exec rake install  \
  && echo "Softcover insalled from miniref branch" \
  && cd /root \
  && git clone https://github.com/minireference/polytexnic.git \
  && cd polytexnic \
  && git checkout miniref \
  && bundle install \
  && bundle exec rake install \
  && echo "PolyTeXnic installed from miniref branch"

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
