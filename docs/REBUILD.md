# 重建 Ubuntu 22.04 GNOME 镜像

本目录的入口是 `rebuild.sh`。它构建 **原版 Firefly-RK3288、armhf、HDMI、TF 卡**使用的 Ubuntu 22.04 GNOME 镜像。引导程序、内核、设备树均针对原版板型；板载 eMMC 在 Linux 设备树中禁用。

## 构建主机

使用 x86_64 Linux 主机、可正常运行容器的 Docker Engine，以及 Python 3、Bash、tar、gzip、sha256sum。建议预留至少 60 GB 空间、8 GB 内存，并能访问 Ubuntu 软件仓库。Docker 工具镜像基于 Ubuntu 22.04。

`rootfs` 和 `finalize` 两步需要 Docker `--privileged`，用来挂载 chroot 的 `/dev`、`/proc`、`/sys` 并注册 ARM 用户态执行器。相关脚本退出时卸载这些挂载，并撤销自己新建的 binfmt 注册。工具和内核构建、镜像组装不需要这一选项。所有输出是目录和普通镜像文件；刷写 TF 卡另行操作。

从新克隆的仓库或解压到新目录的 Release 源码材料开始构建。已有 rootfs 或镜像需要继续构建时，使用下文的分步入口和新输出名称。

## 获取源码与基础归档

```bash
git clone https://github.com/hehuang139/ubuntu-firefly-rk3288.git
cd ubuntu-firefly-rk3288
./rebuild.sh fetch
```

Git 仓库保存脚本、配置、文档和发布记录。`fetch` 读取根目录 `sources.json`，从上游下载固定版本的 Ubuntu Base、Linux 和 U-Boot 三份归档并核对 SHA-256；这一步仅需要 Python 3 和网络。已有文件也要通过哈希核对，核对失败会报告具体文件。

[v0.1.0-alpha Release](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/tag/v0.1.0-alpha) 的 `firefly-rk3288-ubuntu22.04-gnome-sources.tar.gz` 已包含这三份输入归档，可直接解压后构建，也可把归档按下列路径离线复制到仓库。Docker 基础镜像和 Ubuntu 软件包安装仍需访问对应仓库。

## 目录布局

以下归档由 `fetch` 获取，loader 由 `bootloader` 阶段生成；Release 源码材料随附制作时使用的归档与 loader。

```text
rebuild.sh
sources.json
LICENSE
THIRD_PARTY.md
builder/Dockerfile
scripts/
  install-rootfs.sh
  configure-rootfs.sh
  finalize-rootfs.sh
  assemble-image.py
  prefetch-packages.py
  ...
overlay/
  etc/...
  usr/local/sbin/firefly-resize
downloads/
  ubuntu-base-22.04.5-base-armhf.tar.gz
  SHA256SUMS
  SHA256SUMS.gpg
kernel/
  Dockerfile
  build-kernel.sh
  firefly-ubuntu22.config
  rk3288-firefly-ubuntu22.dts
  linux-6.6.161.tar.xz
  source.sha256
  sha256sums.asc
  audit-kernel.py
  ...
bootloader/
  idbloader.img
  u-boot-dtb.img
  source/
    rebuild-u-boot.sh
    u-boot-v2024.01.tar.gz
    uboot.config
    uboot-manifest.json
docs/
release-records/20261103/
  packages.tsv
  source-packages.tsv
  validation/
```

首次构建生成 `rootfs/`、`kernel/build/`、`kernel/staging/`、`bootloader/source/build/`、`boot-files/`、`image-parts/` 和 `artifacts/`。`packages.tsv` 记录实际安装的二进制包版本，`image-manifest.json` 记录镜像和启动文件校验值。已有交付记录与重建后的记录可能不同。

## 一次完成

在已经获取输入归档的仓库或解压目录中执行：

```bash
./rebuild.sh check
./rebuild.sh all
```

`check` 核对 Docker 可用性、必要文件及 Ubuntu Base、Linux、U-Boot 源码归档 SHA-256。Ubuntu Base 的签名文件保留在 `downloads/`；本次制作时的签名核对记录见 [BUILDNOTES.md](BUILDNOTES.md)。仓库的 `all` 入口先执行 `fetch`，再依次构建工具容器、内核、U-Boot、GNOME 根文件系统、initramfs 和整盘镜像。

输出位置：

```text
artifacts/firefly-rk3288-ubuntu22.04-gnome-armhf.img
artifacts/firefly-rk3288-ubuntu22.04-gnome-armhf.img.gz
artifacts/firefly-rk3288-ubuntu22.04-gnome-armhf.SHA256SUMS
```

默认未压缩镜像为 8 GiB，TF 卡需至少 16 GB。镜像包含 256 MiB FAT32 启动分区和 ext4 根分区；第一次启动将根分区扩展到卡上可用空间。

## 分步构建及继续工作

```bash
./rebuild.sh fetch
./rebuild.sh tools
./rebuild.sh kernel
./rebuild.sh bootloader
./rebuild.sh rootfs
./rebuild.sh finalize
./rebuild.sh image
```

- `fetch` 获取并验证三份固定版本输入归档，已有且哈希一致的文件直接复用。
- `tools` 构建 `firefly-ubuntu22-builder:local` 和 `firefly-ubuntu22-cross:local`。
- `kernel` 调用 `kernel/build-kernel.sh`，基于 Linux 6.6.161 的 `multi_v7_defconfig` 合并 Firefly 配置片段，编译 zImage、DTB 和模块。
- `bootloader` 调用 `bootloader/source/rebuild-u-boot.sh`。配方以原版 `firefly-rk3288_defconfig` 为起点，在命令中声明所有配置改动；`uboot.config` 是制作时解析后的配置记录。产物复制到 `bootloader/`。
- `rootfs` 从 Ubuntu Base 新建系统，在 QEMU ARM chroot 内执行 apt/dpkg，安装 GNOME、中文环境和桌面程序。此入口要求 `rootfs/` 为空。
- `finalize` 要求包安装已成功、内核和模块已生成。它安装模块、生成匹配的 initramfs、应用 overlay、清理缓存和机器标识，然后生成 `boot-files/`。只在前置步骤完成后执行一次。
- `image` 需要已完成的 `rootfs/`、`boot-files/` 和两个 loader。它用 mkfs/mtools 组装普通文件并校验分区和 loader，压缩后输出两个文件的 SHA-256。

如果 apt 下载中断且还没有执行 `finalize`，可以在检查上一次日志后直接重跑安装脚本，继续现有包安装状态：

```bash
docker run --rm --privileged \
  -v "$PWD:/build" -w /build firefly-ubuntu22-builder:local \
  bash /build/scripts/install-rootfs.sh
```

`finalize` 会把 DNS 配置换成目标系统的链接、清除构建期辅助文件。完整重建请重新解压源码材料，避免把一个已配置完毕的根文件系统再次当作新系统安装。

可通过环境变量使用已有工具容器或更改输出文件名：

```bash
FIREFLY_BUILD_IMAGE=my-firefly-cross:local ./rebuild.sh kernel
FIREFLY_ROOTFS_IMAGE=my-firefly-rootfs:local ./rebuild.sh image
FIREFLY_OUTPUT_NAME=firefly-ubuntu22-test2 ./rebuild.sh image
```

这两个容器需具备对应 Dockerfile 中列出的工具。输出名仅允许普通文件名字符，不接受路径。重新组装前应使用新文件名；入口保留已有镜像。

## Ubuntu 软件包与首次建号

Ubuntu 包使用安装时的 Jammy、jammy-updates、jammy-security 和 jammy-backports 仓库。APT 验证 Ubuntu 签名元数据；当前脚本从中科大 Ubuntu Ports 镜像下载。源码归档和内核版本固定，但 APT 仓库、Docker 基础层及文件系统 UUID 会变化。比较重建结果时使用实际生成的 `packages.tsv` 和 manifest。2026-11-03 交付镜像的包清单、对应源码包清单与验证结果保存在 [release-records/20261103/](../release-records/20261103/)。

镜像预设 `zh_CN.UTF-8` 和 Asia/Shanghai，安装中文 GNOME 翻译、字体及拼音输入法。Jammy 的 GNOME Initial Setup 软件包默认跳过语言页；首次启动按实际显示的页面完成设置，创建自己的用户名和密码即可。镜像不预置普通用户或统一密码，root 锁定。语言和地区可在进入桌面后通过系统设置调整。

GDM 默认启用 Wayland，保留 Xorg 会话；Panfrost 使用 Ubuntu 的 Mesa 驱动。不要用其他板子的 DTB 或专有 libmali 覆盖这些文件。

## 后续内核更新必须成套进行

Ubuntu 常规 `apt upgrade` 更新用户空间软件。当前内核是本项目构建的 `6.6.161-firefly`，并非仓库通用内核包；安装另一套发行版内核包不会自动完成本板适配。

更新内核时同时准备并核对：

1. 新内核 zImage 和对应 DTB。
2. `/lib/modules/<新版本>/` 中的模块及 `depmod` 元数据。
3. 在目标 Ubuntu 根文件系统中为这个新版本生成的 initramfs。
4. TF 卡 FAT 启动分区中的内核、initramfs、DTB 和 `extlinux/extlinux.conf`。
5. 根文件系统 `/boot/` 中用于后续维护的版本文件及配置。

当前 FAT 启动分区挂载在 `/boot/firmware`，启动文件为 `/boot/firmware/boot/{zImage,initrd.img,rk3288-firefly.dtb}`。不要只替换 `/boot/vmlinuz-*`，也不要仅换模块或设备树。升级配方中的版本常量时，需同步更新 `kernel/build-kernel.sh`、配置、`scripts/finalize-rootfs.sh`、入口前置检查和记录文件，再生成新整盘测试镜像。

U-Boot 是另一层独立组件；本版两个 loader 写入 32 KiB 和 8 MiB 偏移。更新它应保留 Firefly 的 DDR、板型和 SD 引导配置。旧板载引导是否优先启动由现有固件决定，镜像里的 U-Boot 设置只有在自身已运行后生效。

## 发布材料

Git 仓库收录配方、配置、校验文件、许可证及版本记录。压缩镜像和配套源码材料作为 GitHub Release 附件发布；Ubuntu 用户空间对应源码的索引与归档也单独列在该版本的 Release 附件中。具体组件许可与获取方式见 [THIRD_PARTY.md](../THIRD_PARTY.md)。

整理发布文件时按明确清单选取，构建目录、根文件系统、缓存和个人环境由 `.gitignore` 排除。版本记录保存在 `release-records/<日期>/`，保留该次实际镜像的包版本、哈希和验证结果。
