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

## テスト

```bash
.venv/bin/python -m pytest tests/ -v
```
