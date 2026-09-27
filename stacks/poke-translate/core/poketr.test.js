// node --test で実行する。辞書は tests/test_poke_translate.py が小さな CSV から
// dictionary.py で作り、POKETR_FIXTURE で渡す（辞書の作成から照合まで通して確かめる）。
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const PokeTr = require('./poketr.js');

const fixture = JSON.parse(fs.readFileSync(process.env.POKETR_FIXTURE, 'utf8'));
const glossary = (extra = {}) => new PokeTr.Glossary({ ...fixture, ...extra });
const keys = (g, text, language) => g.find(text, language).map(([, , key]) => key);
const nameOf = (g, text) => g.name(g.find(text, 'en')[0][2], 'ja');

class Fake {
  constructor(reply = (text) => text) { this.calls = []; this.reply = reply; }
  async translate(text) { this.calls.push(text); return this.reply(text); }
}

test('longest name wins', () => {
  assert.deepEqual(keys(glossary(), 'メガリザードンXとリザードン', 'ja'), ['form:10134', 'species:6']);
});

test('short hiragana names are not matched inside ordinary words', () => {
  assert.deepEqual(keys(glossary(), 'くさい', 'ja'), []);
  assert.deepEqual(keys(glossary(), 'くさタイプ', 'ja'), ['type:12:typed']);
});

test('english names respect word boundaries and exclusions', () => {
  const g = glossary({ exclude: { en: ['Bold'] } });
  assert.deepEqual(keys(g, 'Earthquakes', 'en'), []);
  assert.deepEqual(keys(g, 'a Bold plan', 'en'), []);
  assert.deepEqual(keys(g, 'Earthquake!', 'en'), ['move:89']);
});

test('ambiguous words are terms only inside a sentence', () => {
  const g = glossary({ ambiguous: { en: ['Bold'] }, exclude: {} });
  assert.deepEqual(keys(g, 'Bold moves ahead.', 'en'), []);
  assert.deepEqual(keys(g, 'It works. Bold', 'en'), []);
  assert.deepEqual(keys(g, 'Nature: Bold', 'en'), ['nature:2']);
  assert.deepEqual(keys(g, 'with a Bold nature', 'en'), ['nature:2']);
});

test('moves win over types, and type phrases resolve the type', () => {
  const g = glossary();
  assert.deepEqual(keys(g, 'Psychic', 'en'), ['move:94']);
  assert.equal(nameOf(g, 'Psychic immunity'), 'エスパー無効');
  assert.equal(nameOf(g, 'Grass-types'), 'くさタイプ');
  assert.equal(nameOf(g, 'Tera Grass'), 'くさテラス');
  assert.equal(nameOf(g, 'Landorus-Therian'), 'ランドロス（れいじゅうフォルム）');
});

test('custom terms win over official names', () => {
  const g = glossary();
  assert.equal(nameOf(g, 'STAB'), 'タイプ一致');
  assert.deepEqual(keys(g, 'ガブ', 'ja'), ['species:445']);
});

test('terms are protected and restored', async () => {
  const engine = new Fake((text) => text.replace('の', "'s ").replace('は強い。', ' is strong.'));
  const result = await PokeTr.translate(glossary(), engine, 'ガブリアスのじしんは強い。', 'ja', 'en');
  assert.deepEqual(engine.calls, ['⟦1⟧の⟦2⟧は強い。']);
  assert.equal(result.translatedText, "Garchomp's Earthquake is strong.");
  assert.deepEqual(result.terms.map((term) => term.key), ['species:445', 'move:89']);
  assert.deepEqual(result.warnings, []);
});

test('spaces the engine adds are removed in CJK and kept in latin targets', () => {
  const ja = PokeTr.restore('⟦1⟧ は ⟦2⟧ を使う', new Map([[1, 'ガブリアス'], [2, 'じしん']]), 'ja');
  assert.deepEqual(ja, { text: 'ガブリアスはじしんを使う', missing: [] });
  const en = PokeTr.restore('⟦1⟧ uses ⟦2⟧.', new Map([[1, 'Garchomp'], [2, 'Earthquake']]), 'en');
  assert.equal(en.text, 'Garchomp uses Earthquake.');
});

test('dropped placeholders are reported', async () => {
  const result = await PokeTr.translate(glossary(), new Fake(() => 'nothing'), 'じしん', 'ja', 'en');
  assert.deepEqual(result.warnings, ['訳文から用語が落ちました: Earthquake']);
});

test('repeated terms share one placeholder and unknown targets are left alone', () => {
  const same = PokeTr.protect(glossary(), 'Garchomp, Garchomp', 'en', 'ja');
  assert.equal(same.protected, '⟦1⟧, ⟦1⟧');
  assert.equal(PokeTr.protect(glossary(), 'じしん', 'ja', 'fr').protected, 'じしん');
});

test('batches are split back and keep line breaks', async () => {
  const engine = new Fake();
  const result = await PokeTr.translateMany(glossary(), engine, ['Garchomp', 'a\nb', 'Earthquake'], 'en', 'ja');
  assert.deepEqual(engine.calls, ['⟦1⟧\n⟦0⟧\na\nb\n⟦0⟧\n⟦2⟧']);
  assert.deepEqual(result.translatedText, ['ガブリアス', 'a\nb', 'じしん']);
});

test('batches fall back to one call per item when separators are lost', async () => {
  const engine = new Fake((text) => text.replaceAll('⟦0⟧', ''));
  const result = await PokeTr.translateMany(glossary(), engine, ['x', 'y'], 'en', 'ja');
  assert.equal(engine.calls.length, 3);
  assert.equal(result.translatedText.length, 2);
});

test('showdown sets get terms replaced without the engine', () => {
  const text = 'Chompy (Garchomp) @ Choice Scarf\nBold Nature\n- Earthquake';
  assert.deepEqual(PokeTr.replaceTerms(glossary(), [text], 'en', 'ja').translatedText,
    ['Chompy (ガブリアス) @ こだわりスカーフ\n性格: ずぶとい\n- じしん']);
});

test('long text is split on lines within the limit', () => {
  const text = 'a'.repeat(5) + '\n' + 'b'.repeat(12) + '\n';
  const parts = PokeTr.chunks(text, 8);
  assert.ok(parts.every((part) => part.length <= 8));
  assert.equal(parts.join(''), text);
});

test('source detection', () => {
  assert.equal(PokeTr.detect('ガブリアス'), 'ja');
  assert.equal(PokeTr.detect('한국어'), 'ko');
  assert.equal(PokeTr.detect('Garchomp'), 'en');
});

test('google web joins segments and reports blocked responses', async () => {
  const urls = [];
  const ok = new PokeTr.GoogleWeb({
    fetch: async (url) => { urls.push(String(url)); return { status: 200, json: async () => [[['A. ', 'x'], ['B', 'y']], null, 'ja'] }; },
  });
  assert.equal(await ok.translate('x', 'ja', 'en'), 'A. B');
  assert.match(urls[0], /client=dict-chrome-ex/);
  const blocked = new PokeTr.GoogleWeb({
    fetch: async () => ({ status: 429, json: async () => { throw new SyntaxError('html'); } }),
  });
  await assert.rejects(blocked.translate('x', 'ja', 'en'), PokeTr.EngineError);
});
