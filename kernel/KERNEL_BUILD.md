# Firefly-RK3288 Ubuntu 22.04 内核构建

此内核供原版 Firefly-RK3288 的 Ubuntu 22.04 armhf HDMI 桌面镜像使用。内核为上游 Linux 6.6.161 LTS，版本字符串 `6.6.161-firefly`。kernel.org 的发布清单标注该版本发布于 2026-10-30；本次于 2026-11-03 获取。

源码下载地址：<https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.161.tar.xz>

源码 SHA-256：`7d34405be5cd4989b2a5e9cbefa798e3a175218901271e034af3fe4e840b71c6`，与同站点 `sha256sums.asc` 的条目一致。原始压缩包及校验清单随构建材料保留。

构建入口为 `build-kernel.sh`。使用 Docker 中 Ubuntu 22.04 的 GCC 11.4 ARM hard-float 交叉编译器，执行 `multi_v7_defconfig`，合并 `firefly-ubuntu22.config`，然后编译 `zImage`、模块和 Firefly 设备树。镜像构建工具名为 `firefly-batocera-build:20261102`；这只是复用已有的交叉编译工具容器，Linux 源码来自上述独立下载地址。

内核配置包含 systemd 所需的 cgroup、命名空间、seccomp、devtmpfs、文件句柄和 AppArmor；ext4、SD/MMC、ACT8846/FAN53555 电源管理、串口、USB、以太网及 Rockchip 显示驱动编入内核。Panfrost GPU、Broadcom SDIO、USB 声卡、Xbox 手柄与 ZRAM 作为模块安装。ZRAM 默认压缩算法为 LZ4，CMA 预留 128 MiB。

`rk3288-firefly-ubuntu22.dts` 直接包含 Linux 6.6.161 的原版 Firefly 设备树，仅增加 HDMI I2S 声卡、串口启动输出，将 SD 卡频率限制为 50 MHz，并将板载 eMMC 设为禁用。原版设备树中的 CPU/GPU 供电参数保持原值。

模块安装目录是 `staging/lib/modules/6.6.161-firefly`。复制进 Ubuntu 根文件系统后，需要在目标根文件系统中执行 `depmod -a 6.6.161-firefly`，再执行 `update-initramfs -c -k 6.6.161-firefly`。内核支持 Gzip、XZ、LZ4、Zstd initramfs。启动参数使用 `root=LABEL=FIREFLY_ROOT` 时，必须同时加载 initramfs。

`zImage` 为 ARM 的 bootz 格式；启动时配套加载 `rk3288-firefly-ubuntu22.dtb`。现有 Firefly U-Boot 2024.01 支持此格式。这里只构建镜像文件和模块，不操作存储设备。

`audit-kernel.py` 核对最终配置与请求片段、ARM zImage 标识、设备树头、内核版本及 Panfrost/ZRAM/无线/手柄模块版本，生成 `kernel-audit.json`。`independent-dtb-config-audit.md` 记录独立设备树及配置核对结果。完整构建输出保存在 `build.log`。

本次构建结果：交叉编译和模块安装退出状态均为 0；206 项配置请求与最终配置一致；安装 1,015 个剥离调试信息的模块，约 32 MiB。zImage 为 12,038,656 字节，设备树为 42,076 字节。ARM EABI5 / zImage 格式、设备树长度和关键模块版本检查通过。具体 SHA-256 见 `kernel-audit.json`。
