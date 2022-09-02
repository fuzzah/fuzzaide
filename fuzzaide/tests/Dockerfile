FROM ubuntu:22.04 as base

ARG DEBIAN_FRONTEND=noninteractive

RUN : \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get -y install --no-install-suggests --no-install-recommends \
        build-essential \
        less file git curl \
        python3-minimal python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && :

FROM base AS add-afl
# ARG GIT_AFLPP_BRANCH="dev"
ARG GIT_AFLPP_TAG="4.02c"
ENV GIT_AFLPP_SRC="/AFLplusplus"
RUN : \
    && git clone \
        https://github.com/AFLplusplus/AFLplusplus \
        --depth=1 -b ${GIT_AFLPP_TAG} ${GIT_AFLPP_SRC} \
    && cd ${GIT_AFLPP_SRC} \
    && export NO_NYX=1 \
    && make source-only \
    && make install \
    && cd / \
    && rm -rf ${GIT_AFLPP_SRC} \
    && :



FROM add-afl AS test

RUN : \
    && mkdir /fuzz \
    && cd /fuzz \
    && printf "#include <stdio.h>\n#include <stdlib.h>\n#include <unistd.h>\n" \
        > fuzz.c \
    && echo "\n\
int main(int argc, char* argv[])\n\
{\n\
    char buf[10];\n\
    int len = read(0, buf, sizeof(buf));\n\
    if (len < 5) {\n\
        return 0;\n\
    }\n\
    if (buf[0] != 'F') return 1;\n\
    if (buf[1] != 'U') return 2;\n\
    if (buf[2] != 'Z') return 3;\n\
    if (buf[3] != 'Z') return 4;\n\
    //if (buf[4] != '!') return 5;\n\
    abort();\n\
}" \
        >> fuzz.c \
    && afl-gcc fuzz.c -g -O2 -fno-omit-frame-pointer -o fuzz \
    && mkdir in \
    && echo '!ZUF' > in/1 \
    && :

ENV AFL_SKIP_CPUFREQ=1
ENV AFL_TRY_AFFINITY=1
ENV AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1

COPY . /fuzzaide
RUN : \
    && cd /fuzzaide \
    && pip3 install .[test] \
    && pytest \
    && :

WORKDIR /fuzz
