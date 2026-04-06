# filament-build

[Google Filament](https://github.com/google/filament) をソースからマルチプラットフォーム向けにビルドし、GitHub Releases で配布するプロジェクト。

## 背景

Filament 公式のプリビルトバイナリは iOS simulator arm64 (`platform: iossim`) に対応していない。Apple Silicon Mac の iOS シミュレーターは arm64 で動作するが、公式バイナリの arm64 スライスは `platform 2 (ios)` タグが付いておりリンクできない。`EXCLUDED_ARCHS` で arm64 を除外し Rosetta 2 経由で実行する回避策は、Apple が Rosetta の汎用利用を段階的に廃止するため期限がある。

このプロジェクトは公式が提供していない iOS simulator arm64 を含む、ネイティブアプリ開発向けプラットフォームのプリビルトバイナリを提供する。

## 対応プラットフォーム

| ターゲット | アーキテクチャ | ランナー | 公式提供 |
|:---|:---|:---|:---|
| macOS | arm64 | `macos-latest` | あり |
| iOS device | arm64 | `macos-latest` | あり |
| iOS simulator | arm64 | `macos-latest` | **なし** |
| Android | arm64-v8a | `ubuntu-latest` | あり |

Filament 公式は上記に加え Linux (x86_64/ARM)、Windows、Web (WebAssembly) のプリビルトバイナリも提供している。このプロジェクトではそれらはカバーしない。

## ダウンロード

プリビルトバイナリは [Releases](../../releases) ページから取得できる。

各リリースに含まれる成果物:

```
filament-v{version}-macos_arm64.tar.gz
filament-v{version}-ios_device_arm64.tar.gz
filament-v{version}-ios_simulator_arm64.tar.gz
filament-v{version}-android_arm64_v8a.tar.gz
```

各アーカイブの構成:

```
filament/
├── lib/          # 静的ライブラリ (.a)
├── include/      # ヘッダーファイル
├── LICENSE
├── NOTICE
└── VERSIONS
```

## ローカルビルド

必要なもの:
- Python 3
- CMake, Ninja
- Xcode (macOS/iOS ターゲット)
- Android NDK (Android ターゲット、`ANDROID_HOME` の設定が必要)

```bash
# ビルド
python3 run.py build <target>

# パッケージング
python3 run.py package <target>
```

ターゲット: `macos_arm64`, `ios_device_arm64`, `ios_simulator_arm64`, `android_arm64_v8a`

## CI/CD

GitHub Actions でビルドを自動化している。バージョンタグ (`v*`) を push すると自動で Release が作成される。

`workflow_dispatch` で個別プラットフォームの手動ビルドも可能。

## バージョニング

Filament のアップストリームバージョンに追従する。`VERSION` ファイルで管理:

- `FILAMENT_VERSION` - Filament のバージョン
- `FILAMENT_COMMIT` - checkout する git タグ
- `FILAMENT_BUILD_VERSION` - リビルド用サフィックス付きバージョン (例: `1.70.2.0`)

## ライセンス

Apache License 2.0

このプロジェクトが利用しているソフトウェアのライセンスの詳細は [NOTICE](NOTICE) を参照。
