# hlasm-emulator

[![test](https://github.com/kava2108/hlasm-emulator/actions/workflows/test.yml/badge.svg)](https://github.com/kava2108/hlasm-emulator/actions/workflows/test.yml)

HLASMプログラムを実行する、最小限のz/Architectureサブセット・エミュレーター。
背景・設計判断・既知の制約は [HANDOVER.md](HANDOVER.md) を参照。ライセンスは
[MIT](LICENSE)。

## セットアップ

`hlasm-parser`（`/home/ubuntu/workspace/hlasm-parser`）が兄弟ディレクトリに
必要です。

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../hlasm-parser
.venv/bin/pip install -e .
.venv/bin/pip install pytest
```

## 実行

```bash
.venv/bin/hlasm-emulator examples/sum_loop.hlasm          # 実行して最終レジスタ状態を表示
.venv/bin/hlasm-emulator examples/sum_loop.hlasm --trace  # 1命令ごとにレジスタダンプ
```

## DAPアダプター（VSCode等のデバッガー接続用）

`hlasm-dap`はstdin/stdout上でDebug Adapter Protocolを話す独立プロセス。

```bash
.venv/bin/hlasm-dap
```

対応リクエスト・既知の制約はHANDOVER.md §8-1を参照。

## VSCode拡張

`vscode-extension/`にVSCodeのデバッグUIから`hlasm-dap`を使うための拡張が
ある。インストール手順・使い方は`vscode-extension/README.md`を参照。

## テスト

```bash
.venv/bin/python -m pytest tests/ -v
```
