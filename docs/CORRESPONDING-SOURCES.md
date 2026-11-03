# Ubuntu 软件包对应源码

本版镜像的 848 个二进制软件包映射到 501 个精确源码版本。Release 随镜像提供完整的 1,555 个原始源码文件，包括 `.dsc`、上游源码和 Debian/Ubuntu 打包补丁，合计 3,425,999,610 字节。

## 下载和校验

从 [v0.1.0-alpha Release](https://github.com/hehuang139/ubuntu-firefly-rk3288/releases/tag/v0.1.0-alpha) 下载：

- `ubuntu22.04-jammy-corresponding-sources-01-of-03.tar`，约 1.47 GB。
- `ubuntu22.04-jammy-corresponding-sources-02-of-03.tar`，约 1.49 GB。
- `ubuntu22.04-jammy-corresponding-sources-03-of-03.tar`，约 0.53 GB。
- `SHA256SUMS`，覆盖镜像、构建材料和这三份归档。

每份 tar 可以独立解压，同一个源码包的文件完整放在同一份归档中。三份合起来覆盖整个用户空间。每份都有 `README.txt`、包清单、文件清单、签名仓库索引及自己的 `SHA256SUMS`。例如：

```sh
tar -xf ubuntu22.04-jammy-corresponding-sources-01-of-03.tar
cd ubuntu22.04-jammy-corresponding-sources-01-of-03
sha256sum -c SHA256SUMS
```

源码原文件位于 `archives/pool/`。查找对应软件包的 `.dsc` 后，可用 `dpkg-source -x 文件.dsc` 解包源码及 Ubuntu 补丁。源码内的 `debian/` 保存打包与构建配方，各文件和 `debian/copyright` 保存许可证信息。

Linux 6.6.161 与 U-Boot v2024.01 由本项目单独交叉编译，对应完整源码、配置和配方放在 `firefly-rk3288-ubuntu22.04-gnome-sources.tar.gz` 中。

## 本次验证

源码获取工具用 Ubuntu archive keyring 验证了 4 份 Jammy `InRelease` 签名，核对 16 份 `Sources` 索引的大小与 SHA-256，再据其读取精确版本的源码文件列表。全部 1,555 个文件完成大小和 SHA-256 校验；501 份 `.dsc` 中的 1,054 条归档引用均与文件清单一致。打包时再次逐字节核对原文件摘要，并检查归档相对路径、所有权和条目数量。

[完整源码 manifest](../release-records/20261103/ubuntu-source-manifest.json)记录原始 URL、版本和文件摘要；[下载验证记录](../release-records/20261103/ubuntu-source-download-verification.json)和[打包记录](../release-records/20261103/ubuntu-source-archive-report.json)记录实际结果。软件包许可证见 [THIRD_PARTY.md](../THIRD_PARTY.md)。

## 为新镜像收集对应源码

使用目标镜像生成的 `source-packages.tsv`，在装有 Python 3、`gpgv` 和 Ubuntu archive keyring 的 Linux 主机执行：

```sh
python3 scripts/fetch-ubuntu-sources.py source-packages.tsv --plan-only
python3 scripts/fetch-ubuntu-sources.py source-packages.tsv --jobs 8
python3 scripts/package-ubuntu-sources.py \
  --binary-source-tsv source-packages.tsv \
  --output-dir artifacts/corresponding-sources
```

默认缓存位于 `cache/ubuntu-sources/`，下载工具复用已通过哈希核对的文件。工具核对精确源码版本；如仓库已移除某个版本，会列出缺失项并停止，便于从该次发布保留的归档恢复。
