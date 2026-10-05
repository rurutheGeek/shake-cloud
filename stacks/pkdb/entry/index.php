<?php
// ポケモンの登録画面（1ページ）。
//
// 値を集めて pokemondb.register_pokemon / register_title を呼ぶだけで、どの表へ何を
// 入れるかは stacks/pkdb/sql/entry.sql の関数が決める。接続は pkdb_entry ロールで、
// 表へ直接は書けない。入口（Caddy）が Authentik の Forward Auth を通した利用者名を
// X-Authentik-Username で渡すので、それを登録者として記録する。
declare(strict_types=1);

const STATS = ['h' => 'HP', 'a' => 'こうげき', 'b' => 'ぼうぎょ', 'c' => 'とくこう', 'd' => 'とくぼう', 's' => 'すばやさ'];

function h(?string $value): string
{
    return htmlspecialchars($value ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
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

function register_pokemon(PDO $pdo, string $actor): string
{
    $stats = [];
    foreach (STATS as $key => $label) {
        $stats[$key] = number($key, $label);
    }
    // 進化前は「0004 ヒトカゲ」の形で選ぶので、先頭の番号だけを使う。
    $before = preg_match('/^\s*(\d{1,4})/', field('before'), $match) ? $match[1] : '';
    $statement = $pdo->prepare(
        "SELECT register_pokemon(:actor, :ndex, :name, :form_id, :form_name, :title, :type_1, :type_2,
                :h, :a, :b, :c, :d, :s, :ability_1, :ability_2, :ability_h, :english, :before, '00',
                regexp_split_to_array(:aliases, '\\s*[,、]\\s*'))"
    );
    foreach ($stats as $key => $value) {
        $statement->bindValue(':' . $key, $value, PDO::PARAM_INT);
    }
    $statement->bindValue(':actor', $actor);
    $statement->bindValue(':ndex', field('ndex'));
    $statement->bindValue(':name', field('name'));
    $statement->bindValue(':form_id', field('form_id'));
    $statement->bindValue(':form_name', field('form_name'));
    $statement->bindValue(':title', field('title'));
    $statement->bindValue(':type_1', field('type_1'));
    $statement->bindValue(':type_2', field('type_2'));
    $statement->bindValue(':ability_1', field('ability_1'));
    $statement->bindValue(':ability_2', field('ability_2'));
    $statement->bindValue(':ability_h', field('ability_h'));
    $statement->bindValue(':english', field('english'));
    $statement->bindValue(':before', $before);
    $statement->bindValue(':aliases', field('aliases'));
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

$actor = trim((string) ($_SERVER['HTTP_X_AUTHENTIK_USERNAME'] ?? '')) ?: 'unknown';
$token = csrf_token();
$notice = '';
$error = '';
$keep = false;

try {
    $pdo = connect();
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
        if (!hash_equals($token, (string) ($_POST['csrf'] ?? ''))) {
            throw new InvalidArgumentException('ページを開き直してからもう一度送ってください');
        }
        try {
            $notice = field('action') === 'title' ? register_title($pdo, $actor) : register_pokemon($pdo, $actor);
        } catch (PDOException $exception) {
            $error = database_message($exception);
            $keep = true;
        } catch (InvalidArgumentException $exception) {
            $error = $exception->getMessage();
            $keep = true;
        }
    }
    $titles = $pdo->query('SELECT title_group_id, title_name FROM title_group ORDER BY title_group_id DESC')->fetchAll();
    $types = $pdo->query('SELECT name FROM type_data ORDER BY type_id')->fetchAll(PDO::FETCH_COLUMN);
    $abilities = $pdo->query('SELECT DISTINCT name FROM ability_data ORDER BY name')->fetchAll(PDO::FETCH_COLUMN);
    $pokemon = $pdo->query('SELECT ndex_number, name FROM pokemon_name ORDER BY ndex_number')->fetchAll();
    $next = (int) $pdo->query('SELECT coalesce(max(ndex_number::integer), 0) + 1 FROM pokemon_name')->fetchColumn();
    $recent = $pdo->query(
        "SELECT to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'MM/DD HH24:MI') AS at, actor, action, detail
         FROM entry_log ORDER BY id DESC LIMIT 10"
    )->fetchAll();
} catch (InvalidArgumentException $exception) {
    http_response_code(400);
    $error = $exception->getMessage();
    $titles = $types = $abilities = $pokemon = $recent = [];
    $next = 0;
} catch (PDOException $exception) {
    http_response_code(503);
    error_log('pkdb-entry: ' . $exception->getMessage());
    $error = 'データベースにつながりません';
    $titles = $types = $abilities = $pokemon = $recent = [];
    $next = 0;
}

$value = static fn (string $name, string $default = ''): string => h($keep ? field($name) : $default);
$selected = static fn (string $name, string $option, string $default = ''): string =>
    ($keep ? field($name) : $default) === $option ? ' selected' : '';
$pokemonAction = !$keep || field('action') !== 'title';
?>
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ポケモン登録</title>
<style>
:root { color-scheme: light dark; --line: #8884; --accent: #2f6fde; }
body { font-family: system-ui, sans-serif; margin: 0 auto; padding: 16px; max-width: 760px; line-height: 1.5; }
h1 { font-size: 1.3rem; margin: 0 0 12px; }
h2 { font-size: 1rem; margin: 24px 0 8px; }
form { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
label { display: grid; gap: 2px; font-size: .8rem; grid-column: span 3; }
label.wide { grid-column: span 6; }
label.stat { grid-column: span 1; }
label.third { grid-column: span 2; }
input, select, button { font: inherit; padding: 8px; border: 1px solid var(--line); border-radius: 6px; min-width: 0; background: Canvas; color: CanvasText; }
button { grid-column: span 6; background: var(--accent); color: #fff; border: 0; font-weight: 600; cursor: pointer; }
.message { padding: 10px 12px; border-radius: 6px; margin: 0 0 12px; }
.ok { background: #1f9d5522; border: 1px solid #1f9d55; }
.ng { background: #d6454522; border: 1px solid #d64545; }
details { border: 1px solid var(--line); border-radius: 6px; padding: 8px 12px; margin-top: 24px; }
summary { cursor: pointer; font-weight: 600; }
details form { margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
td, th { border-bottom: 1px solid var(--line); padding: 6px 4px; text-align: left; }
@media (max-width: 520px) { label, label.third { grid-column: span 6; } label.stat { grid-column: span 2; } }
</style>
</head>
<body>
<h1>ポケモン登録</h1>
<?php if ($notice !== ''): ?><p class="message ok"><?= h($notice) ?></p><?php endif; ?>
<?php if ($error !== ''): ?><p class="message ng"><?= h($error) ?></p><?php endif; ?>

<form method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= h($token) ?>">
<input type="hidden" name="action" value="pokemon">
<label>図鑑番号<input name="ndex" inputmode="numeric" pattern="[0-9]{1,4}" required value="<?= $pokemonAction ? $value('ndex', (string) $next) : h((string) $next) ?>"></label>
<label>名前<input name="name" value="<?= $pokemonAction ? $value('name') : '' ?>"></label>
<label>英語名<input name="english" value="<?= $pokemonAction ? $value('english') : '' ?>"></label>
<label>作品<select name="title" required>
<?php foreach ($titles as $index => $title): ?>
<option value="<?= h($title['title_group_id']) ?>"<?= $selected('title', $title['title_group_id'], $index === 0 ? $title['title_group_id'] : '') ?>><?= h($title['title_group_id'] . ' ' . $title['title_name']) ?></option>
<?php endforeach; ?>
</select></label>
<label>フォーム番号<input name="form_id" inputmode="numeric" pattern="[0-9]{1,2}" value="<?= $pokemonAction ? $value('form_id', '00') : '00' ?>"></label>
<label>姿の名前<input name="form_name" value="<?= $pokemonAction ? $value('form_name') : '' ?>"></label>
<label>タイプ1<select name="type_1" required>
<option value=""></option>
<?php foreach ($types as $type): ?><option<?= $selected('type_1', $type) ?>><?= h($type) ?></option><?php endforeach; ?>
</select></label>
<label>タイプ2<select name="type_2">
<option value=""></option>
<?php foreach ($types as $type): ?><option<?= $selected('type_2', $type) ?>><?= h($type) ?></option><?php endforeach; ?>
</select></label>
<?php foreach (STATS as $key => $label): ?>
<label class="stat"><?= h($label) ?><input name="<?= $key ?>" type="number" min="1" max="255" required value="<?= $pokemonAction ? $value($key) : '' ?>"></label>
<?php endforeach; ?>
<label class="third">特性1<input name="ability_1" list="abilities" value="<?= $pokemonAction ? $value('ability_1') : '' ?>"></label>
<label class="third">特性2<input name="ability_2" list="abilities" value="<?= $pokemonAction ? $value('ability_2') : '' ?>"></label>
<label class="third">隠れ特性<input name="ability_h" list="abilities" value="<?= $pokemonAction ? $value('ability_h') : '' ?>"></label>
<label>進化前<input name="before" list="pokemon" value="<?= $pokemonAction ? $value('before') : '' ?>"></label>
<label>あだ名<input name="aliases" value="<?= $pokemonAction ? $value('aliases') : '' ?>"></label>
<button>登録</button>
</form>

<details<?= $pokemonAction ? '' : ' open' ?>>
<summary>作品を追加</summary>
<form method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= h($token) ?>">
<input type="hidden" name="action" value="title">
<label class="third">作品ID<input name="title_id" inputmode="numeric" pattern="[0-9]{3}" required value="<?= $pokemonAction ? '' : $value('title_id') ?>"></label>
<label class="third">作品名<input name="title_name" required value="<?= $pokemonAction ? '' : $value('title_name') ?>"></label>
<label class="stat">世代<input name="generation" type="number" min="1" max="99" required value="<?= $pokemonAction ? '' : $value('generation') ?>"></label>
<label class="stat">地方<input name="region" value="<?= $pokemonAction ? '' : $value('region') ?>"></label>
<button>作品を追加</button>
</form>
</details>

<h2>最近の登録</h2>
<table>
<?php foreach ($recent as $row): $detail = json_decode($row['detail'], true) ?: []; ?>
<tr>
<td><?= h($row['at']) ?></td>
<td><?= h($row['actor']) ?></td>
<td><?= $row['action'] === 'register_title'
    ? h('作品 ' . ($detail['title_group_id'] ?? '') . ' ' . ($detail['title_name'] ?? ''))
    : h(($detail['ndex_number'] ?? '') . ' ' . ($detail['name'] ?? '') . (isset($detail['form_name']) ? '（' . $detail['form_name'] . '）' : '') . ' / ' . ($detail['title_group_id'] ?? '') . ' / ' . implode('-', $detail['stats'] ?? [])) ?></td>
</tr>
<?php endforeach; ?>
</table>

<datalist id="abilities">
<?php foreach ($abilities as $ability): ?><option value="<?= h($ability) ?>"><?php endforeach; ?>
</datalist>
<datalist id="pokemon">
<?php foreach ($pokemon as $row): ?><option value="<?= h($row['ndex_number'] . ' ' . $row['name']) ?>"><?php endforeach; ?>
</datalist>
</body>
</html>
