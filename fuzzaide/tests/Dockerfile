FROM ubuntu:22.04 as base

ARG DEBIAN_FRONTEND=noninteractive


ARG LLVM="14"
ARG GCC="12"
RUN : \
    && apt-get update \
    && apt-get -y upgrade \
    && apt-get -y install --no-install-suggests --no-install-recommends \
        autoconf automake make cmake \
        gcc-${GCC} g++-${GCC} gcc-${GCC}-plugin-dev \
        clang-${LLVM} llvm-${LLVM} \
        libc++abi-${LLVM}-dev libc++-${LLVM}-dev \
        llvm-${LLVM}-dev llvm-${LLVM}-tools lld-${LLVM} \
        less file git curl \
        python3-minimal python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && :

RUN : \
    && update-alternatives --install /usr/bin/clang clang /usr/bin/clang-${LLVM} 0 \
    && update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-${LLVM} 0 \
    && update-alternatives --install /usr/bin/llvm-profdata llvm-profdata /usr/bin/llvm-profdata-${LLVM} 0 \
    && update-alternatives --install /usr/bin/llvm-cov llvm-cov /usr/bin/llvm-cov-${LLVM} 0 \
    && update-alternatives --install /usr/bin/llvm-config llvm-config /usr/bin/llvm-config-${LLVM} 0 \
    && update-alternatives --install /usr/bin/llvm-ar llvm-ar /usr/bin/llvm-ar-${LLVM} 0 \
    && update-alternatives --install /usr/bin/llvm-ranlib llvm-ranlib /usr/bin/llvm-ranlib-${LLVM} 0 \
    && update-alternatives --install /usr/bin/lld lld /usr/bin/lld-${LLVM} 0 \
    && update-alternatives --install /usr/bin/ld.lld ld.lld /usr/bin/ld.lld-${LLVM} 0 \
    && : \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-${GCC} 0 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-${GCC} 0 \
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
    && export CC=clang CXX=clang++ \
    && make source-only \
    && make install \
    && cd / \
    && :

ENV LIB_FUZZING_ENGINE="/AFLplusplus/libAFLDriver.a"

WORKDIR /fuzz



FROM add-afl AS test-simple

RUN : \
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



FROM add-afl AS test-heavy

RUN : \
    && apt-get update \
    && apt-get -y install --no-install-suggests --no-install-recommends \
        tcl \
    && rm -rf /var/lib/apt/lists/* \
    && :
# build instructions source:
# https://github.com/google/oss-fuzz/blob/b5c6cd48c0f6b5c50e088096f8decdf2b673fb49/projects/sqlite3/build.sh
ARG GIT_SQLITE_TAG="version-3.39.2"
RUN : \
    && git clone https://github.com/sqlite/sqlite \
        --depth=1 -b ${GIT_SQLITE_TAG} /src \
    && :

RUN : \
    && mkdir -p /src/fuzz_build \
    && cd /src/fuzz_build \
    && export ASAN_OPTIONS=detect_leaks=0 \
    && export CFLAGS="-O2 -fno-omit-frame-pointer \
            -DSQLITE_MAX_LENGTH=128000000 \
            -DSQLITE_MAX_SQL_LENGTH=128000000 \
            -DSQLITE_MAX_MEMORY=25000000 \
            -DSQLITE_PRINTF_PRECISION_LIMIT=1048576 \
            -DSQLITE_DEBUG=1 \
            -DSQLITE_MAX_PAGE_COUNT=16384" \
    && export CC=afl-clang-fast CXX=afl-clang-fast++ LD=afl-clang-fast++ \
    && ../configure \
    && make -j $(nproc) \
    && make sqlite3.c \
    && $CXX $CFLAGS -I. -c /src/test/ossfuzz.c -o /src/test/ossfuzz.o \
    && $CXX $CXXFLAGS /src/test/ossfuzz.o -o /fuzz/sqlite_fuzz $LIB_FUZZING_ENGINE ./sqlite3.o \
    && :



ENV AFL_SKIP_CPUFREQ=1
ENV AFL_TRY_AFFINITY=1
ENV AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1



FROM test-heavy AS fuzzaide

RUN : \
    && pip3 install \
        pytest \
        pytest-mock \
    && :

COPY . /fuzzaide
RUN : \
    && cd /fuzzaide \
    && pip3 install .[test] \
    && pytest \
    && :

