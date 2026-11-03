# Ubuntu 22.04 GNOME Firefly-RK3288 构建说明

## 组成与来源

本版使用 Ubuntu Jammy 的 armhf 用户空间、自编译 Firefly 内核和原版 Firefly U-Boot，生成可写入 TF 卡的整盘镜像。

| 组件 | 版本 / 来源 |
| --- | --- |
| 用户空间起点 | Ubuntu Base 22.04.5，armhf |
| 桌面 | Jammy 仓库 GNOME 42、gdm3、gnome-initial-setup、accountsservice |
| 浏览器 | Ubuntu 仓库 Epiphany |
| 内核 | kernel.org Linux 6.6.161，配置版本后缀 `-firefly` |
| 引导 | U-Boot v2024.01，`firefly-rk3288_defconfig` |
| 包仓库 | 中科大 Ubuntu Ports 镜像，Ubuntu 官方签名元数据 |

Ubuntu Base 文件：`ubuntu-base-22.04.5-base-armhf.tar.gz`。

SHA-256：

```text
fd77cb0659326b75c08ce06b6b8649d2e13ef9a704a8e9212fec32cb97d42add
```

其 `SHA256SUMS` 通过 Ubuntu CD Image 签名验证，密钥指纹为：

```text
8439 38DF 228D 22F7 B374 2BC0 D94A A3F0 EFE2 1092
```

Linux 源码包：`linux-6.6.161.tar.xz`，SHA-256：

```text
7d34405be5cd4989b2a5e9cbefa798e3a175218901271e034af3fe4e840b71c6
```

U-Boot 来自上游 v2024.01，使用原版 Firefly 配置和板级 DDR 参数；配方、归档及配置记录位于 `bootloader/source/`。U-Boot 源码包 SHA-256：

```text
a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4
```

已构建的 Firefly loader 校验值：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| idbloader.img | 63,488 | `52cc45914527403534bd8b6f044acb29b9568c85ef22103c0bbf9afc89825335` |
| u-boot-dtb.img | 554,688 | `4f7d7171563590d7098a7c229157fadf840019003f45f29d10e41b1123ee97c4` |

## 构建过程

可执行重建入口是源码包根目录的 `./rebuild.sh all`，前置条件、分步命令和目录布局见 [REBUILD.md](REBUILD.md)。该入口通过 `FIREFLY_BUILD_IMAGE` 指定独立交叉编译工具镜像。

1. 校验 Ubuntu Base 的 SHA-256 和 Ubuntu 签名，以保留数值所有权及扩展属性的方式解压根文件系统。
2. 在隔离构建环境中用 QEMU ARM 用户态 chroot 运行 Ubuntu 的 apt/dpkg。软件包安装过程中临时禁止服务启动；使用 Ubuntu 签名的 Jammy、updates、security、backports 仓库元数据。
3. 安装 GNOME 会话、gdm3、初始设置向导、中文字体与拼音输入法、网络和常用桌面程序。保存包名、版本及架构清单。
4. 用 ARM 交叉编译器构建 Linux 6.6.161 的 `zImage`、内核模块和 Firefly 专用 DTB。启用 RK3288 电源、TF 卡、USB、HDMI、GMAC 与 Panfrost 所需驱动；设备树描述 HDMI 声卡，并禁用 Linux eMMC 节点。
5. 安装模块，生成匹配内核的 initramfs；把系统服务、网络、首次扩容、GDM 和 SSH 配置写入根文件系统。
6. 清理安装缓存、临时模拟器、构建 DNS 配置、机器 ID、SSH 主机密钥及日志。首次开机生成每张卡自己的机器标识；SSH 启用时生成主机密钥。
7. 创建普通整盘镜像文件，在固定偏移写入两个 Firefly loader，创建 FAT 启动分区和 ext4 根分区，写入内核、initramfs、DTB、extlinux 和完整根文件系统，最后压缩并生成 SHA-256。

配套构建材料中，`scripts/install-rootfs.sh` 负责包安装，`scripts/configure-rootfs.sh` 负责系统配置，`kernel/build-kernel.sh`、配置片段和 DTS 负责内核；`overlay/` 保存进入镜像的系统配置及扩容服务。最终镜像大小、分区清单和文件哈希以交付校验文件为准。

## 启动与分区

| 内容 | 位置 / 标签 | 用途 |
| --- | --- | --- |
| MBR | 镜像起始 | 分区表 |
| idbloader | 32 KiB | Firefly DDR 与早期初始化 |
| U-Boot | 8 MiB | 读取 TF 卡启动配置 |
| FAT32 启动分区 | 从 16 MiB 开始，256 MiB，`FIREFLYBOOT` | 内核、initramfs、DTB、extlinux |
| ext4 根分区 | 启动分区之后，`FIREFLY_ROOT` | Ubuntu 系统及用户数据 |

启动分区挂载为 `/boot/firmware`；根分区按标签挂载。首次扩容服务确认根设备是 MMC 的第二分区，再扩展该分区及 ext4 文件系统。扩容完成标记写入根文件系统，使后续启动跳过这一步。

U-Boot 的持久环境关闭，启动目标为其 `mmc1` SD 别名。这只控制该 U-Boot 已经运行后的启动流程；原板上未知旧引导的介质优先级由原有固件决定。

## 首次桌面与账号

GDM 启用图形初始设置，镜像中不创建常规用户，root 密码锁定。GNOME 初始设置负责创建使用者自己的管理员账号，并按实际显示的页面完成其他设置。镜像已经预设中文；Jammy 软件包的语言页可能被跳过。默认桌面会话使用 Wayland，同时保留 Xorg 会话用于图形问题比较。

SSH 服务与 socket 默认关闭，禁止 root SSH 登录。用户进入桌面后可以用 `sudo systemctl enable --now ssh` 主动开启。镜像不包含共享的 SSH 主机私钥。

默认语言和时区配置为简体中文、Asia/Shanghai；进入桌面后可通过系统设置调整语言和地区。网络由 NetworkManager 管理，TF 卡上的系统默认进入 graphical.target。

## 验证范围与交付记录

制作时直接验证基础文件签名和哈希，在 QEMU 用户态 chroot 中运行 ARM 的 apt、dpkg 及系统工具，并核对桌面组件、服务配置、账号状态、内核和模块版本。镜像结构检查包括引导程序位置、分区边界、启动配置中的文件路径、文件校验值和压缩完整性。

QEMU 用户态 chroot 用于执行 Ubuntu ARM 程序及检查用户空间，不执行 RK3288 的芯片启动流程。硬件验收入口是原版 Firefly-RK3288 的 TF 卡冷启动，依次确认 GNOME 初始设置、桌面显示、输入、以太网、HDMI 音频及 Panfrost。将这些实际结果加入后续版本记录。

APT 仓库和 Docker 基础层随时间更新，镜像创建还包含文件系统 UUID 等动态值。源码材料固定板级配方和源码归档，重建结果不保证逐字节相同；以每次生成的包清单和 manifest 记录实际内容。

## 后续更新

Ubuntu 用户空间通过签名仓库的 apt 更新。当前内核是带 Firefly 配置的自编译内核，APT 的常规软件更新不会替换它；内核升级需要同步提供新内核、模块、initramfs、DTB 与启动配置，保持版本一致。
