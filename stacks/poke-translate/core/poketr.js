// ポケモン用語を公式名に固定する翻訳の本体。翻訳サイト・拡張機能・テストで共用する。
//
// 原文の用語を ⟦n⟧ に置き換えて翻訳エンジンへ渡し、訳文の ⟦n⟧ を訳先言語の
// 公式名へ戻す。辞書（dictionary.json）は manage.py が PokéAPI と
// custom-terms.json から作る。Google翻訳の呼び出しは GoogleWeb だけに閉じる。
(function (root) {
  'use strict';

  const LANGUAGES = {
    ja: '日本語', en: 'English', ko: '한국어', 'zh-TW': '繁體中文', 'zh-CN': '简体中文',
    fr: 'Français', de: 'Deutsch', es: 'Español', it: 'Italiano',
  };
  const CJK = new Set(['ja', 'ko', 'zh-TW', 'zh-CN']);
  // 同じ表記が複数の種別にあるときは先の種別を採る（例: Psychic はタイプより技）。
  const KINDS = ['species', 'move', 'ability', 'item', 'type', 'nature', 'location', 'form', 'stat'];
  const PLACEHOLDER = /[⟦【]\s*(\d+)\s*[⟧】]/g;
  const PLACEHOLDER_CJK = /[ \t　]*[⟦【]\s*(\d+)\s*[⟧】][ \t　]*/g;
  // まとめ訳の区切り。⟦0⟧ は用語の番号に使わないので restore は触らない。
  const SEPARATOR = '\n⟦0⟧\n';
  const SPLIT = /\s*[⟦【]\s*0\s*[⟧】]\s*/;
  const HIRAGANA = /^[ぁ-ゟ]+$/;

  const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  class Glossary {
    constructor(dictionary) {
      this.entries = dictionary.entries || {};
      this.source = dictionary.source || 'custom only';
      this.exclude = toSets(dictionary.exclude);
      this.ambiguous = toSets(dictionary.ambiguous);
      this.patterns = new Map();
    }

    rank(key) {
      if (this.entries[key]._custom) return 0;
      const index = KINDS.indexOf(key.split(':', 1)[0]);
      return index < 0 ? 99 : index + 1;
    }

    usable(language, name) {
      if (this.exclude[language]?.has(name)) return false;
      // 「くさ」「みず」「あく」は普通の文章に紛れるので単独では照合しない。
      if (language === 'ja' && [...name].length <= 2 && HIRAGANA.test(name)) return false;
      return [...name].length >= 2;
    }

    pattern(language) {
      if (!this.patterns.has(language)) {
        const owners = new Map();
        const keys = Object.keys(this.entries).sort((a, b) => this.rank(a) - this.rank(b));
        for (const key of keys) {
          for (const name of this.entries[key][language] || []) {
            if (this.usable(language, name) && !owners.has(name)) owners.set(name, key);
          }
        }
        const alternatives = [...owners.keys()].sort((a, b) => b.length - a.length)
          .map(escape).join('|');
        let regex = null;
        if (alternatives && CJK.has(language)) regex = new RegExp(alternatives, 'gu');
        else if (alternatives) {
          regex = new RegExp(`(?<![\\p{L}\\p{N}_'’-])(?:${alternatives})(?![\\p{L}\\p{N}_’-])`, 'gu');
        }
        this.patterns.set(language, { regex, owners });
      }
      return this.patterns.get(language);
    }

    find(text, language) {
      const { regex, owners } = this.pattern(language);
      if (!regex) return [];
      const ambiguous = this.ambiguous[language] || new Set();
      const found = [];
      for (const match of text.matchAll(regex)) {
        // 「Return to …」「Bold text」のように普通の単語でありうる名前は、
        // 文頭では用語とみなさない。
        if (ambiguous.has(match[0]) && sentenceStart(text, match.index)) continue;
        found.push([match.index, match.index + match[0].length, owners.get(match[0])]);
      }
      return found;
    }

    name(key, language) {
      return this.entries[key]?.[language]?.[0] ?? null;
    }

    lookup(query, limit = 20) {
      const needle = query.trim().toLowerCase();
      const found = [];
      if (!needle) return found;
      for (const [key, names] of Object.entries(this.entries)) {
        const languages = Object.entries(names).filter(([language]) => !language.startsWith('_'));
        if (languages.some(([, values]) => values.some((value) => value.toLowerCase().includes(needle)))) {
          found.push({ key, names: Object.fromEntries(languages) });
          if (found.length >= limit) break;
        }
      }
      return found;
    }
  }

  function toSets(lists) {
    return Object.fromEntries(Object.entries(lists || {}).map(([language, words]) => [language, new Set(words)]));
  }

  function sentenceStart(text, position) {
    const before = text.slice(0, position).replace(/[ \t"'“‘(*_]+$/, '');
    // 「Nature: Bold」「- Return」のような項目・箇条書きは用語として扱う。
    return !before || '.!?\n'.includes(before.at(-1));
  }

  function detect(text) {
    if (/[぀-ヿ]/.test(text)) return 'ja';
    if (/[가-힯]/.test(text)) return 'ko';
    if (/[一-鿿]/.test(text)) return 'zh-CN';
    return 'en';
  }

  // 用語を ⟦n⟧ に置き換える。まとめて訳す文どうしで番号が重ならないよう first から振る。
  function protect(glossary, text, source, target, first = 1) {
    const numbers = new Map();
    const replacements = new Map();
    const used = [];
    let output = '';
    let position = 0;
    for (const [start, end, key] of glossary.find(text, source)) {
      const rendered = glossary.name(key, target);
      if (rendered === null) continue; // 訳先に表記がない用語はエンジンに任せる。
      if (!numbers.has(key)) {
        numbers.set(key, numbers.size + first);
        replacements.set(numbers.get(key), rendered);
        used.push({ key, source: text.slice(start, end), target: rendered });
      }
      output += text.slice(position, start) + `⟦${numbers.get(key)}⟧`;
      position = end;
    }
    return { protected: output + text.slice(position), replacements, used };
  }

  // ⟦n⟧ を訳語へ戻す。CJK の訳文ではエンジンが前後に挟んだ空白も消す。
  function restore(text, replacements, target) {
    const seen = new Set();
    const pattern = CJK.has(target) ? PLACEHOLDER_CJK : PLACEHOLDER;
    const restored = text.replace(pattern, (whole, number) => {
      if (!replacements.has(Number(number))) return whole;
      seen.add(Number(number));
      return replacements.get(Number(number));
    });
    const missing = [...replacements.keys()].filter((n) => !seen.has(n)).sort((a, b) => a - b)
      .map((n) => replacements.get(n));
    return { text: restored, missing };
  }

  // 行単位で limit 文字以下に分ける（GET の URL 長制限のため）。
  function chunks(text, limit = 1500) {
    const parts = [];
    let current = '';
    for (let line of text.split(/(?<=\n)/)) {
      while (line.length > limit) {
        if (current) { parts.push(current); current = ''; }
        parts.push(line.slice(0, limit));
        line = line.slice(limit);
      }
      if (current.length + line.length > limit) { parts.push(current); current = ''; }
      current += line;
    }
    if (current) parts.push(current);
    return parts;
  }

  const dropped = (missing) => missing.map((name) => `訳文から用語が落ちました: ${name}`);

  async function translateText(engine, text, source, target) {
    let output = '';
    for (const part of chunks(text)) output += await engine.translate(part, source, target);
    return output;
  }

  // 複数の文を1回の翻訳呼び出しにまとめる。ページの段落を1件ずつ送ると外部
  // サービスにすぐ遮断されるため、⟦0⟧ で連結して送り、訳文を分け直す。
  // 数が合わなければ1件ずつ訳す。
  async function translateMany(glossary, engine, texts, source, target) {
    if (source === 'auto') source = detect(texts.join('\n'));
    const items = [];
    let first = 1;
    for (const text of texts) {
      const item = protect(glossary, text, source, target, first);
      first += item.replacements.size;
      items.push(item);
    }
    const joined = items.map((item) => item.protected).join(SEPARATOR);
    let parts = (await translateText(engine, joined, source, target)).trim().split(SPLIT);
    if (parts.length !== items.length) {
      parts = [];
      for (const item of items) parts.push(await translateText(engine, item.protected, source, target));
    }
    const results = parts.map((part, i) => {
      const { text, missing } = restore(part.trim(), items[i].replacements, target);
      return { text, used: items[i].used, warnings: dropped(missing) };
    });
    return {
      translatedText: results.map((result) => result.text),
      detectedLanguage: { language: source },
      terms: results.flatMap((result) => result.used),
      warnings: results.flatMap((result) => result.warnings),
    };
  }

  async function translate(glossary, engine, text, source, target) {
    const result = await translateMany(glossary, engine, [text], source, target);
    return { ...result, translatedText: result.translatedText[0] };
  }

  // 翻訳エンジンを通さず用語だけを置き換える（Showdown形式の型・コード欄用）。
  function replaceTerms(glossary, texts, source, target) {
    if (source === 'auto') source = detect(texts.join('\n'));
    const results = texts.map((text) => {
      const item = protect(glossary, text, source, target);
      return {
        text: item.protected.replace(PLACEHOLDER, (whole, n) => item.replacements.get(Number(n)) ?? whole),
        used: item.used,
      };
    });
    return {
      translatedText: results.map((result) => result.text),
      detectedLanguage: { language: source },
      terms: results.flatMap((result) => result.used),
      warnings: [],
    };
  }

  class EngineError extends Error {}

  // Google翻訳の非公式Webエンドポイント。Chrome拡張と同じ client 名で GET する
  // （client=gtx や POST は自動アクセスとして弾かれやすい）。保証はなく、遮断や
  // 仕様変更で使えなくなりうるので、エンジンは translate(text, source, target)
  // を持つ別のオブジェクトに差し替えられるようにしてある。
  class GoogleWeb {
    constructor({ fetch = root.fetch.bind(root), client = 'dict-chrome-ex' } = {}) {
      this.fetch = fetch;
      this.client = client;
    }

    async translate(text, source, target) {
      if (!text.trim()) return text;
      const url = new URL('https://translate.googleapis.com/translate_a/single');
      for (const [key, value] of Object.entries({ client: this.client, sl: source, tl: target, dt: 't', q: text })) {
        url.searchParams.set(key, value);
      }
      let response;
      try {
        response = await this.fetch(url);
      } catch (error) {
        throw new EngineError(`Google翻訳へ接続できません: ${error.message}`);
      }
      let segments;
      try {
        segments = (await response.json())[0] || [];
      } catch {
        throw new EngineError(`Google翻訳が想定外の応答を返しました（HTTP ${response.status}、遮断の可能性）`);
      }
      return segments.filter((segment) => segment && segment[0]).map((segment) => segment[0]).join('');
    }
  }

  const PokeTr = {
    LANGUAGES, Glossary, GoogleWeb, EngineError,
    detect, protect, restore, chunks, translate, translateMany, replaceTerms,
  };
  if (typeof module === 'object' && module.exports) module.exports = PokeTr;
  else root.PokeTr = PokeTr;
})(typeof globalThis === 'object' ? globalThis : this);
