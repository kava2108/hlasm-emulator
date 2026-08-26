# hlasm-emulator 引継ぎドキュメント

作成日: 2026-08-26
作成者: Claude（前セッションでの検討を引き継ぐ形で作成）

## 1. これは何か

HLASM（High Level Assembler）プログラムを実際に**実行**するための、
最小限のz/Architectureサブセット・エミュレーター。GPR/PSWの変化を見ながら
ステップ実行し、将来的にはVSCodeのDebug Adapter Protocol (DAP) 経由で
デバッグできるようにすることを目指す。

**兄弟プロジェクト** `/home/ubuntu/workspace/hlasm-parser` との関係:

- hlasm-parser は「構造解析＋CFG」のみを扱う（意図的にこの2つに限定して
  合意済み。エミュレーション・実行意味論は最初から範囲外）。
- 本プロジェクトはその**続き**として、hlasm-parserが持つAST/CFGを
  フロントエンドとして再利用し、「実行」というレイヤーを追加する。
- 2つは別リポジトリ・別パッケージとして維持する（言語混在の可能性:
  パーサー側はPython、DAPアダプター実装はNode/TS寄りが一般的なため、
  ビルド・配布戦略が食い違う。詳細は §5 参照）。

## 2. なぜ「完全再現」ではなく「サブセット」なのか

z/Architectureの完全なエミュレーターは非現実的:

- 命令数が1,500以上（z/Arch全体）
- LE（Language Environment）、SVC呼び出し、EXCP、CICS API、
  MVSサービス（GETMAIN/FREEMAIN/STORAGE）など、z/OS環境依存の
  ランタイムサービスに実プログラムが依存している

これらを全部再現するのは1プロジェクトの規模を超える。よって:

- **やる**: GPR(R0-R15)・最低限のPSWビット・平坦なバイト配列メモリ、
  20〜30命令程度の中核命令セット（L/ST/LA/A/S/AR/SR/C/CR/B系分岐/BAL・
  BALR/MVC/MVI/CVB/CVD程度から開始）
- **やらない（当面）**: LE呼び出し規約の完全実装、SVC/EXCP/CICS、
  マルチタスク、実ストレージキー保護、浮動小数点・ベクトル命令

未対応のSVC/LE呼び出しは「ダミー実装（no-op or ログ出力して継続）」で
止めずに済ませる方針。ここは要判断ポイント（§7参照）。

## 3. hlasm-parserから再利用する資産

hlasm-parser側で既に実装済みで、そのまま使える/参照できるもの:

| hlasm-parser側 | ファイル | 用途 |
|---|---|---|
| `Program` / `Section` / `Statement` / `Operand` | `hlasm_parser/models.py` | AST。エミュレーターのIR変換の入力になる |
| `build_flow_graph()` / `BasicBlock` / `FlowEdge` | `hlasm_parser/flow/graph.py` | 基本ブロック単位のCFG。命令ポインタ(PSW)の制御移行先を求めるのに使える |
| `BRANCH_MNEMONICS`（UNCONDITIONAL/CALL_LIKE/CONDITIONAL） | `hlasm_parser/flow/graph.py` | どの命令が分岐かの分類。エミュレーターの命令ディスパッチにも流用可 |
| `RULES: dict[mnemonic, Rule(write, read, template)]` | `hlasm_parser/dataflow.py` | 命令ごとにどのオペランドを読み書きするかのテーブル。エミュレーターの命令セマンティクス実装の出発点になる（ただし現状は静的解析用の"読み書きの向き"だけで、実際の値計算ロジックは無い） |
| `Operand` / `classify()` | `hlasm_parser/operands.py` | オペランドの構文分類（即値/アドレス形式D(X,B)/レジスタ等）。実行時のアドレッシング計算のベースになる |

**重要な注意**: 上記テーブル（RULES, BRANCH_MNEMONICS）は「静的解析のため
に読み書きの向きだけを記録したもの」であり、命令の実際の演算（ビット単位
の加算、条件コード設定など）は一切実装されていない。エミュレーター側で
ゼロから実装が必要。

依存の向き: hlasm-emulator → hlasm-parser（ライブラリとして pip install
するか、モノレポ的にpath依存）。逆方向の依存は作らない。

## 4. 提案するアーキテクチャ

```
HLASM source
    │
    ▼
hlasm_parser.parser.parse()          ← hlasm-parser（既存）
    │  Program(sections, macros)
    ▼
ir/lowering.py                        ← 新規: Statement → IR命令列に変換
    │  list[IRInstruction]
    ▼
engine/cpu.py                         ← 新規: GPR/PSW/メモリ + フェッチ実行ループ
    │  ステップ実行、レジスタ変化イベント
    ▼
dap/adapter.py                        ← 新規: Debug Adapter Protocol実装
    │
    ▼
VSCode (launch.json でデバッガーとして接続)
```

パッケージ構成はhlasm-parserと同じ流儀（`pyproject.toml` + hatchling +
`[project.scripts]`）を踏襲する想定だが、DAP部分だけ別言語
（TypeScript/Node、VSCode拡張の標準）にするかはオープン。

## 5. 実装フェーズ案

1. **命令セット確定**: 最初にエミュレートする20〜30命令をリストアップし、
   各命令の正確な意味論（オペコード表・条件コード設定規則）を仕様として
   固める。ここが一番地道で重要。
2. **IR変換**: hlasm-parserの`Statement`/`Operand`を、レジスタ番号・
   実効アドレス計算済みのIR命令に変換するローワリング層。
3. **実行エンジン**: GPR配列・PSW（少なくとも命令アドレス＋条件コード）・
   バイト配列メモリ・フェッチ/デコード/実行ループ。まずCLIから
   「1ステップ実行してレジスタダンプ」ができれば動作確認可能。
4. **DAPアダプター**: ステップ実行・ブレークポイント・レジスタ表示・
   メモリダンプ・ウォッチ式。VSCode拡張のlaunch設定と繋ぐ。
5. **VSCode拡張パッケージング**: 上記をVSCode拡張としてパッケージ化。

## 6. 既知の制約・除外事項（現時点の合意）

- LE/SVC/EXCP/CICS/MVS系サービスは本格実装しない（ダミーで通す）
- マルチCSECT間の動的ロード（LOAD/LINK/XCTL相当）は対象外
- 浮動小数点・ベクトル・10進浮動小数点命令は対象外
- ストレージ保護キー、割り込み機構の完全再現は対象外
- LM/STM（複数レジスタ一括）・MVCL（可変長）は、hlasm-parser側の
  dataflow.pyでも「モデル化を誤るよりは未対応のままにする」方針で
  意図的に除外されている前例あり。同じ判断基準を踏襲してよい。

## 7. オープンな意思決定事項（次のセッションで詰める）

- [x] 初期命令セット: 下記§9参照。CVB/CVD・乗除算・論理演算(N/O/X)は
      未実装のまま次段階に持ち越し（§8参照）
- [x] DAPアダプター実装言語: **Python単一**に決定・実装済み（§8参照）。
      DAPのワイヤーフォーマットはLSPと同じ「Content-Length ヘッダー+JSON」
      で軽量なため、Node/TSを増やす理由がなかった。VSCode拡張本体の
      パッケージング（拡張機能としてこのアダプターを起動する部分）は
      未着手のまま次段階に残す
- [x] 未対応命令に遭遇したときの挙動: `UnsupportedInstructionError`を
      lowering時点で送出して停止する方針に決定（no-op継続だと誤った
      実行結果を「正しく動いた」ように見せてしまうため）。SVC/LE自体は
      まだ影も形もない（§6の除外方針は変更なし）
- [x] リポジトリ構成: `/home/ubuntu/workspace/hlasm-emulator`にhatchling
      構成で作成、hlasm-parserとは別リポジトリ（git init済み）。
      hlasm-parserはpath依存の`pip install -e ../hlasm-parser`で利用
      （pyproject.tomlのdependenciesには入れていない — 直接参照URLだと
      hatchlingが`allow-direct-references`を要求し、しかもpip側で
      editableインストールと衝突したため、READMEで手順を案内する形に
      した）
- [ ] テスト方針: 現状は手計算した期待値によるpytestユニットテストのみ
      （tests/配下、21件）。実機/Hercules等との突合せは未着手

## 8. 実装状況（このセッションで実装した内容）

`hlasm_emulator/`パッケージとして以下を実装済み（コード + pytest 21件、
全てグリーン）:

- **対応命令セット**: LR, LTR, AR, SR, CR（RR形式）／ LA, L, ST, A, S, C
  （RX形式）／ MVI（SI形式）／ MVC, CLC（SS形式）／ B, BR, BC＋拡張
  ニーモニック(BE/BNE/BH/BL/BHE/BNL/BLE/BNH/BP/BM/BZ/BNZ/BO/BNO),
  BCT, BCTR, BAL, BALR（分岐系）
- **アーキテクチャ**: `hlasm_parser.parse()` → `lowering.py`
  （`Program`→`IRInstruction`列＋`Memory`）→ `interpreter.py`
  （フェッチ/デコード/実行ループ）→ `opcodes.py`（命令セマンティクス）。
  CLIは`hlasm-emulator <file> [--trace]`でレジスタダンプ付き実行可能
- **重要な設計簡略化（v0限定、要フォローアップ）**:
  1. 命令アドレス(PSW.instruction_address)は実バイトアドレスではなく
     **IR命令列のインデックス**。hlasm-parserが命令長・実アドレスを
     計算しないための割り切り。BAL/BALRのリンク値もこのインデックス。
  2. **単一CSECTのみ対応**（複数CSECTは`LoweringError`で拒否）
  3. **USING/ベースレジスタによるシンボリックアドレス解決を省略**:
     `L 1,COUNT`のような裸のシンボルオペランドは、`hlasm_parser.layout`
     で計算したそのDC/DSラベルの絶対オフセットに直接解決する
     （実機のようにUSINGレンジからベース+変位を逆算していない）。
     `D(X,B)`の明示形式は実行時にベースレジスタの値を正しく使う
  4. 分岐先ラベルは**実行可能命令の上に置く必要がある**
     （`LOOP DS 0H`のような整列イディオムを分岐先にする慣用句は非対応）
  5. DC初期値のエンコードはC/X/B/F/H/FD型のみ対応。それ以外
     （P/Z/A等）はDCの時点で`LoweringError`（未使用データでも失敗する）
- **未実装**: CVB/CVD、乗除算(M/D)、論理演算(N/O/X)、VSCode拡張パッケージング
- 動作確認例: `LA`でリストの先頭アドレスをロード→`BCT`ループで4要素
  （10,20,30,40）を`AR`で合計→`ST`でTOTALに格納、を実行して合計100が
  正しく得られることを`tests/test_integration.py`で確認済み

### 8-1. DAPアダプター実装（追加セッション）

`hlasm_emulator/dap/`として実装済み（`protocol.py`/`server.py`/
`__main__.py`）。テストはtests/test_dap_protocol.py（フレーミングの
往復）、tests/test_dap_server.py（`DebugSession`を直接駆動、ループ内
ブレークポイントで4回止まりレジスタ値を手計算と突き合わせ）、
tests/test_dap_subprocess.py（`python -m hlasm_emulator.dap`を実プロセス
起動して実配線を確認）の3層、計14件（全体では35件）。

- **起動方法**: `hlasm-dap`（コンソールスクリプト）または
  `python -m hlasm_emulator.dap`。stdin/stdoutでDAPメッセージを待ち受ける
- **対応リクエスト**: initialize, launch（`program`必須, `stopOnEntry`
  任意）, setBreakpoints（行ブレークポイントのみ。命令の無い行は次の
  実行可能行にスナップする）, setExceptionBreakpoints/
  setFunctionBreakpoints（no-opで成功応答のみ）, configurationDone,
  threads, stackTrace（フレーム1枚のみ）, scopes（Registers/Data の
  2スコープ）, variables（R0-R15+CC+IP、およびDCラベルをメモリ上の値で
  表示）, continue, next/stepIn/stepOut（呼び出しスタックを追跡しない
  ためstepIn/stepOutはnextと同じ単一ステップ）, pause（no-op応答のみ、
  §8-2参照）, evaluate（レジスタ名/CC/IP/データラベル名を評価、Watch・
  Hover用）, disconnect, terminate
- **設計上の割り切り**:
  1. 単一スレッド・単一スタックフレームのみ。BAL/BALRのリンクレジスタ
     以上のコールスタック追跡はしていないため、stepIn/stepOutはstepの
     別名でしかない
  2. `continue`は同期実行（ブレークポイント命中 or プログラム終了 or
     最大ステップ数5,000,000到達まで、その場でループを回してから応答
     を返す）。命令実行がI/O待ちしないため実用上問題ないが、`pause`は
     「継続実行中に割り込む」という本来の意味では機能しない
     （no-op応答＋stoppedイベントを返すだけ）
  3. 条件付き/ヒット回数付きブレークポイント、データブレークポイント、
     `readMemory`/`writeMemory`リクエストは未対応

### 8-2. VSCode拡張パッケージング（追加セッションで実装済み）

`vscode-extension/`として実装済み。WebFetchで
https://code.visualstudio.com/api/extension-guides/debugger-extension
の仕様を確認した上で実装（憶測で書かなかった）。

- **構成**: `package.json`（`contributes.debuggers`/`languages`/
  `breakpoints`/`configuration`宣言）＋ `extension.js`（プレーンJS、
  TypeScriptビルド不要）
- **仕組み**: `vscode.debug.registerDebugAdapterDescriptorFactory`で
  `DebugAdapterExecutable`を返し、`<python> -m hlasm_emulator.dap`を
  子プロセスとして起動するだけ。デバッグロジックは一切持たず、全てPython
  側(§8-1)に委譲する薄いグルー
- **Pythonインタプリタ解決順序**: (1) VSCode設定
  `hlasmEmulator.pythonPath` → (2) `<ワークスペース>/.venv/bin/python`
  （自動検出）→ (3) PATH上の`python3`
- **言語登録**: `.hlasm`/`.asm`/`.mlc`拡張子に言語ID`hlasm`を割り当て、
  ガター上でブレークポイントを打てるようにした（構文ハイライトの
  文法定義はスコープ外、未実装）
- **検証方法（初回セッション時点）**: 実VSCode GUIが無い前提で、(1)
  `npx @vscode/vsce package`でのパッケージング成功、(2) Node上で
  `vscode`モジュールを最小限モックして`activate()`の登録処理・
  `resolveDebugConfiguration`のガード・`createDebugAdapterDescriptor`の
  インタプリタ解決ロジック（実リポジトリの`.venv`検出を含む）を検証。
  実VSCode UIでの目視確認は追加セッション（§8-3）で実施済み
- **未実装のまま残るもの**: Marketplace公開（`vsce publish`）、`.vsix`
  へのLICENSE同梱
- 使い方の詳細は`vscode-extension/README.md`参照

### 8-3. 実VSCode環境での目視確認、構文ハイライト（追加セッション）

前回セッションで「実VSCode GUIが無いので目視確認は次回」としていたが、
このマシンに`sudo`とネットワークがあったため、**本物のVSCode
（Electron）をXvfb仮想ディスプレイ上で起動し、公式のExtension Test API
（`@vscode/test-electron`）経由で実際にブレークポイント→変数表示まで
駆動する**という、憶測でも省略でもない本格的な検証を実施できた。

**やったこと**:
1. `sudo apt-get install xvfb imagemagick` で仮想ディスプレイと
   スクリーンショット取得手段を用意
2. `@vscode/test-electron`が実VSCode 1.134.0一式（Electron本体、
   約330MB）をダウンロードし、`runTests()`で
   `--extensionDevelopmentPath`にこの拡張、`--extensionTestsPath`に
   自作のテストスイートを渡して起動
3. テストスイート（Extension Host内で実行、本物の`vscode`
   API使用）が: 拡張を`activate()` → `examples/sum_loop.hlasm`相当の
   ファイルを開く（`languageId`が`hlasm`になることを確認）→
   `vscode.debug.addBreakpoints()`でAR命令の行にブレークポイント設置
   → `vscode.debug.startDebugging()`でlaunch → DebugAdapterTrackerで
   本物のDAPメッセージを傍受して`'stopped'`イベントを検知 →
   `session.customRequest('threads'|'stackTrace'|'scopes'|'variables'|
   'evaluate', ...)`をVSCode本体と全く同じ経路で呼び出し、R1=10/R2=0/
   COUNT=4/停止行=6等を手計算値とアサーション比較 → 全て一致
4. ブレークポイント命中中に`DISPLAY=:99 import -window root`で
   スクリーンショットを取得。エディタのブレークポイント（赤丸）・
   現在行ハイライト・コールスタック（`AR verify_sample.hlasm 6:1`,
   "Paused on breakpoint"）・VARIABLESパネルの`Registers`/`Data`
   スコープ・構文ハイライト（ニーモニックの配色、ラベルの配色、
   `F'4'`等の文字列リテラルの配色、ステータスバーの`HLASM`表示）が
   すべて同一画面に写っていることを目視確認済み
5. 構文ハイライト自体は`vscode-textmate`+`vscode-oniguruma`で
   ヘッドレスにもトークナイズ検証済み（実VSCodeと同じOnigurumaエンジン
   でMAIN=label, CSECT/LA/L/AR/BCT/ST/END/DC=keyword,
   F'4'等=string、という分類が期待通りであることを確認）

**ハマった点（次回同じ検証をする時のために記録）**: このセッション自身が
VSCode拡張ホスト内のNodeプロセスとして動いているため、シェル環境に
`ELECTRON_RUN_AS_NODE=1`と`VSCODE_IPC_HOOK_CLI`が継承されている。これを
消さずに実VSCodeバイナリを起動すると、ElectronがただのNodeとして動作
してしまい（`--no-sandbox`等のオプションが「不正なオプション」として
拒否される、ワークスペースパスをrequireしようとしてMODULE_NOT_FOUND、
等の不可解なエラーになる）。`delete process.env.ELECTRON_RUN_AS_NODE`
と`delete process.env.VSCODE_IPC_HOOK_CLI`をテストランナー側で行うことで
解決した。

**追加した構文ハイライト**: `vscode-extension/syntaxes/hlasm.tmLanguage.json`
（列1のみをラベル/コメント判定に使うヒューリスティック文法。継続列や
71/72桁境界は非対応、と明記）＋`language-configuration.json`
（`*`行コメントのトグル、`()`の対応括弧）。

この検証で使ったXvfb起動・`@vscode/test-electron`実行・スクリーンショット
取得の一連の手順とスクリプトは使い捨てのスクラッチ領域で実行し、
リポジトリには恒久的なCIとしては追加していない（Electron本体
ダウンロード+Xvfbを要するため、通常のpytest実行には重すぎると判断）。
再現手順が要る場合はこのセッションのログを参照。

### 8-4. 命令の実行内容を平易な説明文で表示（追加セッション）

ユーザーから「ステップ実行はできるようになったが、各命令が何をしたのか
直感的にわからない」という課題が出た。Copilotの提案（`opcodes.py`に
`explain()`を足してDAPのVARIABLESに出す）を検討し、以下の点を改良して
実装した:

- `opcodes.py`ではなく新規`hlasm_emulator/explain.py`に分離
  （実行セマンティクスと表示整形の関心を混ぜない）
- 24命令ぶん個別に書くのではなく、IR引数の**型**（`ir.RR`/`ir.RX`/
  `ir.SI`/`ir.SS`/各Branch型）でディスパッチし、同じ形の命令は
  テンプレートを共有
- 実行前のGPRスナップショット（`before_gpr`）を使ってアドレス計算・
  演算前の値を再現。特に`LA 4,4(0,4)`（ベースレジスタと書き込み先
  レジスタが同じ、`examples/sum_loop.hlasm`に実在するパターン）で、
  実行後の状態を使うと自己参照で壊れるため、必ず実行前スナップショット
  でアドレスを解決するようにした
- 1箇所の実装をCLIの`--trace`・DAPのDebug Console出力・DAPの
  `Registers`スコープ内`(last step)`疑似変数の3箇所で共有

**表示例**: `R2 = R2 + R1 = 0 + 10 = 10; CC=2`
（`AR`）、`R1 = mem[4] = 10`（`L`）、`BE: CC=0 -> branch to #7`
（条件分岐）等。分岐命令は「実際に分岐したか」を`next_ip != 現在
IP+1`で判定して表現を出し分けている。

テストは`tests/test_explain.py`に18件（対応する全命令カテゴリを手計算
した期待値と突き合わせ）。既存のDAP subprocess テストも、`next`/
`continue`実行時に追加で送られる`output`イベント（説明文）を読み飛ばす
よう修正済み。全体のpytestは53件でグリーン。

### 8-5. 命令セット拡充 + コールスタック可視化（進行中セッション、中断）

ユーザーから「1. 命令セット拡充」「2. サブルーチン呼び出しの可視化
（コールスタック）」の2つを依頼され、以下まで実装・コミット済み
（セッション上限のため中断、次回はここから再開）:

**完了: 命令セット拡充**（pytest全体で78件グリーン、コミット済み）
- 新規: `hlasm_emulator/packed_decimal.py`（パックド10進数のencode/decode。
  `DC P'...'`の静的初期値と`CVB`/`CVD`の両方から共用）
- 追加した命令: `CVB`/`CVD`（RX形式、常にdoubleword=8バイト固定）、
  `M`/`MR`（乗算、偶数レジスタペアR1:R1+1に64ビット積を格納）、
  `D`/`DR`（除算、ゼロ除算・商のオーバーフローで`ExecutionError`、
  商は0方向への切り捨て・余りは被除数と同符号という実機仕様通り）、
  `N`/`NR`/`O`/`OR`/`X`/`XR`（論理AND/OR/XOR、CCは0(結果ゼロ)/1(非ゼロ)
  のみ）、`LM`/`STM`（複数レジスタロード/ストア、`R3<R1`のレジスタ番号
  折り返し=`LM 14,12,12(13)`慣用句に対応）
- `ir.py`にRS形式(`RS(r1,r3,addr)`)を追加。M/D/MR/DR/N/NR/O/OR/X/XRは
  既存のRR/RX形状を再利用（新規IR型は不要だった）
- `lowering.py`: RS_MNEMONICS追加、3オペランド(reg,reg,addr)の
  リゾルバを追加
- `opcodes.py`: 偶数レジスタチェック`_require_even`、レジスタ範囲
  折り返しヘルパー`_register_range`を追加
- `explain.py`: 上記全命令の説明文フォーマットを追加
  （乗算は`R4:R5 = R5 * R3 = 7 * 6 = 42`、除算は
  `R4:R5 / R3 = 17 / 5 -> quotient R5=3, remainder R4=2`等）
- テスト: `tests/test_opcodes_decimal_and_logic.py`(14件)、
  `tests/test_explain.py`に追加8件

**完了: コールスタック可視化**（次セッションで完了、pytest全体83件グリーン）
- `interpreter.py`に`CallFrame`データクラスと`Interpreter.call_stack`を
  追加。BAL/BALRが実際に分岐した時にフレームをpush、その後の分岐先が
  呼び出し時に保存した戻り先IR indexと一致したらpop、という
  ヒューリスティックで呼び出し/リターンを検出（実機にはコールスタック
  という概念自体が無いことをdocstringに明記）。ネスト呼び出しの
  LIFO順序も`tests/test_call_stack.py`(4件)で確認済み
- `hlasm_emulator/dap/server.py`:
  - `cmd_stackTrace`を複数フレーム対応に変更。フレーム0=現在の命令、
    フレーム1以降=`call_stack`の各保留中呼び出し（BAL/BALRが実行された
    行を表示。「そのフレームの実行はコール元の行で止まっている」という
    通常のデバッガーの慣習に合わせた）
  - `cmd_stepOut`を独立実装に変更:
    保留中の呼び出しがあれば「そのフレームがreturnするまで実行」、
    無ければ「最後まで実行」(継続と同じ)。`_continue_execution`と
    ロジックを共有するため`_run_until(stop_condition)`ヘルパーに
    リファクタリング（ブレークポイントチェック・最大ステップ数
    ガードは共通化、停止条件だけが呼び出し元ごとに異なる）
  - `cmd_stepIn`は変更なし（1ステップ実行が既に「呼び出し先に入る」
    動作そのものであるため、専用実装は不要と判断）
- テスト: `tests/test_dap_call_stack.py`(5件)。呼び出し前後での
  フレーム数変化、コールサイト行の表示、`stepOut`が実際に戻り先まで
  実行すること、呼び出し無しでの`stepOut`が最後まで実行することを確認
- 残る既知の制約: レジスタ/メモリはこのアーキテクチャでは本当に
  グローバルなので、`scopes`はどのフレームを選んでも同じ内容を返す
  （実機的には正しい挙動だが、明記しておく）

### 8-6. CI（GitHub Actions）とLICENSE（追加セッション）

- `.github/workflows/test.yml`: push/PR時にPython 3.10/3.12の2系統で
  pytestを自動実行
- **ハマった点**: 最初`pip install git+https://github.com/kava2108/
  hlasm-parser.git`で組んで実際にpushしたところ、CIが
  `fatal: could not read Username for 'https://github.com'`で失敗した。
  `hlasm-emulator`も`hlasm-parser`も**両方とも非公開(Private)リポジトリ**
  であり、GitHub Actionsの既定の`GITHUB_TOKEN`は実行中のリポジトリ
  自身にしかアクセス権が無く、別の非公開リポジトリ(hlasm-parser)は
  cloneできないため（ローカルでは自分のgh CLI認証があるので
  `git ls-remote`が通ってしまい、この問題に気づくのが遅れた）
- ユーザーに「hlasm-parserを公開にする」か「PATをシークレットにする」
  かを確認し、**PAT方式**を選択。ワークフローを
  `pip install "git+https://x-access-token:${HLASM_PARSER_PAT}@github.com/kava2108/hlasm-parser.git"`
  に変更（`HLASM_PARSER_PAT`はリポジトリシークレット）
- **ユーザー側の残作業（PATの発行はAPIでは不可、Web UI操作が必要）**:
  1. GitHub右上のアバター → Settings → Developer settings →
     Personal access tokens → Fine-grained tokens → Generate new token
  2. Repository access を「Only select repositories」→
     `kava2108/hlasm-parser`のみを選択
  3. Permissions → Repository permissions → **Contents: Read-only**
     だけ付与（他は不要）
  4. 発行されたトークンを、`hlasm-emulator`リポジトリの
     Settings → Secrets and variables → Actions → New repository secret
     で名前`HLASM_PARSER_PAT`として登録
     （または手元の端末で`gh secret set HLASM_PARSER_PAT --repo
     kava2108/hlasm-emulator`を実行し、プロンプトにトークンを貼り付け）
  5. 登録後、Actionsタブから再実行（Re-run jobs）するか、何か1コミット
     pushすれば次回から緑になるはず
- **解決済み（このセッションで確認）**: 最初にPATを登録した直後の
  再実行では`remote: Write access to repository not granted. / 403`
  で失敗（認証自体は通っていたが権限不足）。原因はfine-grained PATの
  デフォルトでは`Contents`権限が付いておらず（`Metadata: Read-only`
  のみ）、cloneに必要な`Contents: Read-only`が無かったこと。ユーザーが
  `Contents: Read-only`を追加 → 再実行 → Python 3.10/3.12両方グリーンで
  確定。CIバッジはリポジトリが非公開のため未ログイン状態だと
  「Not Found」になるが、GitHubにログインしてREADMEを見る分には
  正常に表示される（想定通りの制約、対応不要）
- README.mdにCIバッジを追加
- `LICENSE`（MIT、pyproject.tomlに元々あった`license = {text = "MIT"}`
  宣言を実体化したもの）をリポジトリルートと`vscode-extension/`の両方に
  配置（`vsce package`は拡張ディレクトリ内のLICENSEを見るため、片方だけ
  だと警告が消えない）。`vscode-extension/package.json`にも
  `"license": "MIT"`を追加し、`.vsix`を再パッケージング

### 8-7. より複雑なサンプルプログラム追加

`examples/stats.hlasm`: 6要素の配列に対してSUM/MAX/AVERAGE(整数除算)を
計算する例。`sum_loop.hlasm`より一段複雑で、以下を組み合わせている:
- ループ内比較による最大値探索（`CR`+`BNH`+`LR`）
- サブルーチン呼び出し（`BAL`/`BR`）でAVERAGEを計算し、コールスタックの
  push/popが実際に発生する
- 除算（`DR`、レジスタペア）とパックド10進数変換（`CVD`、印字前処理を
  模した形）
- `*`行コメント（hlasm-parserの字句解析でStatementに現れず、
  こちらのlowering処理に一切影響しないことを確認済み）

`tests/test_example_programs.py`に両サンプルの回帰テストを追加
（`sum_loop.hlasm`は既存の期待値、`stats.hlasm`はSUM/MAX/AVERAGEを
Python側でも計算し直して突き合わせ、`call_stack`が最終的に空になる
ことも確認）。pytest全体で85件グリーン。

## 9. 参考にした過去の議論

前セッションで「自作エミュレーター＋VSCodeデバッガーは実現可能か」を
ユーザーから相談され、以下の結論で合意した:
- 完全再現は不可能だが、部分的エミュレーション（20〜30命令＋GPR/PSW＋DAP）
  は現実的に自作可能
- hlasm-parserとは別プロジェクトにすべき（スコープが違う: 構造解析 vs
  実行意味論）
