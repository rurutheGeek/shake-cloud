# テストの構成と実行

配備せずに壊れた設定・境界・不変条件を検出する回帰テストです。`platform/`・
`stacks/`・`cloud/`・`tools/` の実ファイルを読み、YAML・ソーステキスト・
インメモリの実行で検査します。実機へ接続するのは `tools/verify-*.py` の実行テスト
だけで、通常のテストはホストに触れません。

## 実行

リポジトリのルートで実行します。

```bash
# 全体（CIと同じ）
python3 -m unittest discover -s tests

# 1ファイルだけ
python3 -m unittest discover -s tests -p 'test_homarr_stack.py'

# 直接実行もできる（各ファイルの __main__）
python3 tests/test_homarr_stack.py
```

`tests/__init__.py` は置きません。置くと `discover` が `tests` をパッケージとして
扱い、`from support import ...` が解決できなくなります（`tests` ディレクトリが
`sys.path` に入らなくなるため）。単体実行は上の `-p` を使ってください。

`ansible-playbook` が無い環境では、`--syntax-check` を行うテストは
`skipped 'ansible-playbook is not installed'` になります。skipを許さない場所
（CI・引き継ぎ時の確認）では `platform/ansible/requirements.txt` を入れてから
実行してください。CIは導入済みです。

## 命名と置き場所

- **1対象1ファイル。** ファイル名だけで対象が分かる名前にします。
  - `test_<stack>_stack.py` … `stacks/<name>/`（例: `test_homarr_stack.py`）
  - `test_media_<unit>.py` … `stacks/media/<unit>/`（例: `test_media_kavita.py`）
  - `test_pve_<role>.py` … `platform/ansible/roles/pve_<role>/`（例: `test_pve_backup.py`）
  - `test_verify_<tool>.py` … `tools/verify-<tool>.py`
- テストクラスは層ごとに分けます（例: `ComposeTests`・`ManageTests`・
  `SyntaxTests`・`DocumentationTests`）。
- 各テストは**不変条件を1つ**検査します。モジュールのdocstringに「何が壊れると
  困るか」を書きます（例: ポートがLANへ出る、digest固定が外れる、秘密値が
  `.env` に入る）。
- ドキュメントへ**テスト件数を書かない**でください。すぐ古くなります。必要なら
  「`tests/test_<name>.py` が検査する」とファイルを参照します。

## 共通ヘルパ（`tests/support.py`）

3ファイル以上で同じヘルパを書くことになったら `support.py` へ移します。
標準ライブラリだけで保ち、次を提供します。

| ヘルパ | 用途 |
| --- | --- |
| `read(path)` | リポジトリのファイルをUTF-8で読む |
| `load_module(path, name)` | `manage.py` などをパスから読み込む |
| `role_task(tasks, fragment)` | 名前の一部でAnsibleタスクを引く |
| `scratch_dir(prefix)` | プロセス終了時に消える作業ディレクトリ |
| `syntax_check(playbook, inventory)` | `ansible-playbook --syntax-check` を実行する |
| `ansible_playbook()` | 実行ファイルを探し、無ければ `SkipTest` にする |

一時ディレクトリは `scratch_dir` か `TemporaryDirectory` の**中**に作り、
`/tmp` に残さないでください。`TemporaryDirectory` の親に `-state` を作る形は、
親のcleanupでは消えないため残ります。
