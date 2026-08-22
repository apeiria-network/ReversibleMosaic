# 第三方许可证与通知清单

本目录是 v1.0.0 内部 Release 的交付材料。它覆盖
[发行说明](../docs/release-notes.md) §6 中列出的 APK 运行时组件；PC 开发工具和 Android
SDK/NDK 不会随 APK 分发，因此只在发行说明中列示。

| 组件 | 版本或来源 | 许可证 / 本目录文件 |
|---|---|---|
| CPython | 3.14，p4a recipe | PSF-2.0 — `PSF-2.0.txt` |
| Kivy、PyJNIus、libffi | p4a recipe | MIT — `MIT.txt` |
| SDL2 | p4a recipe | zlib — `ZLIB.txt` |
| NumPy、libwebp、libjpeg-turbo | 2.3.0 / p4a recipe | BSD-3-Clause — `BSD-3-Clause.txt` |
| Pillow | 11.3.0 | HPND — `HPND.txt` |
| Cython、OpenSSL 3.x | 3.2.9 / p4a recipe | Apache-2.0 — `Apache-2.0.txt` |
| libpng | p4a recipe | libpng License — `LIBPNG.txt` |
| SQLite | p4a recipe | Public domain — `PUBLIC-DOMAIN.txt` |
| WenQuanYi Micro Hei | `assets/fonts/wqy-microhei.ttc` | Apache-2.0 或 GPL-3+ Font Exception；完整随 APK 位于 `reversible_mosaic/assets/fonts/LICENSE.txt` |

本清单以实际 Release 构建的 p4a recipe 版本为准；变更 `buildozer.spec` 的运行时依赖或
p4a recipe 后，必须同步更新本表、补充相应许可原文，并更新发行说明 §6。
