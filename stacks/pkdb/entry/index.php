<?php
// ポケモンの登録・修正画面（1ページ）。
//
// 登録済みの値を探して見せ、その行を「修正」するか「コピー」して新しく登録する。
// 値を集めて pokemondb.register_pokemon / update_pokemon / register_title を呼ぶだけで、
// どの表へ何を入れるかは stacks/pkdb/sql/entry.sql の関数が決める。接続は pkdb_entry
// ロールで、表へ直接は書けない。入口（Caddy）が Authentik の Forward Auth を通した
// 利用者名を X-Authentik-Username で渡すので、それを登録者として記録する。
declare(strict_types=1);

const STATS = ['h' => 'HP', 'a' => 'こうげき', 'b' => 'ぼうぎょ', 'c' => 'とくこう', 'd' => 'とくぼう', 's' => 'すばやさ'];
const FIELDS = ['ndex', 'name', 'english', 'title', 'form_id', 'form_name', 'type_1', 'type_2',
    'h', 'a', 'b', 'c', 'd', 's', 'ability_1', 'ability_2', 'ability_h', 'before', 'aliases'];

// 登録済みの1行（図鑑番号・フォーム・作品）を、画面の項目と同じ名前で取り出す。
const ROWS_SQL = <<<'SQL'
SELECT s.ndex_number AS ndex, s.form_id, s.title_group_id AS title, g.title_name,
       n.name, coalesce(f.form_name, '') AS form_name,
       t1.name AS type_1, coalesce(t2.name, '') AS type_2,
       s.basestats_h AS h, s.basestats_a AS a, s.basestats_b AS b,
       s.basestats_c AS c, s.basestats_d AS d, s.basestats_s AS s,
       coalesce((SELECT a.name FROM pokemon_ability pa JOIN ability_data a USING (ability_id, title_group_id)
                 WHERE pa.ndex_number = s.ndex_number AND pa.form_id = s.form_id
                   AND pa.title_group_id = s.title_group_id AND pa.slot = '1'), '') AS ability_1,
       coalesce((SELECT a.name FROM pokemon_ability pa JOIN ability_data a USING (ability_id, title_group_id)
                 WHERE pa.ndex_number = s.ndex_number AND pa.form_id = s.form_id
                   AND pa.title_group_id = s.title_group_id AND pa.slot = '2'), '') AS ability_2,
       coalesce((SELECT a.name FROM pokemon_ability pa JOIN ability_data a USING (ability_id, title_group_id)
                 WHERE pa.ndex_number = s.ndex_number AND pa.form_id = s.form_id
                   AND pa.title_group_id = s.title_group_id AND pa.slot = 'H'), '') AS ability_h,
       coalesce((SELECT string_agg(al.name_alias, '、' ORDER BY al.name_alias) FROM pokemon_name_alias al
                 WHERE al.ndex_number = s.ndex_number AND al.form_id = s.form_id), '') AS aliases,
       coalesce((SELECT l.eng FROM pokemon_name_lang l
                 WHERE l.ndex_number = s.ndex_number AND l.form_id = '00'), '') AS english,
       coalesce((SELECT e.before_ndex_number || ' ' || bn.name FROM pokemon_evolution e
                 JOIN pokemon_name bn ON bn.ndex_number = e.before_ndex_number
                 WHERE e.after_ndex_number = s.ndex_number AND e.after_form_id = s.form_id
                 ORDER BY e.before_ndex_number, e.before_form_id LIMIT 1), '') AS before
FROM pokemon_status s
JOIN pokemon_name n ON n.ndex_number = s.ndex_number
JOIN pokemon_name_form f ON f.ndex_number = s.ndex_number AND f.form_id = s.form_id
JOIN title_group g ON g.title_group_id = s.title_group_id
JOIN type_data t1 ON t1.type_id = s.type_1_id
LEFT JOIN type_data t2 ON t2.type_id = s.type_2_id
SQL;

function h(string|int|null $value): string
{
    return htmlspecialchars((string) ($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

// 固定の属性名だけを出す（値は通さない）。
function attr(bool $on, string $name): string
{
    return $on && preg_match('/^[a-z]+$/', $name) ? ' ' . $name : '';
}

function connect(): PDO
{
    $dsn = sprintf(
        'pgsql:host=%s;port=%s;dbname=%s',
        getenv('PKDB_ENTRY_HOST') ?: 'db',
        getenv('PKDB_ENTRY_PORT') ?: '5432',
        getenv('PKDB_ENTRY_DATABASE') ?: 'sleepy_pkdb'
    );
    $pdo = new PDO($dsn, getenv('PKDB_ENTRY_USER') ?: 'pkdb_entry', getenv('PKDB_ENTRY_PASSWORD') ?: '', [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('SET search_path = pokemondb');
    return $pdo;
}

// PostgreSQL の例外から、関数が RAISE した文だけを取り出す。
function database_message(PDOException $error): string
{
    if (preg_match('/ERROR:\s+(.+?)(?:\n|$)/u', $error->getMessage(), $match)) {
        return $match[1];
    }
    return '登録できませんでした';
}

function field(string $name): string
{
    return trim((string) ($_POST[$name] ?? ''));
}

function number(string $name, string $label): int
{
    $value = filter_var(field($name), FILTER_VALIDATE_INT);
    if ($value === false) {
        throw new InvalidArgumentException($label . 'は数字で入れてください');
    }
    return $value;
}

function csrf_token(): string
{
    $token = $_COOKIE['pkdb_entry_csrf'] ?? '';
    if (!preg_match('/^[0-9a-f]{64}$/', $token)) {
        $token = bin2hex(random_bytes(32));
        setcookie('pkdb_entry_csrf', $token, ['path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
    }
    return $token;
}

// 登録と修正は引数が同じなので、呼ぶ関数だけを変える。
function save_pokemon(PDO $pdo, string $actor, bool $update): string
{
    $stats = [];
    foreach (STATS as $key => $label) {
        $stats[$key] = number($key, $label);
    }
    // 進化前は「0004 ヒトカゲ」の形で選ぶので、先頭の番号だけを使う。
    $before = preg_match('/^\s*(\d{1,4})/', field('before'), $match) ? $match[1] : '';
    $function = $update ? 'update_pokemon' : 'register_pokemon';
    $statement = $pdo->prepare(
        "SELECT $function(:actor, :ndex, :name, :form_id, :form_name, :title, :type_1, :type_2,
                :h, :a, :b, :c, :d, :s, :ability_1, :ability_2, :ability_h, :english, :before, '00',
                regexp_split_to_array(:aliases, '\\s*[,、]\\s*'))"
    );
    foreach ($stats as $key => $value) {
        $statement->bindValue(':' . $key, $value, PDO::PARAM_INT);
    }
    $statement->bindValue(':actor', $actor);
    $statement->bindValue(':before', $before);
    foreach (['ndex', 'name', 'form_id', 'form_name', 'title', 'type_1', 'type_2',
              'ability_1', 'ability_2', 'ability_h', 'english', 'aliases'] as $name) {
        $statement->bindValue(':' . $name, field($name));
    }
    $statement->execute();
    return (string) $statement->fetchColumn();
}

function register_title(PDO $pdo, string $actor): string
{
    $statement = $pdo->prepare('SELECT register_title(:actor, :id, :name, :generation, :region)');
    $statement->bindValue(':actor', $actor);
    $statement->bindValue(':id', field('title_id'));
    $statement->bindValue(':name', field('title_name'));
    $statement->bindValue(':generation', number('generation', '世代'), PDO::PARAM_INT);
    $statement->bindValue(':region', field('region'));
    $statement->execute();
    return (string) $statement->fetchColumn();
}

// 検索語（番号・名前・あだ名・名前の一部）から図鑑番号を1つ決める。
function find_ndex(PDO $pdo, string $query): ?string
{
    $query = trim($query);
    if ($query === '') {
        return null;
    }
    if (preg_match('/^(\d{1,4})\b/', $query, $match)) {
        $ndex = str_pad($match[1], 4, '0', STR_PAD_LEFT);
        $statement = $pdo->prepare('SELECT ndex_number FROM pokemon_name WHERE ndex_number = :ndex');
        $statement->execute([':ndex' => $ndex]);
        return $statement->fetchColumn() ?: null;
    }
    $statement = $pdo->prepare(
        "SELECT ndex_number FROM (
           SELECT ndex_number, 1 AS rank FROM pokemon_name WHERE name = :exact
           UNION ALL SELECT ndex_number, 2 FROM pokemon_name_alias WHERE name_alias = :exact
           UNION ALL SELECT ndex_number, 3 FROM pokemon_name WHERE name LIKE '%' || :part || '%'
         ) found ORDER BY rank, ndex_number LIMIT 1"
    );
    $statement->execute([':exact' => $query, ':part' => addcslashes($query, '%_\\')]);
    return $statement->fetchColumn() ?: null;
}

function row_link(array $row, array $extra): string
{
    return '?' . http_build_query(['q' => $row['ndex'], 'row' => $row['form_id'] . '-' . $row['title']] + $extra);
}

$actor = trim((string) ($_SERVER['HTTP_X_AUTHENTIK_USERNAME'] ?? '')) ?: 'unknown';
$token = csrf_token();
$notice = '';
$error = '';
$mode = 'new';
$form = array_fill_keys(FIELDS, '');
$titleForm = ['title_id' => '', 'title_name' => '', 'generation' => '', 'region' => ''];
$titleOpen = false;
$query = trim((string) ($_GET['q'] ?? ''));
$ndex = null;
$rows = $examples = $titles = $types = $abilities = $pokemon = $recent = $forms = $formNames = [];
$next = 0;
$nextForm = '';

try {
    $pdo = connect();
    $posted = ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST';
    if ($posted) {
        $action = field('action');
        try {
            if (!hash_equals($token, (string) ($_POST['csrf'] ?? ''))) {
                throw new InvalidArgumentException('ページを開き直してからもう一度送ってください');
            }
            if ($action === 'title') {
                $notice = register_title($pdo, $actor);
            } else {
                $notice = save_pokemon($pdo, $actor, $action === 'update');
                $query = field('ndex');
            }
        } catch (PDOException $exception) {
            $error = database_message($exception);
        } catch (InvalidArgumentException $exception) {
            $error = $exception->getMessage();
        }
        if ($error !== '') {
            // 入れ直さずに済むよう、送られた値をそのまま戻す。
            if ($action === 'title') {
                $titleOpen = true;
                foreach ($titleForm as $name => $unused) {
                    $titleForm[$name] = field($name);
                }
            } else {
                $mode = $action === 'update' ? 'edit' : 'new';
                foreach (FIELDS as $name) {
                    $form[$name] = field($name);
                }
                $query = field('ndex');
            }
        }
    }

    $titles = $pdo->query('SELECT title_group_id, title_name, generation FROM title_group ORDER BY title_group_id DESC')->fetchAll();
    $types = $pdo->query('SELECT name FROM type_data ORDER BY type_id')->fetchAll(PDO::FETCH_COLUMN);
    $abilities = $pdo->query('SELECT DISTINCT name FROM ability_data ORDER BY name')->fetchAll(PDO::FETCH_COLUMN);
    $pokemon = $pdo->query('SELECT ndex_number, name FROM pokemon_name ORDER BY ndex_number')->fetchAll();
    $next = (int) $pdo->query('SELECT coalesce(max(ndex_number::integer), 0) + 1 FROM pokemon_name')->fetchColumn();
    $formNames = $pdo->query(
        "SELECT form_name FROM pokemon_name_form WHERE form_name IS NOT NULL AND form_id <> '00'
         GROUP BY form_name ORDER BY count(*) DESC, form_name LIMIT 5"
    )->fetchAll(PDO::FETCH_COLUMN);
    $latestTitle = $titles[0]['title_group_id'] ?? '';

    $ndex = find_ndex($pdo, $query);
    if ($query !== '' && $ndex === null && $error === '' && !$posted) {
        $error = $query . ' は見つかりません';
    }
    if ($ndex !== null) {
        $statement = $pdo->prepare(ROWS_SQL . ' WHERE s.ndex_number = :ndex ORDER BY s.form_id, s.title_group_id');
        $statement->execute([':ndex' => $ndex]);
        $rows = $statement->fetchAll();
        $statement = $pdo->prepare(
            "SELECT form_id, coalesce(form_name, '') AS form_name, coalesce(gender, '') AS gender
             FROM pokemon_name_form WHERE ndex_number = :ndex ORDER BY form_id"
        );
        $statement->execute([':ndex' => $ndex]);
        $forms = $statement->fetchAll();
        $nextForm = str_pad((string) ((int) max(array_column($forms, 'form_id') ?: ['-1']) + 1), 2, '0', STR_PAD_LEFT);
    } else {
        $examples = $pdo->query(
            ROWS_SQL . ' WHERE s.ndex_number IN (SELECT ndex_number FROM pokemon_name ORDER BY ndex_number DESC LIMIT 3)
             ORDER BY s.ndex_number DESC, s.form_id, s.title_group_id'
        )->fetchAll();
    }

    // 一覧の行から「修正」「コピー」を選ぶと、その行の値を入力欄へ入れる。
    if ($error === '' && !$posted && isset($_GET['row'])) {
        [$rowForm, $rowTitle] = array_pad(explode('-', (string) $_GET['row'], 2), 2, '');
        foreach ($rows as $row) {
            if ($row['form_id'] !== $rowForm || $row['title'] !== $rowTitle) {
                continue;
            }
            foreach (FIELDS as $name) {
                $form[$name] = (string) ($row[$name] ?? '');
            }
            $copy = (string) ($_GET['copy'] ?? '');
            if ($copy === 'species') {
                $form = ['ndex' => (string) $next, 'name' => '', 'english' => '', 'form_id' => '00',
                         'form_name' => '', 'title' => $latestTitle, 'before' => '', 'aliases' => ''] + $form;
            } elseif ($copy === 'form') {
                $form = ['form_id' => $nextForm, 'form_name' => '', 'title' => $latestTitle, 'aliases' => ''] + $form;
            } elseif ($copy === 'title') {
                $form = ['title' => $latestTitle === $rowTitle ? '' : $latestTitle] + $form;
            } else {
                $mode = 'edit';
            }
            break;
        }
    }
    if ($mode === 'new' && $form['ndex'] === '') {
        $form = ['ndex' => (string) $next, 'form_id' => '00', 'title' => $latestTitle] + $form;
    }

    $recent = $pdo->query(
        "SELECT to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'MM/DD HH24:MI') AS at, actor, action, detail
         FROM entry_log ORDER BY id DESC LIMIT 10"
    )->fetchAll();
} catch (PDOException $exception) {
    http_response_code(503);
    error_log('pkdb-entry: ' . $exception->getMessage());
    $error = 'データベースにつながりません';
}

$edit = $mode === 'edit';
$shown = $rows ?: $examples;
$titleNames = array_column($titles, 'title_name', 'title_group_id');
$formList = implode(' ／ ', array_map(
    static fn (array $item): string => trim($item['form_id'] . ' ' . ($item['form_name'] !== '' ? $item['form_name'] : $item['gender'])),
    $forms
));
$actions = ['update_pokemon' => '修正', 'register_pokemon' => '登録', 'register_title' => '作品'];
?>
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ポケモン登録</title>
<style>
:root { color-scheme: light dark; --line: #8884; --accent: #2f6fde; --dim: #8889; }
body { font-family: system-ui, sans-serif; margin: 0 auto; padding: 16px; max-width: 980px; line-height: 1.5; }
h1 { font-size: 1.3rem; margin: 0 0 12px; }
h2 { font-size: 1rem; margin: 24px 0 8px; }
form.grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
label { display: grid; gap: 2px; font-size: .8rem; grid-column: span 3; align-content: start; }
label.stat { grid-column: span 1; }
label.third { grid-column: span 2; }
small { color: var(--dim); font-size: .72rem; overflow-wrap: anywhere; }
input, select, button, a.button { font: inherit; padding: 8px; border: 1px solid var(--line); border-radius: 6px; min-width: 0; background: Canvas; color: CanvasText; }
input[readonly] { background: #8882; }
button { background: var(--accent); color: #fff; border: 0; font-weight: 600; cursor: pointer; }
form.grid > button, form.grid > .buttons { grid-column: span 6; }
.buttons { display: flex; gap: 8px; }
.buttons button { flex: 1; }
a.button { text-decoration: none; text-align: center; }
form.search { display: flex; gap: 8px; margin-bottom: 12px; }
form.search input { flex: 1; }
.message { padding: 10px 12px; border-radius: 6px; margin: 0 0 12px; }
.ok { background: #1f9d5522; border: 1px solid #1f9d55; }
.ng { background: #d6454522; border: 1px solid #d64545; }
.mode { font-weight: 600; margin: 0 0 8px; }
details { border: 1px solid var(--line); border-radius: 6px; padding: 8px 12px; margin-top: 24px; }
summary { cursor: pointer; font-weight: 600; }
details form { margin-top: 10px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .8rem; white-space: nowrap; }
td, th { border-bottom: 1px solid var(--line); padding: 5px 6px; text-align: left; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.act a { margin-right: 8px; }
tr.current { background: #2f6fde22; }
@media (max-width: 560px) { label, label.third { grid-column: span 6; } label.stat { grid-column: span 2; } }
</style>
</head>
<body>
<h1>ポケモン登録</h1>
<?php if ($notice !== ''): ?><p class="message ok"><?= h($notice) ?></p><?php endif; ?>
<?php if ($error !== ''): ?><p class="message ng"><?= h($error) ?></p><?php endif; ?>

<form class="search" method="get">
<input name="q" list="pokemon" placeholder="番号・名前・あだ名" value="<?= h($query) ?>">
<button>さがす</button>
<a class="button" href="?">新規</a>
</form>

<?php if ($shown): ?>
<h2><?= h($rows ? $rows[0]['ndex'] . ' ' . $rows[0]['name'] . ' の登録済みの値' : '登録の例（最近のポケモン）') ?></h2>
<div class="scroll"><table>
<tr><th>番号</th><th>名前</th><th>フォーム</th><th>姿の名前</th><th>作品</th><th>タイプ</th><th>H</th><th>A</th><th>B</th><th>C</th><th>D</th><th>S</th><th>特性1</th><th>特性2</th><th>隠れ特性</th><th>進化前</th><th>あだ名</th><th></th></tr>
<?php foreach ($shown as $row): ?>
<tr class="<?= h($edit && $row['ndex'] === $form['ndex'] && $row['form_id'] === $form['form_id'] && $row['title'] === $form['title'] ? 'current' : '') ?>">
<td><?= h($row['ndex']) ?></td><td><?= h($row['name']) ?></td><td><?= h($row['form_id']) ?></td><td><?= h($row['form_name']) ?></td>
<td><?= h($row['title'] . ' ' . $row['title_name']) ?></td><td><?= h($row['type_1'] . ($row['type_2'] !== '' ? '／' . $row['type_2'] : '')) ?></td>
<?php foreach (STATS as $key => $label): ?><td class="num"><?= h($row[$key]) ?></td><?php endforeach; ?>
<td><?= h($row['ability_1']) ?></td><td><?= h($row['ability_2']) ?></td><td><?= h($row['ability_h']) ?></td><td><?= h($row['before']) ?></td><td><?= h($row['aliases']) ?></td>
<td class="act"><a href="<?= h(row_link($row, [])) ?>">修正</a><a href="<?= h(row_link($row, ['copy' => 'title'])) ?>">新作の値へコピー</a><a href="<?= h(row_link($row, ['copy' => 'form'])) ?>">新しい姿へコピー</a><a href="<?= h(row_link($row, ['copy' => 'species'])) ?>">新しいポケモンへコピー</a></td>
</tr>
<?php endforeach; ?>
</table></div>
<?php endif; ?>

<h2><?= h($edit ? '修正' : '登録') ?></h2>
<?php if ($edit): ?><p class="mode"><?= h($form['ndex'] . ' ' . $form['name'] . '／フォーム ' . $form['form_id'] . '／作品 ' . $form['title'] . ' ' . ($titleNames[$form['title']] ?? '')) ?></p><?php endif; ?>
<form class="grid" method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= h($token) ?>">
<input type="hidden" name="action" value="<?= h($edit ? 'update' : 'register') ?>">
<label>図鑑番号<input name="ndex" inputmode="numeric" pattern="[0-9]{1,4}" required value="<?= h($form['ndex']) ?>"<?= attr($edit, 'readonly') ?>>
<small><?= h('1〜4桁の数字。次の空きは ' . $next . '。すでにある番号を入れると、そのポケモンの姿や新作の値を足す') ?></small></label>
<label>名前<input name="name" value="<?= h($form['name']) ?>">
<small><?= h('日本語の正式名称。例 ' . ($pokemon ? end($pokemon)['name'] : '') . '。すでにある番号なら空でよい') ?></small></label>
<label>英語名<input name="english" value="<?= h($form['english']) ?>">
<small>例 Charizard。基本の姿（フォーム 00）にだけ付く</small></label>
<label>作品<?php if ($edit): ?><input type="hidden" name="title" value="<?= h($form['title']) ?>"><input value="<?= h($form['title'] . ' ' . ($titleNames[$form['title']] ?? '')) ?>" readonly><?php else: ?><select name="title" required>
<option value=""></option>
<?php foreach ($titles as $title): ?>
<option value="<?= h($title['title_group_id']) ?>"<?= attr($form['title'] === $title['title_group_id'], 'selected') ?>><?= h($title['title_group_id'] . ' ' . $title['title_name'] . '（第' . $title['generation'] . '世代）') ?></option>
<?php endforeach; ?>
</select><?php endif; ?>
<small>この値になった作品。初登場ならその作品、値が変わったなら変わった作品</small></label>
<label>フォーム番号<input name="form_id" inputmode="numeric" pattern="[0-9]{1,2}" value="<?= h($form['form_id']) ?>"<?= attr($edit, 'readonly') ?>>
<small><?= h('00 が基本の姿、別の姿は 01 から順に。' . ($formList !== '' ? 'このポケモンは ' . $formList . '。次は ' . $nextForm : '')) ?></small></label>
<label>姿の名前<input name="form_name" value="<?= h($form['form_name']) ?>">
<small><?= h('基本の姿は空でよい。例 ' . implode('・', $formNames)) ?></small></label>
<label>タイプ1<select name="type_1" required>
<option value=""></option>
<?php foreach ($types as $type): ?><option<?= attr($form['type_1'] === $type, 'selected') ?>><?= h($type) ?></option><?php endforeach; ?>
</select></label>
<label>タイプ2<select name="type_2">
<option value=""></option>
<?php foreach ($types as $type): ?><option<?= attr($form['type_2'] === $type, 'selected') ?>><?= h($type) ?></option><?php endforeach; ?>
</select><small>単タイプは空</small></label>
<?php foreach (STATS as $key => $label): ?>
<label class="stat"><?= h($label) ?><input name="<?= h($key) ?>" type="number" min="1" max="255" required value="<?= h($form[$key]) ?>"></label>
<?php endforeach; ?>
<label class="third">特性1<input name="ability_1" list="abilities" value="<?= h($form['ability_1']) ?>">
<small>名前で入れる。候補に無い名前は新しい特性になる</small></label>
<label class="third">特性2<input name="ability_2" list="abilities" value="<?= h($form['ability_2']) ?>">
<small>無ければ空</small></label>
<label class="third">隠れ特性<input name="ability_h" list="abilities" value="<?= h($form['ability_h']) ?>">
<small>無ければ空</small></label>
<label>進化前<input name="before" list="pokemon" value="<?= h($form['before']) ?>">
<small><?= h('進化前のポケモンを番号で。例 0025 ピカチュウ。進化しないなら空' . ($edit ? '。修正では足すだけで、外せない' : '')) ?></small></label>
<label>あだ名<input name="aliases" value="<?= h($form['aliases']) ?>">
<small><?= h('「、」で区切る。例 リザX、メガリザX。ほかのポケモンと同じあだ名は付けられない' . ($edit ? '。消したものは外れる' : '')) ?></small></label>
<?php if ($edit): ?>
<div class="buttons"><button>修正を保存</button><a class="button" href="<?= h('?' . http_build_query(['q' => $form['ndex']])) ?>">やめる</a></div>
<?php else: ?>
<button>登録</button>
<?php endif; ?>
</form>

<details<?= attr($titleOpen, 'open') ?>>
<summary>作品を追加</summary>
<form class="grid" method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= h($token) ?>">
<input type="hidden" name="action" value="title">
<label class="third">作品ID<input name="title_id" inputmode="numeric" pattern="[0-9]{3}" required value="<?= h($titleForm['title_id']) ?>">
<small><?= h('3桁。上2桁が世代、下1桁が世代内の順番。いまの最新は ' . ($titles ? $titles[0]['title_group_id'] . ' ' . $titles[0]['title_name'] : '')) ?></small></label>
<label class="third">作品名<input name="title_name" required value="<?= h($titleForm['title_name']) ?>">
<small><?= h('例 ' . implode('・', array_slice(array_column($titles, 'title_name'), 0, 3))) ?></small></label>
<label class="stat">世代<input name="generation" type="number" min="1" max="99" required value="<?= h($titleForm['generation']) ?>"></label>
<label class="stat">地方<input name="region" value="<?= h($titleForm['region']) ?>">
<small>例 パルデア</small></label>
<button>作品を追加</button>
</form>
</details>

<h2>最近の登録</h2>
<div class="scroll"><table>
<?php foreach ($recent as $row): $detail = json_decode($row['detail'], true) ?: []; ?>
<tr>
<td><?= h($row['at']) ?></td>
<td><?= h($row['actor']) ?></td>
<td><?= h($actions[$row['action']] ?? $row['action']) ?></td>
<td><?= h($row['action'] === 'register_title'
    ? ($detail['title_group_id'] ?? '') . ' ' . ($detail['title_name'] ?? '')
    : ($detail['ndex_number'] ?? '') . ' ' . ($detail['name'] ?? '') . (isset($detail['form_name']) ? '（' . $detail['form_name'] . '）' : '') . ' / 作品 ' . ($detail['title_group_id'] ?? '') . ' / ' . implode('-', $detail['stats'] ?? [])) ?></td>
</tr>
<?php endforeach; ?>
</table></div>

<datalist id="abilities">
<?php foreach ($abilities as $ability): ?><option value="<?= h($ability) ?>"><?php endforeach; ?>
</datalist>
<datalist id="pokemon">
<?php foreach ($pokemon as $row): ?><option value="<?= h($row['ndex_number'] . ' ' . $row['name']) ?>"><?php endforeach; ?>
</datalist>
</body>
</html>
