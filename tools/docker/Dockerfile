FROM ubuntu:24.04
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq binutils-arc-linux-gnu python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /w
