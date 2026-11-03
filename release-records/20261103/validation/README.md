# 2026-11-03 镜像制作与验证记录

目标为原版 Firefly-RK3288，TF 卡、HDMI 和 GNOME 桌面。

- Ubuntu Base 22.04.5 armhf：SHA-256 与 Ubuntu CD Image 签名核对通过，签名记录见 `ubuntu-base-signature.txt`。
- Ubuntu ARM 用户空间：QEMU chroot 中安装完成 848 个软件包，`apt-get check` 成功，`dpkg --audit` 输出为空。运行得到 `GNOME Shell 42.9` 和 `armhf`；图形初始设置程序的命令行帮助正常返回。
- Linux 6.6.161-firefly：ARM 交叉编译及模块安装成功，206 项配置与请求一致，1,015 个模块；DTB 的电源、SD、HDMI、音频、GPU 连接检查通过。详见两个 kernel 审查文件。
- FAT32 启动分区：`fsck.vfat -n` 退出状态 0。
- 完整 8 GiB 整盘镜像：独立验证脚本 89 项全部通过，详见 `validation.json`。检查了真实 MBR 分区、loader 字节与 CRC、实际 FAT 启动文件、内核/DTB/initramfs、完整根分区哈希和只读 ext4 fsck，以及包状态、桌面会话、Panfrost 库、账号、服务权限与模块版本。
- root 密码锁定，无预置普通用户；SSH 默认关闭，镜像中无 SSH 主机密钥、构建机器 ID、随机种子或 ARM 构建模拟器。

构建使用 x86_64 Linux、Ubuntu 22.04 Docker 工具容器、ARM 交叉编译及 QEMU 用户态 chroot。2026-11-03，板卡持有者确认尚未刷卡，本版先行公开发布。下一项硬件验收是原版 Firefly 的 TF 卡 + HDMI 冷启动，完成 GNOME 向导并检查桌面、USB 输入、网线、声音及 GPU renderer。

交付镜像压缩为 1,151,731,968 字节，`gzip -t` 退出状态 0。未压缩镜像 SHA-256 与组装后独立验证记录一致；交付文件校验值见上级 `SHA256SUMS`。源码包的 gzip 完整性、43 项材料校验和重建入口检查通过。

公开发布补充：镜像内848个二进制包的501个精确源码版本已从签名Jammy索引获取，1,555个文件的大小和SHA-256全部通过；501个.dsc的1,054条归档引用完整。三份独立tar打包时再次逐字节核验，报告与清单见发布记录目录。公开仓库的`rebuild.sh fetch`实际下载Ubuntu Base、Linux和U-Boot并完成哈希核对，`rebuild.sh check`通过；源码收集工具在公开仓库执行`--plan-only`，结果501/501版本、缺失0。Release附件校验值见`../RELEASE-SHA256SUMS`。
