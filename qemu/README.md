# 在 QEMU 上运行 Firefly-RK3288 的 Ubuntu GNOME

`firefly-rk3288` 是 QEMU 10.2.0 的独立实验板型。它使用 2 GiB 内存、4 个 Cortex-A15 模拟核（提供 RK3288 所用的 ARMv7-A 指令集）、24 MHz 通用定时器，以及按 RK3288 地址映射连接的 GICv2 和 UART2，并用虚拟 PL031 RTC 在开机时读取宿主机时间。虚拟磁盘、显示、键盘、鼠标和随机数设备走 VirtIO MMIO，显示通过本机 VNC 访问，默认不配置网卡；开启 SSH 时启用 VirtIO 网卡。

QEMU 直接加载专用 Linux `zImage` 和实验 DTB，从原版 8 GiB Ubuntu 22.04.5 armhf 镜像的第二个分区启动。模拟内核基于发行版的 `6.6.161-firefly` 配置，启用 VirtIO GPU、输入和随机数驱动，并保留发行版的 VirtIO 网卡驱动。原镜像以只读方式挂载，首次设置和日常改动保存在 qcow2 写时复制盘。启动参数只在模拟器中屏蔽实板专用的 TF 扩容服务。

实验用于验证 Ubuntu 用户空间、GNOME 和虚拟键鼠。Firefly 的 BootROM、DDR 初始化、U-Boot、TF 控制器、HDMI 和 Mali GPU 不在本模型的范围；实验内核、DTB 和 qcow2 文件不能用于实板刷卡。

## 构建并启动

需要 x86_64 Linux、Docker Engine、`curl`、`gzip`、`sha256sum` 和约 16 GiB 可用磁盘。操作时在仓库根目录，使用普通用户。下面用原版 `v0.1.0-alpha` 的完整镜像。

```sh
JOBS=12 ./qemu/prepare.sh
mkdir -p artifacts
name=ubuntu-22.04.5-gnome-firefly-rk3288-sd-20261103-alpha
base=https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/download/v0.1.0-alpha
curl -fL "$base/$name.img.gz" -o "artifacts/$name.img.gz"
printf '%s  %s\n' \
  96d90553dffce3c133fc42c02e06ef522f7eb2ed46a1ed8999b581635ae8d456 \
  "artifacts/$name.img.gz" | sha256sum -c -
gzip -dk "artifacts/$name.img.gz"
./qemu/run.sh "artifacts/$name.img"
```

`prepare.sh` 校验 QEMU 与 Linux 下载归档的 SHA-256；`run.sh` 校验解压后镜像的 SHA-256。已经下载并解压过镜像时，直接运行最后一条即可。脚本只接收普通文件，不写宿主机磁盘设备。输出默认在 `qemu/work/`；可通过 `FIREFLY_QEMU_WORK` 改用其他目录。

在 Remmina 等 VNC 客户端输入 **`127.0.0.1:5908`**（Remmina 也可执行 `remmina -c vnc://127.0.0.1:5908`）。第一次启动等待 GNOME 设置向导，点「开始配置」，选择输入法和隐私选项。在「时区」页输入 `sha`，从下拉列表选 **Shanghai, Shanghai, 中国**，然后创建自己的账号和密码。进入桌面后：

- 点左上角「活动」或按 `Super` 打开概览，再点底部九宫格查看应用。镜像预装文件管理器、终端、文本编辑器和 GNOME Web。
- 用「文件」浏览家目录，从应用列表搜索「终端」打开命令行。
- 右上角系统菜单中可以关机。关闭 VNC 窗口仅断开连接；再次连接可继续操作。

如果界面尚未出现，查看 `qemu/work/vm/serial.log` 和 `qemu/work/vm/qemu.log`。x86_64 主机通过 TCG 模拟 ARM，桌面用软件渲染，首次启动到设置向导约需数分钟。关机后按同样命令启动，会继续使用原有 qcow2。要另起一次干净的测试，指定新的状态目录和 VNC 显示号，例如 `./qemu/run.sh "artifacts/$name.img" qemu/work/another-vm 9`，对应 `127.0.0.1:5909`。

在 x86_64 上运行 ARM 来宾时，QEMU 用多线程 TCG 翻译指令，GNOME 在来宾 CPU 上绘制桌面。默认分辨率为 `1024x768`；启动前可设 `FIREFLY_QEMU_SCREEN=800x600`，分辨率降低后每次重绘的像素更少。也可设为 `1280x800`。要关闭 GNOME 动画，可用来宾账号运行：

```sh
gsettings set org.gnome.desktop.interface enable-animations false
```

也可以在「设置 → 显示器」切换分辨率。`FIREFLY_QEMU_CPU_LIMIT` 和 `FIREFLY_QEMU_RAM_LIMIT` 可以限制容器占用宿主机的资源（如 `20` 和 `47g`）；模拟板卡仍有 4 核和 2 GiB 内存。

## 通过 SSH 登录

先在首次设置中创建自己的账号。关机后，使用原来的状态目录重新启动，在启动命令中指定本机转发端口：

```sh
FIREFLY_QEMU_SSH_PORT=2222 ./qemu/run.sh "artifacts/$name.img"
ssh -p 2222 your_user@127.0.0.1
```

将 `your_user` 换成首次设置中创建的用户名，连接时输入对应密码。脚本只在本机 `127.0.0.1` 监听并转发到来宾 TCP 22，来宾网卡通过 QEMU 的隔离网络领取地址。此模式不提供来宾上网，也不向局域网开放 SSH。通过启动参数启动镜像内已有的 SSH 服务；不改动发行镜像的默认设置。需要从宿主机进入串口登录提示时，可执行 `socat STDIO,raw,echo=0 UNIX-CONNECT:qemu/work/vm/console.sock`。

## 验证记录

在 x86_64 Linux 上从 `v0.1.0-alpha` 的原始镜像启动 Ubuntu 22.04.5 armhf。[启动日志](evidence/serial-excerpt.txt)记录了四核、VirtIO 磁盘、虚拟 RTC 和 GNOME 的加载。在 VNC 中完成[首次设置](evidence/gnome-first-setup.png)，创建测试账号，点[开始使用 Ubuntu](evidence/gnome-setup-complete.png)后进入[应用列表](evidence/gnome-apps.png)。重启时启用 800×600 和 SSH，随后通过 `ssh -p 2222` 使用首次设置创建的账号成功登录；`uname -m` 返回 `armv7l`，`systemctl is-active ssh` 返回 `active`。原始镜像继续以只读方式挂载。

模型 C 源码和 DTS 使用 GPL-2.0-or-later，新增构建及启动脚本使用 MIT。上游 QEMU 和 Linux 源码由 `prepare.sh` 按固定版本获取；Ubuntu 用户空间与实板镜像的对应源码见[发布说明](../docs/CORRESPONDING-SOURCES.md)。
