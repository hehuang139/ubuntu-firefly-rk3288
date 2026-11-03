FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends qemu-user-static binfmt-support debootstrap ubuntu-keyring ca-certificates curl xz-utils zstd gzip e2fsprogs dosfstools mtools fdisk rsync python3 kmod u-boot-tools && rm -rf /var/lib/apt/lists/*
