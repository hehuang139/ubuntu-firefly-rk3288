# Firefly-RK3288 · Ubuntu 22.04 GNOME TF 卡测试版

这份镜像面向 **原版 Firefly-RK3288**，使用 Ubuntu 22.04 Jammy 的 **32 位 armhf 系统**和 GNOME 桌面，首次通过 HDMI 显示器、USB 键盘和鼠标使用。Firefly-RK3288 Reload 和其他 RK3288 板卡需要各自的硬件描述。

本版的系统和数据位于 TF 卡。Linux 设备树禁用了板载 eMMC；原有板载系统仍由它自己的引导程序管理。

## 准备与刷卡

准备至少 **16 GB TF 卡**、读卡器、HDMI 显示器、USB 键盘与鼠标，建议同时接网线。沿用这块板子原来正常使用的电源，安装散热片并保持通风。

1. 用 balenaEtcher 选择交付的 Ubuntu `.img.gz` 文件，再选择 TF 卡，执行写入并等待校验完成。写入会清空目标卡。
2. 板子断电，插入卡，连接 HDMI、键盘、鼠标和网线。
3. 先打开显示器并切到对应 HDMI 输入，再给板子通电。
4. 首次启动会扩容 TF 卡中的根分区并初始化桌面，耗时取决于卡速。保持供电，等待 GNOME 图形初始设置出现。
5. 系统预设为简体中文，向导可能不显示语言选择页。按实际页面完成设置，创建自己的用户名和密码，然后进入桌面；之后可在系统设置中调整语言、键盘和时区。

本版没有预置日常登录账号或统一密码，root 账号处于锁定状态。首次创建的用户用于日常登录和 `sudo` 管理。

## 桌面中已包含的功能

- GNOME 42 桌面、设置、终端、文件管理器、文本编辑器、PDF 阅读器和归档管理器。
- 中文语言包、Noto CJK 字体和 IBus 拼音输入法。输入法可在“设置 → 键盘 → 输入源”中选择。
- Epiphany（Web）浏览器，使用 apt 软件包。
- NetworkManager 管理网络，首次联网建议使用网线。
- Mesa / Panfrost 图形驱动，以及 HDMI 音频的设备树配置。
- zram 压缩交换空间，帮助低内存场景。

GNOME 默认使用 Wayland 会话。如后续遇到与图形会话有关的问题，可在登录界面选择用户后，打开会话选择菜单并选择带 **Xorg** 的 GNOME 会话进行比较；显示名称会随语言设置变化。

## 更新与远程登录

联网后打开终端更新用户空间软件：

```sh
sudo apt update
sudo apt upgrade
```

APT 使用中科大 Ubuntu Ports 镜像站，软件包通过 Ubuntu 官方签名的仓库元数据验证。本版内核为针对 Firefly 构建的 `6.6.161-firefly`；常规 `apt upgrade` 更新 Ubuntu 软件包，Firefly 内核需要与模块、initramfs、设备树和启动配置成套更新，步骤见源码材料中的 `docs/REBUILD.md`。

SSH 已安装，默认关闭。需要远程管理时，在桌面登录后执行：

```sh
sudo systemctl enable --now ssh
hostname -I
```

再从电脑执行 `ssh 自己创建的用户名@板子IP`。首次启动 SSH 时生成本机主机密钥。

## 首次开机后请检查

先确认桌面显示、USB 键鼠和有线网络，再到“设置 → 声音”选择 HDMI 输出。随后打开终端查看：

```sh
uname -r
lsb_release -a
gnome-shell --version
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS
```

内核版本应包含 `6.6.161-firefly`，发行版为 Ubuntu 22.04，根分区标签为 `FIREFLY_ROOT`。图形驱动可通过 `glxinfo -B` 查看；记录 renderer 内容有助于确认 Panfrost 是否正常工作。

正常关机使用桌面系统菜单中的关机操作，或执行 `sudo poweroff`，关闭后再断电。

## 无画面或仍进入原系统

- **仍然进入 Android 或旧 Linux**：说明板载旧引导先运行了。先断电拔卡，确认原系统状态，再记录开机画面和原系统版本；需要根据现有引导确定 TF 卡切换方式。
- **一直无信号或黑屏**：检查写卡校验结果、显示器输入、HDMI 线和供电，记录状态灯及网口灯。板卡启动早期日志可进一步区分 DDR、引导程序、内核或桌面阶段的问题。
- **出现 Linux 文字后停止**：保存最后一屏完整文字，尤其是 `mmc`、`regulator`、`drm` 或根文件系统相关内容。

使用 UART 排针读日志时，先确认这块板卡的具体引脚位置。适配器使用 **3.3 V 电平**，共地、TX/RX 交叉，不连接适配器 VCC；参数为 **115200、8N1、无流控**。

## 当前验证与下一步

镜像制作使用 x86_64 Linux 主机上的 ARM 交叉编译和 QEMU 用户态 chroot 环境。Ubuntu 基础包的 SHA-256 与签名已核对；包安装、系统配置和桌面组件检查由构建记录保存。

下一项验收是这块 Firefly 的 **TF 卡 + HDMI 冷启动**，并完成 GNOME 初始设置。首启后记录桌面、键鼠、网线、HDMI 声音及图形 renderer，继续确认板上的 Wi-Fi、蓝牙和其他接口。
