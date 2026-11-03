# Independent Firefly Ubuntu kernel config and DTB audit

Executed 2026-11-03 against:

- `build/.config`, resolved by Linux 6.6.161 olddefconfig.
- `build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb`.

Parsed `.config` with Python and checked required symbols. Queried compiled DTB with `fdtget` from the `firefly-batocera-build:20261102` Docker image. This audit read existing artifacts; it did not alter kernel sources or the rootfs.

## Results

All required symbols checked resolve to built-in (`y`) or module (`m`):

```
DEVTMPFS=y DEVTMPFS_MOUNT=y CGROUPS=y INOTIFY_USER=y
SIGNALFD=y TIMERFD=y EPOLL=y UNIX=y SYSFS=y PROC_FS=y FHANDLE=y
NET_NS=y USER_NS=y SECCOMP=y SECCOMP_FILTER=y TMPFS_XATTR=y
EXT4_FS=y EXT4_FS_POSIX_ACL=y CRYPTO_USER_API_HASH=y CRYPTO_HMAC=y
CRYPTO_SHA256=y ROCKCHIP_IOMMU=y CMA=y DMA_CMA=y CMA_SIZE_MBYTES=128
REGULATOR_ACT8865=y REGULATOR_FAN53555=y MMC_DW_ROCKCHIP=y
DRM_ROCKCHIP=y ROCKCHIP_DW_HDMI=y DRM_PANFROST=m
SND_SIMPLE_CARD=y SND_SOC_ROCKCHIP_I2S=y DRM_DW_HDMI_I2S_AUDIO=y
INPUT_EVDEV=y USB_HID=y VT=y VT_CONSOLE=y UNIX98_PTYS=y
SWAP=y ZRAM=m CRYPTO_LZ4=y RTC_DRV_HYM8563=y
DWMAC_ROCKCHIP=y REALTEK_PHY=y USB_STORAGE=y HIGHMEM=y SMP=y
BINFMT_ELF=y BINFMT_SCRIPT=y
```

`RT_GROUP_SCHED` and `FW_LOADER_USER_HELPER` disabled as intended. Panfrost and ZRAM modules must accompany this kernel in `/lib/modules/6.6.161-firefly/` with depmod metadata.

Compiled DTB properties:

| Node/property | Actual value |
|---|---|
| `/ model` | `Firefly-RK3288` |
| `/ compatible` | `firefly,firefly-rk3288 rockchip,rk3288` |
| `/chosen stdout-path` | `serial2:115200n8` |
| `/mmc@ff0f0000 status` | disabled |
| `/mmc@ff0c0000 status` | okay |
| `/hdmi@ff980000 status` | okay |
| `/i2s@ff890000 status` | okay |
| `/gpu@ffa30000 status` | okay |
| `/vop@ff930000 status` | okay |
| `/vop@ff940000 status` | okay |
| `/hdmi-sound/simple-audio-card,cpu sound-dai` | 0x95 |
| `/i2s@ff890000 phandle` | 0x95 |
| `/hdmi-sound/simple-audio-card,codec sound-dai` | 0x96 |
| `/hdmi@ff980000 phandle` | 0x96 |

HDMI sound card DAI references therefore resolve to the intended CPU I2S and HDMI codec nodes. No static blocker found in the reviewed configuration/device tree.

## Example commands used

```
fdtget -t s build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb / model
fdtget -t s build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb / compatible
fdtget build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb /chosen stdout-path
fdtget build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb /mmc@ff0f0000 status
fdtget -t x build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb /hdmi-sound/simple-audio-card,cpu sound-dai
fdtget -t x build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb /i2s@ff890000 phandle
```
