# 组件来源与许可

本项目用于重建原版 Firefly-RK3288 的 Ubuntu 22.04 GNOME TF 卡镜像。系统由 Ubuntu 软件包、Linux 内核、U-Boot、设备树和本项目的组装脚本组成，各部分使用各自的许可证。

Git 仓库保存配方、配置、许可证与版本记录；`./rebuild.sh fetch` 按 `sources.json` 获取并核对 Ubuntu Base、Linux 和 U-Boot 的固定版本归档。Release 的配套源码材料包含这三份输入归档，可供离线复制与核对。Ubuntu 用户空间的对应源码索引与归档采用独立 Release 附件，具体文件及校验值以[对应版本页面](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/tag/v0.1.0-alpha)为准。

## 本项目独立脚本

根目录 `LICENSE` 的 MIT 条款只适用于本项目独立编写的脚本：

- `rebuild.sh`。
- `scripts/` 中的输入归档获取、根文件系统安装、配置、finalize、镜像组装、预下载与核对脚本。
- `overlay/usr/local/sbin/firefly-resize`。
- `kernel/build-kernel.sh`、`kernel/audit-kernel.py`。
- `bootloader/source/rebuild-u-boot.sh`。

该 MIT 条款不改变上游源码、由上游配置派生的配置文件、设备树、系统软件包、固件、字体及图片的许可。上游文件保留其版权声明和 SPDX 标记。

## Ubuntu 22.04 armhf 用户空间

- 基础归档：`downloads/ubuntu-base-22.04.5-base-armhf.tar.gz`。
- 来源：https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/ 。
- 安装仓库：Ubuntu Jammy、updates、security、backports；脚本使用中科大 Ubuntu Ports 镜像，APT 验证 Ubuntu 签名元数据。
- 官方仓库：https://ports.ubuntu.com/ubuntu-ports/ 。
- 本次实际二进制包清单：[release-records/20261103/packages.tsv](release-records/20261103/packages.tsv)。
- 对应源码包与版本：[release-records/20261103/source-packages.tsv](release-records/20261103/source-packages.tsv)。

Ubuntu Base 以及后续安装的 GNOME、Mesa、systemd、应用程序和工具不是一个单一许可证的软件包集合。每个安装包的许可及上游来源可在镜像内 `/usr/share/doc/<包名>/copyright` 查阅。GNOME 各组件、Mesa、系统库等分别使用 GPL、LGPL、MIT/BSD 等许可证；固件包中不同文件另有各自许可。镜像中由 Ubuntu 包提供的壁纸、图标和字体也保留原许可。

板级源码材料包含内核、U-Boot 及组装脚本的源码和配方，Ubuntu Base 归档属于二进制起点。已安装的 848 个二进制包对应 501 组源码包名与版本。Release 的三份 `ubuntu22.04-jammy-corresponding-sources-*-of-03.tar` 包含全部 1,555 个原始源码文件，逐文件大小和 SHA-256 核对通过；下载、解包及认证记录见[对应源码说明](docs/CORRESPONDING-SOURCES.md)。继续分发镜像时，各组件的源码和许可提供要求随其许可证适用。

记录二进制包对应的源码包与版本，可在运行的系统或构建 chroot 中执行：

```sh
dpkg-query -W -f='${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n' > source-packages.tsv
```

添加与当前二进制仓库匹配的 `deb-src` 条目、运行 `sudo apt update` 后，用 `apt-get source 源码包名=源码版本` 获取该版本源码。Ubuntu 更新仓库可能清理旧版本；需要固定版本归档时，应在制作该次镜像时一并保存源码包、其签名 `.dsc` 和相关构建资料。镜像内的 `copyright` 文件及上游仓库是识别具体许可边界的依据。

## Linux 6.6.161

- 完整源码归档：`kernel/linux-6.6.161.tar.xz`，由 `fetch` 获取，Release 配套源码材料内含该文件。
- 来源：https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.161.tar.xz 。
- 核对文件：`kernel/source.sha256`、`kernel/sha256sums.asc`。
- 本板构建资料：`kernel/firefly-ubuntu22.config`、`kernel/rk3288-firefly-ubuntu22.dts`、`kernel/build-kernel.sh`。

Linux 内核整体采用 GPL-2.0-only，并在具体文件中包含双重许可及不同许可的组件。完整源码内的 `COPYING`、`LICENSES/` 和各文件 SPDX 声明适用。源码归档内保留这些文本；对应源代码、板级配置和构建配方随本材料提供。

原版 Firefly 设备树及本项目 wrapper DTS 的文件头为 `(GPL-2.0+ OR MIT)`；其他设备树与绑定头文件按自身声明处理。设备树引用上游原版 Firefly 板型，未导入其他系统的设备树补丁集合。

## U-Boot v2024.01

- 完整源码归档：`bootloader/source/u-boot-v2024.01.tar.gz`，由 `fetch` 获取，Release 配套源码材料内含该文件。
- 来源：https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01 。
- 配方：`bootloader/source/rebuild-u-boot.sh`。
- 解析后配置记录：`bootloader/source/uboot.config`。
- 原有构建产物来源记录：`bootloader/source/uboot-manifest.json`。
- 构建产物：`bootloader/idbloader.img`、`bootloader/u-boot-dtb.img`；配套源码材料附有制作时使用的这两个文件。

U-Boot 主体使用 GPLv2，部分文件允许后续版本或使用其他许可；以源码内 `Licenses/README`、许可文本与各文件声明为准。两个 loader 从上游原版 Firefly 配置构建，使用 RAM 环境、保留串口输出，并从 SD 目标读取启动配置。完整源码、配置及重建脚本一并提供。

## 名称与资料

Ubuntu、GNOME、Firefly 等名称用于说明发行版、桌面和硬件兼容目标。各项目名称、标识及包内素材的权利属于各自权利人。本材料中的项目级 MIT 许可证不授予这些名称或素材的额外权利。
