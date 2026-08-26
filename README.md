# hlasm-emulator

HLASMプログラムを実行する、最小限のz/Architectureサブセット・エミュレーター。
背景・設計判断・既知の制約は [HANDOVER.md](HANDOVER.md) を参照。

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
.venv/bin/hlasm-emulator path/to/program.hlasm          # 実行して最終レジスタ状態を表示
.venv/bin/hlasm-emulator path/to/program.hlasm --trace  # 1命令ごとにレジスタダンプ
```

## DAPアダプター（VSCode等のデバッガー接続用）

`hlasm-dap`はstdin/stdout上でDebug Adapter Protocolを話す独立プロセス。
VSCode拡張としてのパッケージングはまだ無いので、現状は生のDAPクライアント
（またはDAP対応の汎用ツール）から接続する。

```bash
.venv/bin/hlasm-dap
```

対応リクエスト・既知の制約はHANDOVER.md §8-1を参照。

## テスト

```bash
.venv/bin/python -m pytest tests/ -v
```
