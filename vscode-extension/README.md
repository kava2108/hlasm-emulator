# HLASM Emulator Debugger (VSCode拡張)

`hlasm-emulator`（`../hlasm_emulator/dap`）をDebug Adapter Protocol経由で
VSCodeのデバッグUIに接続する薄いグルー拡張。実際のデバッグロジックは
すべてPython側（`hlasm-dap`）にあり、この拡張はそれを子プロセスとして
起動するだけ。TypeScriptビルドは不要（プレーンJSで完結）。

`.hlasm`/`.asm`/`.mlc`ファイル向けの構文ハイライト（`syntaxes/hlasm.tmLanguage.json`、
ラベル/命令/文字列リテラル/コメントの配色）も同梱。

## 前提

リポジトリルート（`hlasm-emulator/`）で、README.mdの手順通りに
`.venv`をセットアップ済みであること（`hlasm_emulator`と`hlasm_parser`が
importできる状態）。

## インストール

事前ビルド済みの`hlasm-emulator-debug-0.1.0.vsix`がある場合:

1. VSCodeのコマンドパレットで `Extensions: Install from VSIX...` を実行
2. この`.vsix`ファイルを選択

自分でパッケージし直す場合:

```bash
cd vscode-extension
npx --yes @vscode/vsce package --allow-missing-repository
```

## 使い方

0. お試し用に`../examples/sum_loop.hlasm`が同梱されている
1. `.hlasm`/`.asm`/`.mlc`拡張子のHLASMソースファイルを開く
2. 実行/デバッグビュー →「実行とデバッグ」→ `HLASM Emulator` を選択
   （`launch.json`が無ければ自動的に開いているファイルを対象にする）
3. ブレークポイントをガター（行番号の左）に設定してからデバッグ開始
4. 変数ビューに `Registers`（R0-R15, CC, IP）と `Data`（DC/DSラベルの
   現在値）が表示される。ウォッチ式やホバーでも `R1` や `COUNT` のような
   レジスタ名/データラベル名を評価できる

`launch.json`を手書きする場合の例:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "hlasmEmulator",
      "request": "launch",
      "name": "HLASMを実行",
      "program": "${workspaceFolder}/sum.hlasm",
      "stopOnEntry": true
    }
  ]
}
```

## Pythonインタプリタの解決順序

1. VSCode設定 `hlasmEmulator.pythonPath`（明示指定）
2. `<ワークスペース>/.venv/bin/python`（Windowsは`.venv\Scripts\python.exe`）
3. PATH上の`python3`（Windowsは`python`）

`hlasm_emulator`がimportできないインタプリタだと`launch`が
`ModuleNotFoundError`で失敗するので、その場合は設定1で明示するか、
ワークスペード直下に`.venv`を作る。

## 既知の制約

DAPサーバー本体の制約（単一スタックフレーム、条件付きブレークポイント
未対応など）は `../HANDOVER.md` §8-1を参照。この拡張自体はまだ
Marketplaceに公開しておらず、`.vsix`の手動インストールのみ対応。
