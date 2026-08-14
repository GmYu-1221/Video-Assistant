# Bundled Font Assets

All fonts in this directory are loaded through `src/fonts/loadFonts.ts`. Compositions must use the semantic registry rather than declaring local `@font-face` rules.

| Registry ID | Font | Source | License |
| --- | --- | --- | --- |
| `source-han-serif` | Source Han Serif SC | [Adobe Source Han Serif](https://github.com/adobe-fonts/source-han-serif) | SIL Open Font License 1.1 (`source-han-serif/LICENSE.txt`) |
| `lxgw-wenkai` | LXGW WenKai 1.522 | [LXGW WenKai](https://github.com/lxgw/LxgwWenKai/releases/tag/v1.522) | SIL Open Font License 1.1 (`lxgw-wenkai/OFL.txt`) |
| `zcool-qingke-huangyou` | ZCOOL QingKe HuangYou | [Google Fonts](https://fonts.google.com/specimen/ZCOOL+QingKe+HuangYou) | SIL Open Font License 1.1 (`zcool-qingke-huangyou/OFL.txt`) |
| `zcool-kuaile` | ZCOOL KuaiLe | [Google Fonts](https://fonts.google.com/specimen/ZCOOL+KuaiLe) | SIL Open Font License 1.1 (`zcool-kuaile/OFL.txt`) |
| `ma-shan-zheng` | Ma Shan Zheng | [Google Fonts](https://fonts.google.com/specimen/Ma+Shan+Zheng) | SIL Open Font License 1.1 (`ma-shan-zheng/OFL.txt`) |
| `noto-sans-sc` | Noto Sans SC | [Google Fonts](https://fonts.google.com/specimen/Noto+Sans+SC) | SIL Open Font License 1.1 (`noto-sans-sc/OFL.txt`) |

The font files are committed with the project so Remotion output does not depend on fonts installed on macOS, CI, or Linux render hosts.
