# Ubuntu GNOME for Firefly-RK3288

为**原版 Firefly-RK3288**制作的 Ubuntu 22.04.5 armhf 桌面镜像，使用 GNOME 42.9、Linux 6.6.161-firefly 和 Mesa / Panfrost。通过 **TF（microSD）卡启动、HDMI 显示器输出**，配合 USB 键盘和鼠标使用。

本仓库保存板级配置、设备树、构建脚本和版本验证记录。Firefly-RK3288 Reload 及其他 RK3288 板卡需要各自适配。本版系统与数据均放在 TF 卡上，Linux 设备树禁用板载 eMMC。

## 下载与首次开机

下载 [v0.1.0-alpha](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/tag/v0.1.0-alpha) 中的镜像和校验文件：

- [Ubuntu GNOME 镜像 `.img.gz`](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/download/v0.1.0-alpha/ubuntu-22.04.5-gnome-firefly-rk3288-sd-20261103-alpha.img.gz)
- [SHA256SUMS](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/download/v0.1.0-alpha/SHA256SUMS)
- [配套源码材料](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/download/v0.1.0-alpha/firefly-rk3288-ubuntu22.04-gnome-sources.tar.gz)

准备至少 **16 GB TF 卡**、读卡器、HDMI 显示器和 USB 键鼠，建议接网线并安装散热片。未压缩镜像为 8 GiB，首次启动会把根分区扩展到卡上可用空间。

1. 用 [balenaEtcher](https://etcher.balena.io/) 选择 `.img.gz` 和目标 TF 卡，写入并等待校验完成。写入会清空这张卡。
2. 板子断电后插卡，连接 HDMI、键鼠和网线；打开显示器，再给板子通电。
3. 等待 GNOME 初始设置，创建自己的用户名和密码，进入桌面。系统预设简体中文，向导可能跳过语言选择页。

镜像不预置普通账号或统一密码，root 账号锁定。SSH 默认关闭，需要时在桌面终端运行 `sudo systemctl enable --now ssh`。更多设置、更新方法及无画面排查见[刷卡与首次开机](docs/README-刷卡与首次开机.md)。

## 系统组成

| 组件 | 本版配置 |
| --- | --- |
| 用户空间 | Ubuntu Base 22.04.5，Jammy armhf 软件仓库 |
| 桌面 | GNOME Shell 42.9、GDM、GNOME Initial Setup，Wayland 与 Xorg 会话 |
| 内核 | Linux 6.6.161-firefly，原版 Firefly 设备树及 HDMI 音频配置 |
| 引导 | U-Boot v2024.01，原版 Firefly 配置，TF 卡启动目标 |
| 图形 | Mesa / Panfrost，Mali-T764 开源驱动 |
| 常用功能 | 中文字体与拼音输入法、文件管理器、终端、Epiphany 浏览器、NetworkManager、zram |

用户空间通过 `apt` 更新。自编译内核需要连同模块、initramfs、DTB 和 TF 卡启动文件一起更新，具体步骤见[重建文档](docs/REBUILD.md)。

## 构建与验证

使用 x86_64 Linux、Docker Engine、Python 3、至少 60 GB 可用磁盘和建议 8 GB 内存。从仓库开始构建：

```sh
git clone https://github.com/hehuang139/ubuntu-firefly-rk3288.git
cd ubuntu-firefly-rk3288
./rebuild.sh fetch
./rebuild.sh check
./rebuild.sh all
```

`fetch` 按 `sources.json` 下载固定版本的 Ubuntu Base、Linux 与 U-Boot 归档并核对 SHA-256，仅需要 Python 3 和网络；`all` 也会先执行这一阶段。Release 的配套源码材料已经包含这三份输入归档，可供离线复制和核对；工具容器与 Ubuntu 软件包安装仍需访问相应仓库。

构建过程包括工具容器、内核与 U-Boot 交叉编译、QEMU ARM chroot 内安装 Ubuntu 桌面、生成 initramfs，以及组装和验证整盘镜像。`rootfs` 和 `finalize` 阶段使用特权容器挂载 chroot 所需目录。输出位于 `artifacts/`；分步重建、依赖与目录说明见 [REBUILD.md](docs/REBUILD.md)。

2026-11-03 版本的实际结果：

- Ubuntu Base 的 SHA-256 与 Ubuntu CD Image 签名核对通过；ARM chroot 内完成 848 个软件包安装，`apt-get check` 成功，`dpkg --audit` 输出为空，运行得到 `GNOME Shell 42.9`。
- Linux 交叉编译与模块安装成功，206 项配置核对一致，生成 1,015 个内核模块；编译后的设备树完成电源、SD、HDMI、音频与 GPU 连接检查。
- 完整 8 GiB 镜像的 **89 项独立检查全部通过**，包括分区与 loader、FAT 启动文件、内核和 initramfs、根文件系统、包状态、桌面会话、Panfrost 库、账号及服务配置；镜像压缩完整性检查通过。

实际[包版本清单](release-records/20261103/packages.tsv)、[对应源码包清单](release-records/20261103/source-packages.tsv)和[完整验证记录](release-records/20261103/validation/README.md)保存在 `release-records/20261103/`。APT 仓库和 Docker 基础镜像会更新，重建时以新生成的包清单和镜像 manifest 记录实际版本。

当前硬件验收入口是**原版板的 TF 卡 + HDMI 冷启动**：完成 GNOME 首次建号，再记录桌面显示、USB 键鼠、有线网络、HDMI 声音及 `glxinfo -B` 的 renderer。板上 Wi-Fi、蓝牙及其他接口按实际结果继续补充记录。

## 文档与许可

- [刷卡与首次开机](docs/README-刷卡与首次开机.md)
- [构建组成、分区与启动过程](docs/BUILDNOTES.md)
- [完整重建与内核更新](docs/REBUILD.md)
- [内核配置与构建说明](kernel/KERNEL_BUILD.md)
- [组件来源与许可](THIRD_PARTY.md)

[MIT 许可证](LICENSE)仅适用于本项目独立编写的构建和组装脚本。Linux、U-Boot、设备树、上游派生配置、Ubuntu 软件包、固件、字体和图片保留各自许可；具体边界与对应源码获取方式见 [THIRD_PARTY.md](THIRD_PARTY.md)。
