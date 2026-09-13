(() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __commonJS = (cb, mod) => function __require() {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  };
  var __export = (target, all3) => {
    for (var name in all3)
      __defProp(target, name, { get: all3[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
    // If the importer is in node compatibility mode or this is not an ESM
    // file that has been converted to a CommonJS file using a Babel-
    // compatible transform (i.e. "__esModule" has not been set), then set
    // "default" to the CommonJS "module.exports" for node compatibility.
    isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
    mod
  ));
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

  // node_modules/semver/internal/debug.js
  var require_debug = __commonJS({
    "node_modules/semver/internal/debug.js"(exports, module) {
      "use strict";
      var debug = typeof process === "object" && process.env && process.env.NODE_DEBUG && /\bsemver\b/i.test(process.env.NODE_DEBUG) ? (...args) => console.error("SEMVER", ...args) : () => {
      };
      module.exports = debug;
    }
  });

  // node_modules/semver/internal/constants.js
  var require_constants = __commonJS({
    "node_modules/semver/internal/constants.js"(exports, module) {
      "use strict";
      var SEMVER_SPEC_VERSION = "2.0.0";
      var MAX_LENGTH = 256;
      var MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER || /* istanbul ignore next */
      9007199254740991;
      var MAX_SAFE_COMPONENT_LENGTH = 16;
      var MAX_SAFE_BUILD_LENGTH = MAX_LENGTH - 6;
      var RELEASE_TYPES = [
        "major",
        "premajor",
        "minor",
        "preminor",
        "patch",
        "prepatch",
        "prerelease"
      ];
      module.exports = {
        MAX_LENGTH,
        MAX_SAFE_COMPONENT_LENGTH,
        MAX_SAFE_BUILD_LENGTH,
        MAX_SAFE_INTEGER,
        RELEASE_TYPES,
        SEMVER_SPEC_VERSION,
        FLAG_INCLUDE_PRERELEASE: 1,
        FLAG_LOOSE: 2
      };
    }
  });

  // node_modules/semver/internal/re.js
  var require_re = __commonJS({
    "node_modules/semver/internal/re.js"(exports, module) {
      "use strict";
      var {
        MAX_SAFE_COMPONENT_LENGTH,
        MAX_SAFE_BUILD_LENGTH,
        MAX_LENGTH
      } = require_constants();
      var debug = require_debug();
      exports = module.exports = {};
      var re = exports.re = [];
      var safeRe = exports.safeRe = [];
      var src = exports.src = [];
      var safeSrc = exports.safeSrc = [];
      var t = exports.t = {};
      var R = 0;
      var LETTERDASHNUMBER = "[a-zA-Z0-9-]";
      var safeRegexReplacements = [
        ["\\s", 1],
        ["\\d", MAX_LENGTH],
        [LETTERDASHNUMBER, MAX_SAFE_BUILD_LENGTH]
      ];
      var makeSafeRegex = (value) => {
        for (const [token, max] of safeRegexReplacements) {
          value = value.split(`${token}*`).join(`${token}{0,${max}}`).split(`${token}+`).join(`${token}{1,${max}}`);
        }
        return value;
      };
      var createToken = (name, value, isGlobal) => {
        const safe = makeSafeRegex(value);
        const index = R++;
        debug(name, index, value);
        t[name] = index;
        src[index] = value;
        safeSrc[index] = safe;
        re[index] = new RegExp(value, isGlobal ? "g" : void 0);
        safeRe[index] = new RegExp(safe, isGlobal ? "g" : void 0);
      };
      createToken("NUMERICIDENTIFIER", "0|[1-9]\\d*");
      createToken("NUMERICIDENTIFIERLOOSE", "\\d+");
      createToken("NONNUMERICIDENTIFIER", `\\d*[a-zA-Z-]${LETTERDASHNUMBER}*`);
      createToken("MAINVERSION", `(${src[t.NUMERICIDENTIFIER]})\\.(${src[t.NUMERICIDENTIFIER]})\\.(${src[t.NUMERICIDENTIFIER]})`);
      createToken("MAINVERSIONLOOSE", `(${src[t.NUMERICIDENTIFIERLOOSE]})\\.(${src[t.NUMERICIDENTIFIERLOOSE]})\\.(${src[t.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASEIDENTIFIER", `(?:${src[t.NONNUMERICIDENTIFIER]}|${src[t.NUMERICIDENTIFIER]})`);
      createToken("PRERELEASEIDENTIFIERLOOSE", `(?:${src[t.NONNUMERICIDENTIFIER]}|${src[t.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASE", `(?:-(${src[t.PRERELEASEIDENTIFIER]}(?:\\.${src[t.PRERELEASEIDENTIFIER]})*))`);
      createToken("PRERELEASELOOSE", `(?:-?(${src[t.PRERELEASEIDENTIFIERLOOSE]}(?:\\.${src[t.PRERELEASEIDENTIFIERLOOSE]})*))`);
      createToken("BUILDIDENTIFIER", `${LETTERDASHNUMBER}+`);
      createToken("BUILD", `(?:\\+(${src[t.BUILDIDENTIFIER]}(?:\\.${src[t.BUILDIDENTIFIER]})*))`);
      createToken("FULLPLAIN", `v?${src[t.MAINVERSION]}${src[t.PRERELEASE]}?${src[t.BUILD]}?`);
      createToken("FULL", `^${src[t.FULLPLAIN]}$`);
      createToken("LOOSEPLAIN", `[v=\\s]*${src[t.MAINVERSIONLOOSE]}${src[t.PRERELEASELOOSE]}?${src[t.BUILD]}?`);
      createToken("LOOSE", `^${src[t.LOOSEPLAIN]}$`);
      createToken("GTLT", "((?:<|>)?=?)");
      createToken("XRANGEIDENTIFIERLOOSE", `${src[t.NUMERICIDENTIFIERLOOSE]}|x|X|\\*`);
      createToken("XRANGEIDENTIFIER", `${src[t.NUMERICIDENTIFIER]}|x|X|\\*`);
      createToken("XRANGEPLAIN", `[v=\\s]*(${src[t.XRANGEIDENTIFIER]})(?:\\.(${src[t.XRANGEIDENTIFIER]})(?:\\.(${src[t.XRANGEIDENTIFIER]})(?:${src[t.PRERELEASE]})?${src[t.BUILD]}?)?)?`);
      createToken("XRANGEPLAINLOOSE", `[v=\\s]*(${src[t.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t.XRANGEIDENTIFIERLOOSE]})(?:${src[t.PRERELEASELOOSE]})?${src[t.BUILD]}?)?)?`);
      createToken("XRANGE", `^${src[t.GTLT]}\\s*${src[t.XRANGEPLAIN]}$`);
      createToken("XRANGELOOSE", `^${src[t.GTLT]}\\s*${src[t.XRANGEPLAINLOOSE]}$`);
      createToken("COERCEPLAIN", `${"(^|[^\\d])(\\d{1,"}${MAX_SAFE_COMPONENT_LENGTH}})(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?`);
      createToken("COERCE", `${src[t.COERCEPLAIN]}(?:$|[^\\d])`);
      createToken("COERCEFULL", src[t.COERCEPLAIN] + `(?:${src[t.PRERELEASE]})?(?:${src[t.BUILD]})?(?:$|[^\\d])`);
      createToken("COERCERTL", src[t.COERCE], true);
      createToken("COERCERTLFULL", src[t.COERCEFULL], true);
      createToken("LONETILDE", "(?:~>?)");
      createToken("TILDETRIM", `(\\s*)${src[t.LONETILDE]}\\s+`, true);
      exports.tildeTrimReplace = "$1~";
      createToken("TILDE", `^${src[t.LONETILDE]}${src[t.XRANGEPLAIN]}$`);
      createToken("TILDELOOSE", `^${src[t.LONETILDE]}${src[t.XRANGEPLAINLOOSE]}$`);
      createToken("LONECARET", "(?:\\^)");
      createToken("CARETTRIM", `(\\s*)${src[t.LONECARET]}\\s+`, true);
      exports.caretTrimReplace = "$1^";
      createToken("CARET", `^${src[t.LONECARET]}${src[t.XRANGEPLAIN]}$`);
      createToken("CARETLOOSE", `^${src[t.LONECARET]}${src[t.XRANGEPLAINLOOSE]}$`);
      createToken("COMPARATORLOOSE", `^${src[t.GTLT]}\\s*(${src[t.LOOSEPLAIN]})$|^$`);
      createToken("COMPARATOR", `^${src[t.GTLT]}\\s*(${src[t.FULLPLAIN]})$|^$`);
      createToken("COMPARATORTRIM", `(\\s*)${src[t.GTLT]}\\s*(${src[t.LOOSEPLAIN]}|${src[t.XRANGEPLAIN]})`, true);
      exports.comparatorTrimReplace = "$1$2$3";
      createToken("HYPHENRANGE", `^\\s*(${src[t.XRANGEPLAIN]})\\s+-\\s+(${src[t.XRANGEPLAIN]})\\s*$`);
      createToken("HYPHENRANGELOOSE", `^\\s*(${src[t.XRANGEPLAINLOOSE]})\\s+-\\s+(${src[t.XRANGEPLAINLOOSE]})\\s*$`);
      createToken("STAR", "(<|>)?=?\\s*\\*");
      createToken("GTE0", "^\\s*>=\\s*0\\.0\\.0\\s*$");
      createToken("GTE0PRE", "^\\s*>=\\s*0\\.0\\.0-0\\s*$");
    }
  });

  // node_modules/semver/internal/parse-options.js
  var require_parse_options = __commonJS({
    "node_modules/semver/internal/parse-options.js"(exports, module) {
      "use strict";
      var looseOption = Object.freeze({ loose: true });
      var emptyOpts = Object.freeze({});
      var parseOptions = (options) => {
        if (!options) {
          return emptyOpts;
        }
        if (typeof options !== "object") {
          return looseOption;
        }
        return options;
      };
      module.exports = parseOptions;
    }
  });

  // node_modules/semver/internal/identifiers.js
  var require_identifiers = __commonJS({
    "node_modules/semver/internal/identifiers.js"(exports, module) {
      "use strict";
      var numeric = /^[0-9]+$/;
      var compareIdentifiers = (a, b) => {
        if (typeof a === "number" && typeof b === "number") {
          return a === b ? 0 : a < b ? -1 : 1;
        }
        const anum = numeric.test(a);
        const bnum = numeric.test(b);
        if (anum && bnum) {
          a = +a;
          b = +b;
        }
        return a === b ? 0 : anum && !bnum ? -1 : bnum && !anum ? 1 : a < b ? -1 : 1;
      };
      var rcompareIdentifiers = (a, b) => compareIdentifiers(b, a);
      module.exports = {
        compareIdentifiers,
        rcompareIdentifiers
      };
    }
  });

  // node_modules/semver/classes/semver.js
  var require_semver = __commonJS({
    "node_modules/semver/classes/semver.js"(exports, module) {
      "use strict";
      var debug = require_debug();
      var { MAX_LENGTH, MAX_SAFE_INTEGER } = require_constants();
      var { safeRe: re, t } = require_re();
      var parseOptions = require_parse_options();
      var { compareIdentifiers } = require_identifiers();
      var isPrereleaseIdentifier = (prerelease, identifier) => {
        const identifiers = identifier.split(".");
        if (identifiers.length > prerelease.length) {
          return false;
        }
        for (let i = 0; i < identifiers.length; i++) {
          if (compareIdentifiers(prerelease[i], identifiers[i]) !== 0) {
            return false;
          }
        }
        return true;
      };
      var SemVer = class _SemVer {
        constructor(version, options) {
          options = parseOptions(options);
          if (version instanceof _SemVer) {
            if (version.loose === !!options.loose && version.includePrerelease === !!options.includePrerelease) {
              return version;
            } else {
              version = version.version;
            }
          } else if (typeof version !== "string") {
            throw new TypeError(`Invalid version. Must be a string. Got type "${typeof version}".`);
          }
          if (version.length > MAX_LENGTH) {
            throw new TypeError(
              `version is longer than ${MAX_LENGTH} characters`
            );
          }
          debug("SemVer", version, options);
          this.options = options;
          this.loose = !!options.loose;
          this.includePrerelease = !!options.includePrerelease;
          const m = version.trim().match(options.loose ? re[t.LOOSE] : re[t.FULL]);
          if (!m) {
            throw new TypeError(`Invalid Version: ${version}`);
          }
          this.raw = version;
          this.major = +m[1];
          this.minor = +m[2];
          this.patch = +m[3];
          if (this.major > MAX_SAFE_INTEGER || this.major < 0) {
            throw new TypeError("Invalid major version");
          }
          if (this.minor > MAX_SAFE_INTEGER || this.minor < 0) {
            throw new TypeError("Invalid minor version");
          }
          if (this.patch > MAX_SAFE_INTEGER || this.patch < 0) {
            throw new TypeError("Invalid patch version");
          }
          if (!m[4]) {
            this.prerelease = [];
          } else {
            this.prerelease = m[4].split(".").map((id) => {
              if (/^[0-9]+$/.test(id)) {
                const num = +id;
                if (num >= 0 && num < MAX_SAFE_INTEGER) {
                  return num;
                }
              }
              return id;
            });
          }
          this.build = m[5] ? m[5].split(".") : [];
          this.format();
        }
        format() {
          this.version = `${this.major}.${this.minor}.${this.patch}`;
          if (this.prerelease.length) {
            this.version += `-${this.prerelease.join(".")}`;
          }
          return this.version;
        }
        toString() {
          return this.version;
        }
        compare(other) {
          debug("SemVer.compare", this.version, this.options, other);
          if (!(other instanceof _SemVer)) {
            if (typeof other === "string" && other === this.version) {
              return 0;
            }
            other = new _SemVer(other, this.options);
          }
          if (other.version === this.version) {
            return 0;
          }
          return this.compareMain(other) || this.comparePre(other);
        }
        compareMain(other) {
          if (!(other instanceof _SemVer)) {
            other = new _SemVer(other, this.options);
          }
          if (this.major < other.major) {
            return -1;
          }
          if (this.major > other.major) {
            return 1;
          }
          if (this.minor < other.minor) {
            return -1;
          }
          if (this.minor > other.minor) {
            return 1;
          }
          if (this.patch < other.patch) {
            return -1;
          }
          if (this.patch > other.patch) {
            return 1;
          }
          return 0;
        }
        comparePre(other) {
          if (!(other instanceof _SemVer)) {
            other = new _SemVer(other, this.options);
          }
          if (this.prerelease.length && !other.prerelease.length) {
            return -1;
          } else if (!this.prerelease.length && other.prerelease.length) {
            return 1;
          } else if (!this.prerelease.length && !other.prerelease.length) {
            return 0;
          }
          let i = 0;
          do {
            const a = this.prerelease[i];
            const b = other.prerelease[i];
            debug("prerelease compare", i, a, b);
            if (a === void 0 && b === void 0) {
              return 0;
            } else if (b === void 0) {
              return 1;
            } else if (a === void 0) {
              return -1;
            } else if (a === b) {
              continue;
            } else {
              return compareIdentifiers(a, b);
            }
          } while (++i);
        }
        compareBuild(other) {
          if (!(other instanceof _SemVer)) {
            other = new _SemVer(other, this.options);
          }
          let i = 0;
          do {
            const a = this.build[i];
            const b = other.build[i];
            debug("build compare", i, a, b);
            if (a === void 0 && b === void 0) {
              return 0;
            } else if (b === void 0) {
              return 1;
            } else if (a === void 0) {
              return -1;
            } else if (a === b) {
              continue;
            } else {
              return compareIdentifiers(a, b);
            }
          } while (++i);
        }
        // preminor will bump the version up to the next minor release, and immediately
        // down to pre-release. premajor and prepatch work the same way.
        inc(release, identifier, identifierBase) {
          if (release.startsWith("pre")) {
            if (!identifier && identifierBase === false) {
              throw new Error("invalid increment argument: identifier is empty");
            }
            if (identifier) {
              const match = `-${identifier}`.match(this.options.loose ? re[t.PRERELEASELOOSE] : re[t.PRERELEASE]);
              if (!match || match[1] !== identifier) {
                throw new Error(`invalid identifier: ${identifier}`);
              }
            }
          }
          switch (release) {
            case "premajor":
              this.prerelease.length = 0;
              this.patch = 0;
              this.minor = 0;
              this.major++;
              this.inc("pre", identifier, identifierBase);
              break;
            case "preminor":
              this.prerelease.length = 0;
              this.patch = 0;
              this.minor++;
              this.inc("pre", identifier, identifierBase);
              break;
            case "prepatch":
              this.prerelease.length = 0;
              this.inc("patch", identifier, identifierBase);
              this.inc("pre", identifier, identifierBase);
              break;
            // If the input is a non-prerelease version, this acts the same as
            // prepatch.
            case "prerelease":
              if (this.prerelease.length === 0) {
                this.inc("patch", identifier, identifierBase);
              }
              this.inc("pre", identifier, identifierBase);
              break;
            case "release":
              if (this.prerelease.length === 0) {
                throw new Error(`version ${this.raw} is not a prerelease`);
              }
              this.prerelease.length = 0;
              break;
            case "major":
              if (this.minor !== 0 || this.patch !== 0 || this.prerelease.length === 0) {
                this.major++;
              }
              this.minor = 0;
              this.patch = 0;
              this.prerelease = [];
              break;
            case "minor":
              if (this.patch !== 0 || this.prerelease.length === 0) {
                this.minor++;
              }
              this.patch = 0;
              this.prerelease = [];
              break;
            case "patch":
              if (this.prerelease.length === 0) {
                this.patch++;
              }
              this.prerelease = [];
              break;
            // This probably shouldn't be used publicly.
            // 1.0.0 'pre' would become 1.0.0-0 which is the wrong direction.
            case "pre": {
              const base = Number(identifierBase) ? 1 : 0;
              if (this.prerelease.length === 0) {
                this.prerelease = [base];
              } else {
                let i = this.prerelease.length;
                while (--i >= 0) {
                  if (typeof this.prerelease[i] === "number") {
                    this.prerelease[i]++;
                    i = -2;
                  }
                }
                if (i === -1) {
                  if (identifier === this.prerelease.join(".") && identifierBase === false) {
                    throw new Error("invalid increment argument: identifier already exists");
                  }
                  this.prerelease.push(base);
                }
              }
              if (identifier) {
                let prerelease = [identifier, base];
                if (identifierBase === false) {
                  prerelease = [identifier];
                }
                if (isPrereleaseIdentifier(this.prerelease, identifier)) {
                  const prereleaseBase = this.prerelease[identifier.split(".").length];
                  if (isNaN(prereleaseBase)) {
                    this.prerelease = prerelease;
                  }
                } else {
                  this.prerelease = prerelease;
                }
              }
              break;
            }
            default:
              throw new Error(`invalid increment argument: ${release}`);
          }
          this.raw = this.format();
          if (this.build.length) {
            this.raw += `+${this.build.join(".")}`;
          }
          return this;
        }
      };
      module.exports = SemVer;
    }
  });

  // node_modules/semver/functions/major.js
  var require_major = __commonJS({
    "node_modules/semver/functions/major.js"(exports, module) {
      "use strict";
      var SemVer = require_semver();
      var major2 = (a, loose) => new SemVer(a, loose).major;
      module.exports = major2;
    }
  });

  // node_modules/semver/functions/parse.js
  var require_parse = __commonJS({
    "node_modules/semver/functions/parse.js"(exports, module) {
      "use strict";
      var SemVer = require_semver();
      var parse = (version, options, throwErrors = false) => {
        if (version instanceof SemVer) {
          return version;
        }
        try {
          return new SemVer(version, options);
        } catch (er) {
          if (!throwErrors) {
            return null;
          }
          throw er;
        }
      };
      module.exports = parse;
    }
  });

  // node_modules/semver/functions/valid.js
  var require_valid = __commonJS({
    "node_modules/semver/functions/valid.js"(exports, module) {
      "use strict";
      var parse = require_parse();
      var valid2 = (version, options) => {
        const v = parse(version, options);
        return v ? v.version : null;
      };
      module.exports = valid2;
    }
  });

  // node_modules/escape-html/index.js
  var require_escape_html = __commonJS({
    "node_modules/escape-html/index.js"(exports, module) {
      "use strict";
      var matchHtmlRegExp = /["'&<>]/;
      module.exports = escapeHtml;
      function escapeHtml(string) {
        var str = "" + string;
        var match = matchHtmlRegExp.exec(str);
        if (!match) {
          return str;
        }
        var escape;
        var html2 = "";
        var index = 0;
        var lastIndex = 0;
        for (index = match.index; index < str.length; index++) {
          switch (str.charCodeAt(index)) {
            case 34:
              escape = "&quot;";
              break;
            case 38:
              escape = "&amp;";
              break;
            case 39:
              escape = "&#39;";
              break;
            case 60:
              escape = "&lt;";
              break;
            case 62:
              escape = "&gt;";
              break;
            default:
              continue;
          }
          if (lastIndex !== index) {
            html2 += str.substring(lastIndex, index);
          }
          lastIndex = index + 1;
          html2 += escape;
        }
        return lastIndex !== index ? html2 + str.substring(lastIndex, index) : html2;
      }
    }
  });

  // node_modules/@nextcloud/event-bus/dist/index.mjs
  var import_major = __toESM(require_major(), 1);
  var import_valid = __toESM(require_valid(), 1);
  var ProxyBus = class {
    constructor(bus2) {
      __publicField(this, "bus");
      if (typeof bus2.getVersion !== "function" || !(0, import_valid.default)(bus2.getVersion())) {
        console.warn("Proxying an event bus with an unknown or invalid version");
      } else if ((0, import_major.default)(bus2.getVersion()) !== (0, import_major.default)(this.getVersion())) {
        console.warn(
          "Proxying an event bus of version " + bus2.getVersion() + " with " + this.getVersion()
        );
      }
      this.bus = bus2;
    }
    getVersion() {
      return "3.3.3";
    }
    subscribe(name, handler) {
      this.bus.subscribe(name, handler);
    }
    unsubscribe(name, handler) {
      this.bus.unsubscribe(name, handler);
    }
    emit(name, ...event) {
      this.bus.emit(name, ...event);
    }
  };
  var SimpleBus = class {
    constructor() {
      __publicField(this, "handlers", /* @__PURE__ */ new Map());
    }
    getVersion() {
      return "3.3.3";
    }
    subscribe(name, handler) {
      this.handlers.set(
        name,
        (this.handlers.get(name) || []).concat(
          handler
        )
      );
    }
    unsubscribe(name, handler) {
      this.handlers.set(
        name,
        (this.handlers.get(name) || []).filter((h) => h !== handler)
      );
    }
    emit(name, ...event) {
      const handlers = this.handlers.get(name) || [];
      handlers.forEach((h) => {
        try {
          ;
          h(event[0]);
        } catch (e2) {
          console.error("could not invoke event listener", e2);
        }
      });
    }
  };
  var bus = null;
  function getBus() {
    if (bus !== null) {
      return bus;
    }
    if (typeof window === "undefined") {
      return new Proxy({}, {
        get: () => {
          return () => console.error(
            "Window not available, EventBus can not be established!"
          );
        }
      });
    }
    if (window.OC?._eventBus && typeof window._nc_event_bus === "undefined") {
      console.warn(
        "found old event bus instance at OC._eventBus. Update your version!"
      );
      window._nc_event_bus = window.OC._eventBus;
    }
    if (typeof window?._nc_event_bus !== "undefined") {
      bus = new ProxyBus(window._nc_event_bus);
    } else {
      bus = window._nc_event_bus = new SimpleBus();
    }
    return bus;
  }
  function subscribe(name, handler) {
    getBus().subscribe(name, handler);
  }
  function unsubscribe(name, handler) {
    getBus().unsubscribe(name, handler);
  }
  function emit(name, ...event) {
    getBus().emit(name, ...event);
  }

  // node_modules/@nextcloud/router/dist/index.mjs
  var _generateUrlPath = (url, params, options) => {
    const allOptions = Object.assign({
      escape: true
    }, options || {});
    const _build = function(text2, vars) {
      vars = vars || {};
      return text2.replace(
        /{([^{}]*)}/g,
        function(a, b) {
          const r = vars[b];
          if (allOptions.escape) {
            return typeof r === "string" || typeof r === "number" ? encodeURIComponent(r.toString()) : encodeURIComponent(a);
          } else {
            return typeof r === "string" || typeof r === "number" ? r.toString() : a;
          }
        }
      );
    };
    if (url.charAt(0) !== "/") {
      url = "/" + url;
    }
    return _build(url, params || {});
  };
  var generateUrl = (url, params, options) => {
    const allOptions = Object.assign({
      noRewrite: false
    }, options || {});
    const baseOrRootURL = options?.baseURL ?? getRootUrl();
    if (window?.OC?.config?.modRewriteWorking === true && !allOptions.noRewrite) {
      return baseOrRootURL + _generateUrlPath(url, params, options);
    }
    return baseOrRootURL + "/index.php" + _generateUrlPath(url, params, options);
  };
  function getRootUrl() {
    let webroot = window._oc_webroot;
    if (typeof webroot === "undefined") {
      webroot = location.pathname;
      const pos = webroot.indexOf("/index.php/");
      if (pos !== -1) {
        webroot = webroot.slice(0, pos);
      } else {
        const index = webroot.indexOf("/", 1);
        webroot = webroot.slice(0, index > 0 ? index : void 0);
      }
    }
    return webroot;
  }

  // node_modules/@nextcloud/browser-storage/dist/ScopedStorage.js
  var _ScopedStorage = class _ScopedStorage {
    constructor(scope, wrapped, persistent) {
      __publicField(this, "scope");
      __publicField(this, "wrapped");
      this.scope = `${persistent ? _ScopedStorage.GLOBAL_SCOPE_PERSISTENT : _ScopedStorage.GLOBAL_SCOPE_VOLATILE}_${btoa(scope)}_`;
      this.wrapped = wrapped;
    }
    scopeKey(key) {
      return `${this.scope}${key}`;
    }
    setItem(key, value) {
      this.wrapped.setItem(this.scopeKey(key), value);
    }
    getItem(key) {
      return this.wrapped.getItem(this.scopeKey(key));
    }
    removeItem(key) {
      this.wrapped.removeItem(this.scopeKey(key));
    }
    clear() {
      Object.keys(this.wrapped).filter((key) => key.startsWith(this.scope)).map(this.wrapped.removeItem.bind(this.wrapped));
    }
  };
  __publicField(_ScopedStorage, "GLOBAL_SCOPE_VOLATILE", "nextcloud_vol");
  __publicField(_ScopedStorage, "GLOBAL_SCOPE_PERSISTENT", "nextcloud_per");
  var ScopedStorage = _ScopedStorage;

  // node_modules/@nextcloud/browser-storage/dist/StorageBuilder.js
  var StorageBuilder = class {
    constructor(appId) {
      __publicField(this, "appId");
      __publicField(this, "persisted", false);
      __publicField(this, "clearedOnLogout", false);
      this.appId = appId;
    }
    persist(persist = true) {
      this.persisted = persist;
      return this;
    }
    clearOnLogout(clear = true) {
      this.clearedOnLogout = clear;
      return this;
    }
    build() {
      return new ScopedStorage(this.appId, this.persisted ? window.localStorage : window.sessionStorage, !this.clearedOnLogout);
    }
  };

  // node_modules/@nextcloud/browser-storage/dist/index.js
  function getBuilder(appId) {
    return new StorageBuilder(appId);
  }

  // node_modules/@nextcloud/auth/dist/index.mjs
  _subscribeToTokenUpdates();
  function getRequestToken() {
    if (globalThis._nc_auth_requestToken) {
      return globalThis._nc_auth_requestToken;
    }
    if (globalThis.document) {
      return document.head.dataset.requesttoken ?? null;
    }
    return null;
  }
  function setRequestToken(token) {
    if (!token || typeof token !== "string") {
      throw new Error("Invalid CSRF token given", { cause: { token } });
    }
    if (globalThis._nc_auth_requestToken === token) {
      return;
    }
    globalThis._nc_auth_requestToken = token;
    if (globalThis.document) {
      document.head.dataset.requesttoken = token;
    }
    emit("csrf-token-update", { token, _internal: true });
  }
  async function fetchRequestToken() {
    const url = generateUrl("/csrftoken");
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error("Could not fetch CSRF token from API", { cause: response });
    }
    try {
      const { token } = await response.json();
      setRequestToken(token);
      return token;
    } catch (error) {
      throw new Error("Could not parse CSRF token from API response", { cause: error });
    }
  }
  function onRequestTokenUpdate(observer) {
    const wrapper = async ({ token }) => {
      try {
        observer(token);
      } catch (error) {
        console.error("Error updating CSRF token observer", error);
      }
    };
    subscribe("csrf-token-update", wrapper);
    return () => unsubscribe("csrf-token-update", wrapper);
  }
  function _subscribeToTokenUpdates() {
    subscribe("csrf-token-update", ({ token, _internal }) => {
      if (!_internal) {
        setRequestToken(token);
      }
    });
  }
  var browserStorage = getBuilder("public").persist().build();
  var currentUser;
  function getAttribute(el, attribute) {
    if (el) {
      return el.getAttribute(attribute);
    }
    return null;
  }
  function getCurrentUser() {
    if (currentUser !== void 0) {
      return currentUser;
    }
    const head = document?.getElementsByTagName("head")[0];
    if (!head) {
      return null;
    }
    const uid = getAttribute(head, "data-user");
    if (uid === null) {
      currentUser = null;
      return currentUser;
    }
    currentUser = {
      uid,
      displayName: getAttribute(head, "data-user-displayname"),
      isAdmin: !!window._oc_isadmin
    };
    return currentUser;
  }

  // node_modules/@nextcloud/logger/dist/index.mjs
  var LogLevel = /* @__PURE__ */ ((LogLevel2) => {
    LogLevel2[LogLevel2["Debug"] = 0] = "Debug";
    LogLevel2[LogLevel2["Info"] = 1] = "Info";
    LogLevel2[LogLevel2["Warn"] = 2] = "Warn";
    LogLevel2[LogLevel2["Error"] = 3] = "Error";
    LogLevel2[LogLevel2["Fatal"] = 4] = "Fatal";
    return LogLevel2;
  })(LogLevel || {});
  var ConsoleLogger = class {
    constructor(context) {
      __publicField(this, "context");
      this.context = context || {};
    }
    formatMessage(message, level, context) {
      let msg = "[" + LogLevel[level].toUpperCase() + "] ";
      if (context && context.app) {
        msg += context.app + ": ";
      }
      if (typeof message === "string") return msg + message;
      msg += `Unexpected ${message.name}`;
      if (message.message) msg += ` "${message.message}"`;
      if (level === LogLevel.Debug && message.stack) msg += `

Stack trace:
${message.stack}`;
      return msg;
    }
    log(level, message, context) {
      if (typeof this.context?.level === "number" && level < this.context?.level) {
        return;
      }
      if (typeof message === "object" && context?.error === void 0) {
        context.error = message;
      }
      switch (level) {
        case LogLevel.Debug:
          console.debug(this.formatMessage(message, LogLevel.Debug, context), context);
          break;
        case LogLevel.Info:
          console.info(this.formatMessage(message, LogLevel.Info, context), context);
          break;
        case LogLevel.Warn:
          console.warn(this.formatMessage(message, LogLevel.Warn, context), context);
          break;
        case LogLevel.Error:
          console.error(this.formatMessage(message, LogLevel.Error, context), context);
          break;
        case LogLevel.Fatal:
        default:
          console.error(this.formatMessage(message, LogLevel.Fatal, context), context);
          break;
      }
    }
    debug(message, context) {
      this.log(LogLevel.Debug, message, Object.assign({}, this.context, context));
    }
    info(message, context) {
      this.log(LogLevel.Info, message, Object.assign({}, this.context, context));
    }
    warn(message, context) {
      this.log(LogLevel.Warn, message, Object.assign({}, this.context, context));
    }
    error(message, context) {
      this.log(LogLevel.Error, message, Object.assign({}, this.context, context));
    }
    fatal(message, context) {
      this.log(LogLevel.Fatal, message, Object.assign({}, this.context, context));
    }
  };
  function buildConsoleLogger(context) {
    return new ConsoleLogger(context);
  }
  var LoggerBuilder = class {
    constructor(factory2) {
      __publicField(this, "context");
      __publicField(this, "factory");
      this.context = {};
      this.factory = factory2;
    }
    /**
     * Set the app name within the logging context
     *
     * @param appId App name
     */
    setApp(appId) {
      this.context.app = appId;
      return this;
    }
    /**
     * Set the logging level within the logging context
     *
     * @param level Logging level
     */
    setLogLevel(level) {
      this.context.level = level;
      return this;
    }
    /* eslint-disable jsdoc/no-undefined-types */
    /**
     * Set the user id within the logging context
     * @param uid User ID
     * @see {@link detectUser}
     */
    /* eslint-enable jsdoc/no-undefined-types */
    setUid(uid) {
      this.context.uid = uid;
      return this;
    }
    /**
     * Detect the currently logged in user and set the user id within the logging context
     */
    detectUser() {
      const user = getCurrentUser();
      if (user !== null) {
        this.context.uid = user.uid;
      }
      return this;
    }
    /**
     * Detect and use logging level configured in nextcloud config
     */
    detectLogLevel() {
      const self2 = this;
      const onLoaded = () => {
        if (document.readyState === "complete" || document.readyState === "interactive") {
          self2.context.level = window._oc_config?.loglevel ?? LogLevel.Warn;
          if (window._oc_debug) {
            self2.context.level = LogLevel.Debug;
          }
          document.removeEventListener("readystatechange", onLoaded);
        } else {
          document.addEventListener("readystatechange", onLoaded);
        }
      };
      onLoaded();
      return this;
    }
    /** Build a logger using the logging context and factory */
    build() {
      if (this.context.level === void 0) {
        this.detectLogLevel();
      }
      return this.factory(this.context);
    }
  };
  function getLoggerBuilder() {
    return new LoggerBuilder(buildConsoleLogger);
  }

  // node_modules/@nextcloud/files/dist/chunks/folder-29HuacU_.mjs
  window._nc_files_scope ?? (window._nc_files_scope = {});
  var _a;
  (_a = window._nc_files_scope).v4_0 ?? (_a.v4_0 = {});
  var scopedGlobals = window._nc_files_scope.v4_0;
  var logger = getLoggerBuilder().setApp("@nextcloud/files").detectUser().build();
  var FileType = Object.freeze({
    Folder: "folder",
    File: "file"
  });
  var Permission = Object.freeze({
    /**
     * No permissions granted
     */
    NONE: 0,
    /**
     * Can read the file content
     */
    READ: 1,
    /**
     * Can modify the file itself (move, rename, etc)
     */
    UPDATE: 2,
    /**
     * Can create new files/folders inside a folder
     */
    CREATE: 4,
    /**
     * Can change the file content
     */
    WRITE: 4,
    /**
     * Can delete the node
     */
    DELETE: 8,
    /**
     * Can share the node
     */
    SHARE: 16,
    /**
     * All permissions are granted
     */
    ALL: 31
  });
  var NodeStatus = Object.freeze({
    /** This is a new node and it doesn't exists on the filesystem yet */
    NEW: "new",
    /** This node has failed and is unavailable  */
    FAILED: "failed",
    /** This node is currently loading or have an operation in progress */
    LOADING: "loading",
    /** This node is locked and cannot be modified */
    LOCKED: "locked"
  });

  // node_modules/typescript-event-target/dist/index.mjs
  var e = class extends EventTarget {
    dispatchTypedEvent(s, t) {
      return super.dispatchEvent(t);
    }
  };

  // node_modules/dompurify/dist/purify.es.mjs
  function _arrayLikeToArray(r, a) {
    (null == a || a > r.length) && (a = r.length);
    for (var e2 = 0, n = Array(a); e2 < a; e2++) n[e2] = r[e2];
    return n;
  }
  function _arrayWithHoles(r) {
    if (Array.isArray(r)) return r;
  }
  function _iterableToArrayLimit(r, l) {
    var t = null == r ? null : "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
    if (null != t) {
      var e2, n, i, u, a = [], f = true, o = false;
      try {
        if (i = (t = t.call(r)).next, 0 === l) ;
        else for (; !(f = (e2 = i.call(t)).done) && (a.push(e2.value), a.length !== l); f = true) ;
      } catch (r2) {
        o = true, n = r2;
      } finally {
        try {
          if (!f && null != t.return && (u = t.return(), Object(u) !== u)) return;
        } finally {
          if (o) throw n;
        }
      }
      return a;
    }
  }
  function _nonIterableRest() {
    throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  function _slicedToArray(r, e2) {
    return _arrayWithHoles(r) || _iterableToArrayLimit(r, e2) || _unsupportedIterableToArray(r, e2) || _nonIterableRest();
  }
  function _unsupportedIterableToArray(r, a) {
    if (r) {
      if ("string" == typeof r) return _arrayLikeToArray(r, a);
      var t = {}.toString.call(r).slice(8, -1);
      return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a) : void 0;
    }
  }
  var entries = Object.entries;
  var setPrototypeOf = Object.setPrototypeOf;
  var isFrozen = Object.isFrozen;
  var getPrototypeOf = Object.getPrototypeOf;
  var getOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
  var freeze = Object.freeze;
  var seal = Object.seal;
  var create = Object.create;
  var _ref = typeof Reflect !== "undefined" && Reflect;
  var apply = _ref.apply;
  var construct = _ref.construct;
  if (!freeze) {
    freeze = function freeze2(x) {
      return x;
    };
  }
  if (!seal) {
    seal = function seal2(x) {
      return x;
    };
  }
  if (!apply) {
    apply = function apply2(func, thisArg) {
      for (var _len = arguments.length, args = new Array(_len > 2 ? _len - 2 : 0), _key = 2; _key < _len; _key++) {
        args[_key - 2] = arguments[_key];
      }
      return func.apply(thisArg, args);
    };
  }
  if (!construct) {
    construct = function construct2(Func) {
      for (var _len2 = arguments.length, args = new Array(_len2 > 1 ? _len2 - 1 : 0), _key2 = 1; _key2 < _len2; _key2++) {
        args[_key2 - 1] = arguments[_key2];
      }
      return new Func(...args);
    };
  }
  var arrayForEach = unapply(Array.prototype.forEach);
  var arrayLastIndexOf = unapply(Array.prototype.lastIndexOf);
  var arrayPop = unapply(Array.prototype.pop);
  var arrayPush = unapply(Array.prototype.push);
  var arraySplice = unapply(Array.prototype.splice);
  var arrayIsArray = Array.isArray;
  var stringToLowerCase = unapply(String.prototype.toLowerCase);
  var stringToString = unapply(String.prototype.toString);
  var stringMatch = unapply(String.prototype.match);
  var stringReplace = unapply(String.prototype.replace);
  var stringIndexOf = unapply(String.prototype.indexOf);
  var stringTrim = unapply(String.prototype.trim);
  var numberToString = unapply(Number.prototype.toString);
  var booleanToString = unapply(Boolean.prototype.toString);
  var bigintToString = typeof BigInt === "undefined" ? null : unapply(BigInt.prototype.toString);
  var symbolToString = typeof Symbol === "undefined" ? null : unapply(Symbol.prototype.toString);
  var objectHasOwnProperty = unapply(Object.prototype.hasOwnProperty);
  var objectToString = unapply(Object.prototype.toString);
  var regExpTest = unapply(RegExp.prototype.test);
  var typeErrorCreate = unconstruct(TypeError);
  function unapply(func) {
    return function(thisArg) {
      if (thisArg instanceof RegExp) {
        thisArg.lastIndex = 0;
      }
      for (var _len3 = arguments.length, args = new Array(_len3 > 1 ? _len3 - 1 : 0), _key3 = 1; _key3 < _len3; _key3++) {
        args[_key3 - 1] = arguments[_key3];
      }
      return apply(func, thisArg, args);
    };
  }
  function unconstruct(Func) {
    return function() {
      for (var _len4 = arguments.length, args = new Array(_len4), _key4 = 0; _key4 < _len4; _key4++) {
        args[_key4] = arguments[_key4];
      }
      return construct(Func, args);
    };
  }
  function addToSet(set, array) {
    let transformCaseFunc = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : stringToLowerCase;
    if (setPrototypeOf) {
      setPrototypeOf(set, null);
    }
    if (!arrayIsArray(array)) {
      return set;
    }
    let l = array.length;
    while (l--) {
      let element2 = array[l];
      if (typeof element2 === "string") {
        const lcElement = transformCaseFunc(element2);
        if (lcElement !== element2) {
          if (!isFrozen(array)) {
            array[l] = lcElement;
          }
          element2 = lcElement;
        }
      }
      set[element2] = true;
    }
    return set;
  }
  function cleanArray(array) {
    for (let index = 0; index < array.length; index++) {
      const isPropertyExist = objectHasOwnProperty(array, index);
      if (!isPropertyExist) {
        array[index] = null;
      }
    }
    return array;
  }
  function clone(object) {
    const newObject = create(null);
    for (const _ref2 of entries(object)) {
      var _ref3 = _slicedToArray(_ref2, 2);
      const property = _ref3[0];
      const value = _ref3[1];
      const isPropertyExist = objectHasOwnProperty(object, property);
      if (isPropertyExist) {
        if (arrayIsArray(value)) {
          newObject[property] = cleanArray(value);
        } else if (value && typeof value === "object" && value.constructor === Object) {
          newObject[property] = clone(value);
        } else {
          newObject[property] = value;
        }
      }
    }
    return newObject;
  }
  function stringifyValue(value) {
    switch (typeof value) {
      case "string": {
        return value;
      }
      case "number": {
        return numberToString(value);
      }
      case "boolean": {
        return booleanToString(value);
      }
      case "bigint": {
        return bigintToString ? bigintToString(value) : "0";
      }
      case "symbol": {
        return symbolToString ? symbolToString(value) : "Symbol()";
      }
      case "undefined": {
        return objectToString(value);
      }
      case "function":
      case "object": {
        if (value === null) {
          return objectToString(value);
        }
        const valueAsRecord = value;
        const valueToString = lookupGetter(valueAsRecord, "toString");
        if (typeof valueToString === "function") {
          const stringified = valueToString(valueAsRecord);
          return typeof stringified === "string" ? stringified : objectToString(stringified);
        }
        return objectToString(value);
      }
      default: {
        return objectToString(value);
      }
    }
  }
  function lookupGetter(object, prop) {
    while (object !== null) {
      const desc = getOwnPropertyDescriptor(object, prop);
      if (desc) {
        if (desc.get) {
          return unapply(desc.get);
        }
        if (typeof desc.value === "function") {
          return unapply(desc.value);
        }
      }
      object = getPrototypeOf(object);
    }
    function fallbackValue() {
      return null;
    }
    return fallbackValue;
  }
  function isRegex(value) {
    try {
      regExpTest(value, "");
      return true;
    } catch (_unused) {
      return false;
    }
  }
  var html$1 = freeze(["a", "abbr", "acronym", "address", "area", "article", "aside", "audio", "b", "bdi", "bdo", "big", "blink", "blockquote", "body", "br", "button", "canvas", "caption", "center", "cite", "code", "col", "colgroup", "content", "data", "datalist", "dd", "decorator", "del", "details", "dfn", "dialog", "dir", "div", "dl", "dt", "element", "em", "fieldset", "figcaption", "figure", "font", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html", "i", "img", "input", "ins", "kbd", "label", "legend", "li", "main", "map", "mark", "marquee", "menu", "menuitem", "meter", "nav", "nobr", "ol", "optgroup", "option", "output", "p", "picture", "pre", "progress", "q", "rp", "rt", "ruby", "s", "samp", "search", "section", "select", "shadow", "slot", "small", "source", "spacer", "span", "strike", "strong", "style", "sub", "summary", "sup", "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "time", "tr", "track", "tt", "u", "ul", "var", "video", "wbr"]);
  var svg$1 = freeze(["svg", "a", "altglyph", "altglyphdef", "altglyphitem", "animatecolor", "animatemotion", "animatetransform", "circle", "clippath", "defs", "desc", "ellipse", "enterkeyhint", "exportparts", "filter", "font", "g", "glyph", "glyphref", "hkern", "image", "inputmode", "line", "lineargradient", "marker", "mask", "metadata", "mpath", "part", "path", "pattern", "polygon", "polyline", "radialgradient", "rect", "stop", "style", "switch", "symbol", "text", "textpath", "title", "tref", "tspan", "view", "vkern"]);
  var svgFilters = freeze(["feBlend", "feColorMatrix", "feComponentTransfer", "feComposite", "feConvolveMatrix", "feDiffuseLighting", "feDisplacementMap", "feDistantLight", "feDropShadow", "feFlood", "feFuncA", "feFuncB", "feFuncG", "feFuncR", "feGaussianBlur", "feImage", "feMerge", "feMergeNode", "feMorphology", "feOffset", "fePointLight", "feSpecularLighting", "feSpotLight", "feTile", "feTurbulence"]);
  var svgDisallowed = freeze(["animate", "color-profile", "cursor", "discard", "font-face", "font-face-format", "font-face-name", "font-face-src", "font-face-uri", "foreignobject", "hatch", "hatchpath", "mesh", "meshgradient", "meshpatch", "meshrow", "missing-glyph", "script", "set", "solidcolor", "unknown", "use"]);
  var mathMl$1 = freeze(["math", "menclose", "merror", "mfenced", "mfrac", "mglyph", "mi", "mlabeledtr", "mmultiscripts", "mn", "mo", "mover", "mpadded", "mphantom", "mroot", "mrow", "ms", "mspace", "msqrt", "mstyle", "msub", "msup", "msubsup", "mtable", "mtd", "mtext", "mtr", "munder", "munderover", "mprescripts"]);
  var mathMlDisallowed = freeze(["maction", "maligngroup", "malignmark", "mlongdiv", "mscarries", "mscarry", "msgroup", "mstack", "msline", "msrow", "semantics", "annotation", "annotation-xml", "mprescripts", "none"]);
  var text = freeze(["#text"]);
  var html = freeze(["accept", "action", "align", "alt", "autocapitalize", "autocomplete", "autopictureinpicture", "autoplay", "background", "bgcolor", "border", "capture", "cellpadding", "cellspacing", "checked", "cite", "class", "clear", "color", "cols", "colspan", "command", "commandfor", "controls", "controlslist", "coords", "crossorigin", "datetime", "decoding", "default", "dir", "disabled", "disablepictureinpicture", "disableremoteplayback", "download", "draggable", "enctype", "enterkeyhint", "exportparts", "face", "for", "headers", "height", "hidden", "high", "href", "hreflang", "id", "inert", "inputmode", "integrity", "ismap", "kind", "label", "lang", "list", "loading", "loop", "low", "max", "maxlength", "media", "method", "min", "minlength", "multiple", "muted", "name", "nonce", "noshade", "novalidate", "nowrap", "open", "optimum", "part", "pattern", "placeholder", "playsinline", "popover", "popovertarget", "popovertargetaction", "poster", "preload", "pubdate", "radiogroup", "readonly", "rel", "required", "rev", "reversed", "role", "rows", "rowspan", "spellcheck", "scope", "selected", "shape", "size", "sizes", "slot", "span", "srclang", "start", "src", "srcset", "step", "style", "summary", "tabindex", "title", "translate", "type", "usemap", "valign", "value", "width", "wrap", "xmlns"]);
  var svg = freeze(["accent-height", "accumulate", "additive", "alignment-baseline", "amplitude", "ascent", "attributename", "attributetype", "azimuth", "basefrequency", "baseline-shift", "begin", "bias", "by", "class", "clip", "clippathunits", "clip-path", "clip-rule", "color", "color-interpolation", "color-interpolation-filters", "color-profile", "color-rendering", "cx", "cy", "d", "dx", "dy", "diffuseconstant", "direction", "display", "divisor", "dominant-baseline", "dur", "edgemode", "elevation", "end", "exponent", "fill", "fill-opacity", "fill-rule", "filter", "filterunits", "flood-color", "flood-opacity", "font-family", "font-size", "font-size-adjust", "font-stretch", "font-style", "font-variant", "font-weight", "fx", "fy", "g1", "g2", "glyph-name", "glyphref", "gradientunits", "gradienttransform", "height", "href", "id", "image-rendering", "in", "in2", "intercept", "k", "k1", "k2", "k3", "k4", "kerning", "keypoints", "keysplines", "keytimes", "lang", "lengthadjust", "letter-spacing", "kernelmatrix", "kernelunitlength", "lighting-color", "local", "marker-end", "marker-mid", "marker-start", "markerheight", "markerunits", "markerwidth", "maskcontentunits", "maskunits", "max", "mask", "mask-type", "media", "method", "mode", "min", "name", "numoctaves", "offset", "operator", "opacity", "order", "orient", "orientation", "origin", "overflow", "paint-order", "path", "pathlength", "patterncontentunits", "patterntransform", "patternunits", "pointer-events", "points", "preservealpha", "preserveaspectratio", "primitiveunits", "r", "rx", "ry", "radius", "refx", "refy", "repeatcount", "repeatdur", "restart", "result", "rotate", "scale", "seed", "shape-rendering", "slope", "specularconstant", "specularexponent", "spreadmethod", "startoffset", "stddeviation", "stitchtiles", "stop-color", "stop-opacity", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-opacity", "stroke", "stroke-width", "style", "surfacescale", "systemlanguage", "tabindex", "tablevalues", "targetx", "targety", "transform", "transform-origin", "text-anchor", "text-decoration", "text-orientation", "text-rendering", "textlength", "type", "u1", "u2", "unicode", "values", "vector-effect", "viewbox", "visibility", "version", "vert-adv-y", "vert-origin-x", "vert-origin-y", "width", "word-spacing", "wrap", "writing-mode", "xchannelselector", "ychannelselector", "x", "x1", "x2", "xmlns", "y", "y1", "y2", "z", "zoomandpan"]);
  var mathMl = freeze(["accent", "accentunder", "align", "bevelled", "close", "columnalign", "columnlines", "columnspacing", "columnspan", "denomalign", "depth", "dir", "display", "displaystyle", "encoding", "fence", "frame", "height", "href", "id", "largeop", "length", "linethickness", "lquote", "lspace", "mathbackground", "mathcolor", "mathsize", "mathvariant", "maxsize", "minsize", "movablelimits", "notation", "numalign", "open", "rowalign", "rowlines", "rowspacing", "rowspan", "rspace", "rquote", "scriptlevel", "scriptminsize", "scriptsizemultiplier", "selection", "separator", "separators", "stretchy", "subscriptshift", "supscriptshift", "symmetric", "voffset", "width", "xmlns"]);
  var xml = freeze(["xlink:href", "xml:id", "xlink:title", "xml:space", "xmlns:xlink"]);
  var MUSTACHE_EXPR = seal(/{{[\w\W]*|^[\w\W]*}}/g);
  var ERB_EXPR = seal(/<%[\w\W]*|^[\w\W]*%>/g);
  var TMPLIT_EXPR = seal(/\${[\w\W]*/g);
  var DATA_ATTR = seal(/^data-[\-\w.\u00B7-\uFFFF]+$/);
  var ARIA_ATTR = seal(/^aria-[\-\w]+$/);
  var IS_ALLOWED_URI = seal(
    /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i
    // eslint-disable-line no-useless-escape
  );
  var IS_SCRIPT_OR_DATA = seal(/^(?:\w+script|data):/i);
  var ATTR_WHITESPACE = seal(
    /[\u0000-\u0020\u00A0\u1680\u180E\u2000-\u2029\u205F\u3000]/g
    // eslint-disable-line no-control-regex
  );
  var DOCTYPE_NAME = seal(/^html$/i);
  var CUSTOM_ELEMENT = seal(/^[a-z][.\w]*(-[.\w]+)+$/i);
  var ELEMENT_MARKUP_PROBE = seal(/<[/\w!]/g);
  var COMMENT_MARKUP_PROBE = seal(/<[/\w]/g);
  var FALLBACK_TAG_CLOSE = seal(/<\/no(script|embed|frames)/i);
  var SELF_CLOSING_TAG = seal(/\/>/i);
  var NODE_TYPE = {
    element: 1,
    attribute: 2,
    text: 3,
    cdataSection: 4,
    entityReference: 5,
    // Deprecated
    entityNode: 6,
    // Deprecated
    processingInstruction: 7,
    comment: 8,
    document: 9,
    documentType: 10,
    documentFragment: 11,
    notation: 12
    // Deprecated
  };
  var LITERAL_TEXT_ELEMENT_NAMES = ["style", "script", "xmp", "iframe", "noembed", "noframes", "plaintext", "noscript"];
  var LITERAL_TEXT_ELEMENTS = freeze(addToSet({}, LITERAL_TEXT_ELEMENT_NAMES));
  var LITERAL_TEXT_CLOSE = (function() {
    const map = {};
    arrayForEach(LITERAL_TEXT_ELEMENT_NAMES, (name) => {
      map[name] = seal(new RegExp("</" + name + "(?=[\\t\\n\\f\\r />])", "i"));
    });
    return freeze(map);
  })();
  var getGlobal = function getGlobal2() {
    return typeof window === "undefined" ? null : window;
  };
  var _createTrustedTypesPolicy = function _createTrustedTypesPolicy2(trustedTypes, purifyHostElement) {
    if (typeof trustedTypes !== "object" || typeof trustedTypes.createPolicy !== "function") {
      return null;
    }
    let suffix = null;
    const ATTR_NAME = "data-tt-policy-suffix";
    if (purifyHostElement && purifyHostElement.hasAttribute(ATTR_NAME)) {
      suffix = purifyHostElement.getAttribute(ATTR_NAME);
    }
    const policyName = "dompurify" + (suffix ? "#" + suffix : "");
    try {
      return trustedTypes.createPolicy(policyName, {
        createHTML(html2) {
          return html2;
        },
        createScriptURL(scriptUrl) {
          return scriptUrl;
        }
      });
    } catch (_) {
      console.warn("TrustedTypes policy " + policyName + " could not be created.");
      return null;
    }
  };
  var _createHooksMap = function _createHooksMap2() {
    return {
      afterSanitizeAttributes: [],
      afterSanitizeElements: [],
      afterSanitizeShadowDOM: [],
      beforeSanitizeAttributes: [],
      beforeSanitizeElements: [],
      beforeSanitizeShadowDOM: [],
      uponSanitizeAttribute: [],
      uponSanitizeElement: [],
      uponSanitizeShadowNode: []
    };
  };
  var _resolveSetOption = function _resolveSetOption2(cfg, key, fallback, options) {
    return objectHasOwnProperty(cfg, key) && arrayIsArray(cfg[key]) ? addToSet(options.base ? clone(options.base) : {}, cfg[key], options.transform) : fallback;
  };
  var _resolveObjectOption = function _resolveObjectOption2(cfg, key, makeFallback) {
    const value = objectHasOwnProperty(cfg, key) ? cfg[key] : void 0;
    return value && typeof value === "object" ? clone(value) : makeFallback();
  };
  function createDOMPurify() {
    let window2 = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : getGlobal();
    const DOMPurify = (root) => createDOMPurify(root);
    DOMPurify.version = "3.4.15";
    DOMPurify.removed = [];
    if (!window2 || !window2.document || window2.document.nodeType !== NODE_TYPE.document || !window2.Element) {
      DOMPurify.isSupported = false;
      return DOMPurify;
    }
    let document2 = window2.document;
    const originalDocument = document2;
    const currentScript = originalDocument.currentScript;
    window2.DocumentFragment;
    const HTMLTemplateElement = window2.HTMLTemplateElement, Node2 = window2.Node, Element = window2.Element, NodeFilter = window2.NodeFilter, _window$NamedNodeMap = window2.NamedNodeMap;
    _window$NamedNodeMap === void 0 ? window2.NamedNodeMap || window2.MozNamedAttrMap : _window$NamedNodeMap;
    window2.HTMLFormElement;
    const DOMParser = window2.DOMParser, trustedTypes = window2.trustedTypes;
    const ElementPrototype = Element.prototype;
    const cloneNode = lookupGetter(ElementPrototype, "cloneNode");
    const remove = lookupGetter(ElementPrototype, "remove");
    const removeAttributeNode = lookupGetter(ElementPrototype, "removeAttributeNode");
    const getNextSibling = lookupGetter(ElementPrototype, "nextSibling");
    const getChildNodes = lookupGetter(ElementPrototype, "childNodes");
    const getParentNode = lookupGetter(ElementPrototype, "parentNode");
    const getShadowRoot = lookupGetter(ElementPrototype, "shadowRoot");
    const getAttributes = lookupGetter(ElementPrototype, "attributes");
    const getNodeType = Node2 && Node2.prototype ? lookupGetter(Node2.prototype, "nodeType") : null;
    const getNodeName = Node2 && Node2.prototype ? lookupGetter(Node2.prototype, "nodeName") : null;
    const getOwnerDocument = Node2 && Node2.prototype ? lookupGetter(Node2.prototype, "ownerDocument") : null;
    const _readNodeType = function _readNodeType2(node) {
      return getNodeType ? getNodeType(node) : node.nodeType;
    };
    const _readNodeName = function _readNodeName2(node) {
      return getNodeName ? getNodeName(node) : node.nodeName;
    };
    if (typeof HTMLTemplateElement === "function") {
      const template = document2.createElement("template");
      if (template.content && template.content.ownerDocument) {
        document2 = template.content.ownerDocument;
      }
    }
    let trustedTypesPolicy;
    let emptyHTML = "";
    let defaultTrustedTypesPolicy;
    let defaultTrustedTypesPolicyResolved = false;
    let IN_TRUSTED_TYPES_POLICY = 0;
    const _assertNotInTrustedTypesPolicy = function _assertNotInTrustedTypesPolicy2() {
      if (IN_TRUSTED_TYPES_POLICY > 0) {
        throw typeErrorCreate('A configured TRUSTED_TYPES_POLICY callback (createHTML or createScriptURL) must not call DOMPurify.sanitize, as that causes infinite recursion. Do not pass a policy whose callbacks wrap DOMPurify as TRUSTED_TYPES_POLICY; see the "DOMPurify and Trusted Types" section of the README.');
      }
    };
    const _createTrustedHTML = function _createTrustedHTML2(html2) {
      _assertNotInTrustedTypesPolicy();
      IN_TRUSTED_TYPES_POLICY++;
      try {
        return trustedTypesPolicy.createHTML(html2);
      } finally {
        IN_TRUSTED_TYPES_POLICY--;
      }
    };
    const _createTrustedScriptURL = function _createTrustedScriptURL2(scriptUrl) {
      _assertNotInTrustedTypesPolicy();
      IN_TRUSTED_TYPES_POLICY++;
      try {
        return trustedTypesPolicy.createScriptURL(scriptUrl);
      } finally {
        IN_TRUSTED_TYPES_POLICY--;
      }
    };
    const _getDefaultTrustedTypesPolicy = function _getDefaultTrustedTypesPolicy2() {
      if (!defaultTrustedTypesPolicyResolved) {
        defaultTrustedTypesPolicy = _createTrustedTypesPolicy(trustedTypes, currentScript);
        defaultTrustedTypesPolicyResolved = true;
      }
      return defaultTrustedTypesPolicy;
    };
    const _document = document2, implementation = _document.implementation, createNodeIterator = _document.createNodeIterator, createDocumentFragment = _document.createDocumentFragment, getElementsByTagName = _document.getElementsByTagName;
    const importNode = originalDocument.importNode;
    let hooks = _createHooksMap();
    DOMPurify.isSupported = typeof entries === "function" && typeof getParentNode === "function" && implementation && implementation.createHTMLDocument !== void 0;
    const MUSTACHE_EXPR$1 = MUSTACHE_EXPR, ERB_EXPR$1 = ERB_EXPR, TMPLIT_EXPR$1 = TMPLIT_EXPR, DATA_ATTR$1 = DATA_ATTR, ARIA_ATTR$1 = ARIA_ATTR, IS_SCRIPT_OR_DATA$1 = IS_SCRIPT_OR_DATA, ATTR_WHITESPACE$1 = ATTR_WHITESPACE, CUSTOM_ELEMENT$1 = CUSTOM_ELEMENT;
    let IS_ALLOWED_URI$1 = IS_ALLOWED_URI;
    let ALLOWED_TAGS = null;
    const DEFAULT_ALLOWED_TAGS = addToSet({}, [...html$1, ...svg$1, ...svgFilters, ...mathMl$1, ...text]);
    let ALLOWED_ATTR = null;
    const DEFAULT_ALLOWED_ATTR = addToSet({}, [...html, ...svg, ...mathMl, ...xml]);
    let CUSTOM_ELEMENT_HANDLING = Object.seal(create(null, {
      tagNameCheck: {
        writable: true,
        configurable: false,
        enumerable: true,
        value: null
      },
      attributeNameCheck: {
        writable: true,
        configurable: false,
        enumerable: true,
        value: null
      },
      allowCustomizedBuiltInElements: {
        writable: true,
        configurable: false,
        enumerable: true,
        value: false
      }
    }));
    let FORBID_TAGS = null;
    let FORBID_ATTR = null;
    const EXTRA_ELEMENT_HANDLING = Object.seal(create(null, {
      tagCheck: {
        writable: true,
        configurable: false,
        enumerable: true,
        value: null
      },
      attributeCheck: {
        writable: true,
        configurable: false,
        enumerable: true,
        value: null
      }
    }));
    let ALLOW_ARIA_ATTR = true;
    let ALLOW_DATA_ATTR = true;
    let ALLOW_UNKNOWN_PROTOCOLS = false;
    let ALLOW_SELF_CLOSE_IN_ATTR = true;
    let SAFE_FOR_TEMPLATES = false;
    let SAFE_FOR_XML = true;
    let WHOLE_DOCUMENT = false;
    let SET_CONFIG = false;
    let SET_CONFIG_ALLOWED_TAGS = null;
    let SET_CONFIG_ALLOWED_ATTR = null;
    let FORCE_BODY = false;
    let RETURN_DOM = false;
    let RETURN_DOM_FRAGMENT = false;
    let RETURN_TRUSTED_TYPE = false;
    let SANITIZE_DOM = true;
    let SANITIZE_NAMED_PROPS = false;
    const SANITIZE_NAMED_PROPS_PREFIX = "user-content-";
    let KEEP_CONTENT = true;
    let IN_PLACE = false;
    let USE_PROFILES = {};
    let FORBID_CONTENTS = null;
    const DEFAULT_FORBID_CONTENTS = addToSet({}, [
      "annotation-xml",
      "audio",
      "colgroup",
      "desc",
      "foreignobject",
      "head",
      "iframe",
      "math",
      "mi",
      "mn",
      "mo",
      "ms",
      "mtext",
      "noembed",
      "noframes",
      "noscript",
      "plaintext",
      "script",
      // <selectedcontent> mirrors the selected <option>'s subtree, cloned by
      // the UA (customizable <select>) — including any on* handlers — and the
      // engine re-mirrors synchronously whenever a removal changes which
      // option/selectedcontent is current, even inside DOMPurify's inert
      // DOMParser document. Hoisting its children on removal re-inserts a fresh
      // mirror target ahead of the walk, which the engine refills, looping
      // forever (DoS) and amplifying output. Dropping its content on removal
      // (rather than hoisting) breaks that cascade; the content is a duplicate
      // of the option, which is sanitized on its own. See campaign-3 F1/F6.
      "selectedcontent",
      "style",
      "svg",
      "template",
      "thead",
      "title",
      "video",
      "xmp"
    ]);
    let DATA_URI_TAGS = null;
    const DEFAULT_DATA_URI_TAGS = addToSet({}, ["audio", "video", "img", "source", "image", "track"]);
    let URI_SAFE_ATTRIBUTES = null;
    const DEFAULT_URI_SAFE_ATTRIBUTES = addToSet({}, ["alt", "class", "for", "id", "label", "name", "pattern", "placeholder", "role", "summary", "title", "value", "style", "xmlns"]);
    const MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML";
    const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
    const HTML_NAMESPACE = "http://www.w3.org/1999/xhtml";
    let NAMESPACE = HTML_NAMESPACE;
    let IS_EMPTY_INPUT = false;
    let ALLOWED_NAMESPACES = null;
    const DEFAULT_ALLOWED_NAMESPACES = addToSet({}, [MATHML_NAMESPACE, SVG_NAMESPACE, HTML_NAMESPACE], stringToString);
    const DEFAULT_MATHML_TEXT_INTEGRATION_POINTS = freeze(["mi", "mo", "mn", "ms", "mtext"]);
    let MATHML_TEXT_INTEGRATION_POINTS = addToSet({}, DEFAULT_MATHML_TEXT_INTEGRATION_POINTS);
    const DEFAULT_HTML_INTEGRATION_POINTS = freeze(["annotation-xml"]);
    let HTML_INTEGRATION_POINTS = addToSet({}, DEFAULT_HTML_INTEGRATION_POINTS);
    const COMMON_SVG_AND_HTML_ELEMENTS = addToSet({}, ["title", "style", "font", "a", "script"]);
    let PARSER_MEDIA_TYPE = null;
    const SUPPORTED_PARSER_MEDIA_TYPES = ["application/xhtml+xml", "text/html"];
    const DEFAULT_PARSER_MEDIA_TYPE = "text/html";
    let transformCaseFunc = null;
    let CONFIG = null;
    const formElement = document2.createElement("form");
    const isRegexOrFunction = function isRegexOrFunction2(testValue) {
      return testValue instanceof RegExp || testValue instanceof Function;
    };
    const _parseConfig = function _parseConfig2() {
      let cfg = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
      if (CONFIG && CONFIG === cfg) {
        return;
      }
      if (!cfg || typeof cfg !== "object") {
        cfg = {};
      }
      cfg = clone(cfg);
      PARSER_MEDIA_TYPE = // eslint-disable-next-line unicorn/prefer-includes
      SUPPORTED_PARSER_MEDIA_TYPES.indexOf(cfg.PARSER_MEDIA_TYPE) === -1 ? DEFAULT_PARSER_MEDIA_TYPE : cfg.PARSER_MEDIA_TYPE;
      transformCaseFunc = PARSER_MEDIA_TYPE === "application/xhtml+xml" ? stringToString : stringToLowerCase;
      ALLOWED_TAGS = _resolveSetOption(cfg, "ALLOWED_TAGS", DEFAULT_ALLOWED_TAGS, {
        transform: transformCaseFunc
      });
      ALLOWED_ATTR = _resolveSetOption(cfg, "ALLOWED_ATTR", DEFAULT_ALLOWED_ATTR, {
        transform: transformCaseFunc
      });
      ALLOWED_NAMESPACES = _resolveSetOption(cfg, "ALLOWED_NAMESPACES", DEFAULT_ALLOWED_NAMESPACES, {
        transform: stringToString
      });
      URI_SAFE_ATTRIBUTES = _resolveSetOption(cfg, "ADD_URI_SAFE_ATTR", DEFAULT_URI_SAFE_ATTRIBUTES, {
        transform: transformCaseFunc,
        base: DEFAULT_URI_SAFE_ATTRIBUTES
      });
      DATA_URI_TAGS = _resolveSetOption(cfg, "ADD_DATA_URI_TAGS", DEFAULT_DATA_URI_TAGS, {
        transform: transformCaseFunc,
        base: DEFAULT_DATA_URI_TAGS
      });
      FORBID_CONTENTS = _resolveSetOption(cfg, "FORBID_CONTENTS", DEFAULT_FORBID_CONTENTS, {
        transform: transformCaseFunc
      });
      FORBID_TAGS = _resolveSetOption(cfg, "FORBID_TAGS", clone({}), {
        transform: transformCaseFunc
      });
      FORBID_ATTR = _resolveSetOption(cfg, "FORBID_ATTR", clone({}), {
        transform: transformCaseFunc
      });
      USE_PROFILES = objectHasOwnProperty(cfg, "USE_PROFILES") ? cfg.USE_PROFILES && typeof cfg.USE_PROFILES === "object" ? clone(cfg.USE_PROFILES) : cfg.USE_PROFILES : false;
      ALLOW_ARIA_ATTR = cfg.ALLOW_ARIA_ATTR !== false;
      ALLOW_DATA_ATTR = cfg.ALLOW_DATA_ATTR !== false;
      ALLOW_UNKNOWN_PROTOCOLS = cfg.ALLOW_UNKNOWN_PROTOCOLS || false;
      ALLOW_SELF_CLOSE_IN_ATTR = cfg.ALLOW_SELF_CLOSE_IN_ATTR !== false;
      SAFE_FOR_TEMPLATES = cfg.SAFE_FOR_TEMPLATES || false;
      SAFE_FOR_XML = cfg.SAFE_FOR_XML !== false;
      WHOLE_DOCUMENT = cfg.WHOLE_DOCUMENT || false;
      RETURN_DOM = cfg.RETURN_DOM || false;
      RETURN_DOM_FRAGMENT = cfg.RETURN_DOM_FRAGMENT || false;
      RETURN_TRUSTED_TYPE = cfg.RETURN_TRUSTED_TYPE || false;
      FORCE_BODY = cfg.FORCE_BODY || false;
      SANITIZE_DOM = cfg.SANITIZE_DOM !== false;
      SANITIZE_NAMED_PROPS = cfg.SANITIZE_NAMED_PROPS || false;
      KEEP_CONTENT = cfg.KEEP_CONTENT !== false;
      IN_PLACE = cfg.IN_PLACE || false;
      IS_ALLOWED_URI$1 = isRegex(cfg.ALLOWED_URI_REGEXP) ? cfg.ALLOWED_URI_REGEXP : IS_ALLOWED_URI;
      NAMESPACE = typeof cfg.NAMESPACE === "string" ? cfg.NAMESPACE : HTML_NAMESPACE;
      MATHML_TEXT_INTEGRATION_POINTS = _resolveObjectOption(
        cfg,
        "MATHML_TEXT_INTEGRATION_POINTS",
        () => addToSet({}, DEFAULT_MATHML_TEXT_INTEGRATION_POINTS)
        // Default built-in map
      );
      HTML_INTEGRATION_POINTS = _resolveObjectOption(
        cfg,
        "HTML_INTEGRATION_POINTS",
        () => addToSet({}, DEFAULT_HTML_INTEGRATION_POINTS)
        // Default built-in map
      );
      const customElementHandling = _resolveObjectOption(cfg, "CUSTOM_ELEMENT_HANDLING", () => create(null));
      CUSTOM_ELEMENT_HANDLING = create(null);
      if (objectHasOwnProperty(customElementHandling, "tagNameCheck") && isRegexOrFunction(customElementHandling.tagNameCheck)) {
        CUSTOM_ELEMENT_HANDLING.tagNameCheck = customElementHandling.tagNameCheck;
      }
      if (objectHasOwnProperty(customElementHandling, "attributeNameCheck") && isRegexOrFunction(customElementHandling.attributeNameCheck)) {
        CUSTOM_ELEMENT_HANDLING.attributeNameCheck = customElementHandling.attributeNameCheck;
      }
      if (objectHasOwnProperty(customElementHandling, "allowCustomizedBuiltInElements") && typeof customElementHandling.allowCustomizedBuiltInElements === "boolean") {
        CUSTOM_ELEMENT_HANDLING.allowCustomizedBuiltInElements = customElementHandling.allowCustomizedBuiltInElements;
      }
      seal(CUSTOM_ELEMENT_HANDLING);
      if (SAFE_FOR_TEMPLATES) {
        ALLOW_DATA_ATTR = false;
      }
      if (RETURN_DOM_FRAGMENT) {
        RETURN_DOM = true;
      }
      if (USE_PROFILES) {
        ALLOWED_TAGS = addToSet({}, text);
        ALLOWED_ATTR = create(null);
        if (USE_PROFILES.html === true) {
          addToSet(ALLOWED_TAGS, html$1);
          addToSet(ALLOWED_ATTR, html);
        }
        if (USE_PROFILES.svg === true) {
          addToSet(ALLOWED_TAGS, svg$1);
          addToSet(ALLOWED_ATTR, svg);
          addToSet(ALLOWED_ATTR, xml);
        }
        if (USE_PROFILES.svgFilters === true) {
          addToSet(ALLOWED_TAGS, svgFilters);
          addToSet(ALLOWED_ATTR, svg);
          addToSet(ALLOWED_ATTR, xml);
        }
        if (USE_PROFILES.mathMl === true) {
          addToSet(ALLOWED_TAGS, mathMl$1);
          addToSet(ALLOWED_ATTR, mathMl);
          addToSet(ALLOWED_ATTR, xml);
        }
      }
      EXTRA_ELEMENT_HANDLING.tagCheck = null;
      EXTRA_ELEMENT_HANDLING.attributeCheck = null;
      if (objectHasOwnProperty(cfg, "ADD_TAGS")) {
        if (typeof cfg.ADD_TAGS === "function") {
          EXTRA_ELEMENT_HANDLING.tagCheck = cfg.ADD_TAGS;
        } else if (arrayIsArray(cfg.ADD_TAGS)) {
          if (ALLOWED_TAGS === DEFAULT_ALLOWED_TAGS) {
            ALLOWED_TAGS = clone(ALLOWED_TAGS);
          }
          addToSet(ALLOWED_TAGS, cfg.ADD_TAGS, transformCaseFunc);
        }
      }
      if (objectHasOwnProperty(cfg, "ADD_ATTR")) {
        if (typeof cfg.ADD_ATTR === "function") {
          EXTRA_ELEMENT_HANDLING.attributeCheck = cfg.ADD_ATTR;
        } else if (arrayIsArray(cfg.ADD_ATTR)) {
          if (ALLOWED_ATTR === DEFAULT_ALLOWED_ATTR) {
            ALLOWED_ATTR = clone(ALLOWED_ATTR);
          }
          addToSet(ALLOWED_ATTR, cfg.ADD_ATTR, transformCaseFunc);
        }
      }
      if (objectHasOwnProperty(cfg, "ADD_FORBID_CONTENTS") && arrayIsArray(cfg.ADD_FORBID_CONTENTS)) {
        if (FORBID_CONTENTS === DEFAULT_FORBID_CONTENTS) {
          FORBID_CONTENTS = clone(FORBID_CONTENTS);
        }
        addToSet(FORBID_CONTENTS, cfg.ADD_FORBID_CONTENTS, transformCaseFunc);
      }
      if (KEEP_CONTENT) {
        ALLOWED_TAGS["#text"] = true;
      }
      if (WHOLE_DOCUMENT) {
        addToSet(ALLOWED_TAGS, ["html", "head", "body"]);
      }
      if (ALLOWED_TAGS.table) {
        addToSet(ALLOWED_TAGS, ["tbody"]);
        delete FORBID_TAGS.tbody;
      }
      if (cfg.TRUSTED_TYPES_POLICY) {
        if (typeof cfg.TRUSTED_TYPES_POLICY.createHTML !== "function") {
          throw typeErrorCreate('TRUSTED_TYPES_POLICY configuration option must provide a "createHTML" hook.');
        }
        if (typeof cfg.TRUSTED_TYPES_POLICY.createScriptURL !== "function") {
          throw typeErrorCreate('TRUSTED_TYPES_POLICY configuration option must provide a "createScriptURL" hook.');
        }
        const previousTrustedTypesPolicy = trustedTypesPolicy;
        trustedTypesPolicy = cfg.TRUSTED_TYPES_POLICY;
        try {
          emptyHTML = _createTrustedHTML("");
        } catch (error) {
          trustedTypesPolicy = previousTrustedTypesPolicy;
          throw error;
        }
      } else if (cfg.TRUSTED_TYPES_POLICY === null) {
        trustedTypesPolicy = void 0;
        emptyHTML = "";
      } else {
        if (trustedTypesPolicy === void 0) {
          trustedTypesPolicy = _getDefaultTrustedTypesPolicy();
        }
        if (trustedTypesPolicy && typeof emptyHTML === "string") {
          emptyHTML = _createTrustedHTML("");
        }
      }
      if (freeze) {
        freeze(cfg);
      }
      CONFIG = cfg;
    };
    const ALL_SVG_TAGS = addToSet({}, [...svg$1, ...svgFilters, ...svgDisallowed]);
    const ALL_MATHML_TAGS = addToSet({}, [...mathMl$1, ...mathMlDisallowed]);
    const _checkSvgNamespace = function _checkSvgNamespace2(tagName, parent, parentTagName) {
      if (parent.namespaceURI === HTML_NAMESPACE) {
        return tagName === "svg";
      }
      if (parent.namespaceURI === MATHML_NAMESPACE) {
        return tagName === "svg" && (parentTagName === "annotation-xml" || MATHML_TEXT_INTEGRATION_POINTS[parentTagName]);
      }
      return Boolean(ALL_SVG_TAGS[tagName]);
    };
    const _checkMathMlNamespace = function _checkMathMlNamespace2(tagName, parent, parentTagName) {
      if (parent.namespaceURI === HTML_NAMESPACE) {
        return tagName === "math";
      }
      if (parent.namespaceURI === SVG_NAMESPACE) {
        return tagName === "math" && HTML_INTEGRATION_POINTS[parentTagName];
      }
      return Boolean(ALL_MATHML_TAGS[tagName]);
    };
    const _checkHtmlNamespace = function _checkHtmlNamespace2(tagName, parent, parentTagName) {
      if (parent.namespaceURI === SVG_NAMESPACE && !HTML_INTEGRATION_POINTS[parentTagName]) {
        return false;
      }
      if (parent.namespaceURI === MATHML_NAMESPACE && !MATHML_TEXT_INTEGRATION_POINTS[parentTagName]) {
        return false;
      }
      return !ALL_MATHML_TAGS[tagName] && (COMMON_SVG_AND_HTML_ELEMENTS[tagName] || !ALL_SVG_TAGS[tagName]);
    };
    const _checkValidNamespace = function _checkValidNamespace2(element2) {
      let parent = getParentNode(element2);
      if (!parent || !parent.tagName) {
        parent = {
          namespaceURI: NAMESPACE,
          tagName: "template"
        };
      }
      const tagName = stringToLowerCase(element2.tagName);
      const parentTagName = stringToLowerCase(parent.tagName);
      if (!ALLOWED_NAMESPACES[element2.namespaceURI]) {
        return false;
      }
      if (element2.namespaceURI === SVG_NAMESPACE) {
        return _checkSvgNamespace(tagName, parent, parentTagName);
      }
      if (element2.namespaceURI === MATHML_NAMESPACE) {
        return _checkMathMlNamespace(tagName, parent, parentTagName);
      }
      if (element2.namespaceURI === HTML_NAMESPACE) {
        return _checkHtmlNamespace(tagName, parent, parentTagName);
      }
      if (PARSER_MEDIA_TYPE === "application/xhtml+xml" && ALLOWED_NAMESPACES[element2.namespaceURI]) {
        return true;
      }
      return false;
    };
    const _forceRemove = function _forceRemove2(node) {
      arrayPush(DOMPurify.removed, {
        element: node
      });
      try {
        getParentNode(node).removeChild(node);
      } catch (_) {
        remove(node);
        if (!getParentNode(node)) {
          throw typeErrorCreate("a node selected for removal could not be detached from its tree and cannot be safely returned; refusing to sanitize in place");
        }
      }
    };
    const _stripAttributeNode = function _stripAttributeNode2(element2, attribute, name) {
      try {
        removeAttributeNode(element2, attribute);
      } catch (_) {
        try {
          element2.removeAttribute(name);
        } catch (_2) {
        }
      }
    };
    const _neutralizeRoot = function _neutralizeRoot2(root) {
      _neutralizeSubtree(root);
      const childNodes = getChildNodes(root);
      if (childNodes) {
        const snapshot = [];
        arrayForEach(childNodes, (child) => {
          arrayPush(snapshot, child);
        });
        arrayForEach(snapshot, (child) => {
          try {
            remove(child);
          } catch (_) {
          }
        });
      }
      const attributes = getAttributes(root);
      if (attributes) {
        for (let i = attributes.length - 1; i >= 0; --i) {
          const attribute = attributes[i];
          const name = attribute && attribute.name;
          if (typeof name === "string") {
            _stripAttributeNode(root, attribute, name);
          }
        }
      }
    };
    const _removeAttribute = function _removeAttribute2(name, element2, attr) {
      if (!attr) {
        try {
          attr = element2.getAttributeNode(name);
        } catch (_) {
          attr = null;
        }
      }
      arrayPush(DOMPurify.removed, {
        attribute: attr || null,
        from: element2
      });
      try {
        if (attr) {
          removeAttributeNode(element2, attr);
        } else {
          element2.removeAttribute(name);
        }
      } catch (_) {
        try {
          element2.removeAttribute(name);
        } catch (_2) {
        }
      }
      if (name === "is") {
        if (RETURN_DOM || RETURN_DOM_FRAGMENT) {
          try {
            _forceRemove(element2);
          } catch (_) {
          }
        } else {
          try {
            element2.setAttribute(name, "");
          } catch (_) {
          }
        }
      }
    };
    const _stripDisallowedAttributes = function _stripDisallowedAttributes2(element2) {
      const attributes = getAttributes(element2);
      if (!attributes) {
        return;
      }
      for (let i = attributes.length - 1; i >= 0; --i) {
        const attribute = attributes[i];
        const name = attribute && attribute.name;
        if (typeof name !== "string" || ALLOWED_ATTR[transformCaseFunc(name)]) {
          continue;
        }
        _stripAttributeNode(element2, attribute, name);
      }
    };
    const _neutralizeSubtree = function _neutralizeSubtree2(root) {
      const stack = [root];
      while (stack.length > 0) {
        const node = stack.pop();
        const nodeType = _readNodeType(node);
        if (nodeType === NODE_TYPE.element) {
          _stripDisallowedAttributes(node);
        }
        const childNodes = getChildNodes(node);
        if (childNodes) {
          for (let i = childNodes.length - 1; i >= 0; --i) {
            stack.push(childNodes[i]);
          }
        }
      }
    };
    const _isPatchLinkageAttribute = function _isPatchLinkageAttribute2(lcName, lcTag) {
      if (!SAFE_FOR_XML) {
        return false;
      }
      if (lcName === "patchsrc") {
        return true;
      }
      return lcName === "for" && lcTag !== "label" && lcTag !== "output";
    };
    const _neutralizePatchLinkage = function _neutralizePatchLinkage2(root) {
      if (!SAFE_FOR_XML) {
        return;
      }
      const stack = [root];
      while (stack.length > 0) {
        const node = stack.pop();
        const nodeType = _readNodeType(node);
        if (nodeType === NODE_TYPE.processingInstruction || nodeType === NODE_TYPE.comment && regExpTest(COMMENT_MARKUP_PROBE, node.data)) {
          try {
            remove(node);
          } catch (_) {
          }
          continue;
        }
        if (nodeType === NODE_TYPE.element) {
          const element2 = node;
          const lcTag = transformCaseFunc(_readNodeName(node));
          try {
            if (element2.hasAttribute && element2.hasAttribute("patchsrc")) {
              element2.removeAttribute("patchsrc");
            }
            if (element2.hasAttribute && element2.hasAttribute("for") && _isPatchLinkageAttribute("for", lcTag)) {
              element2.removeAttribute("for");
            }
          } catch (_) {
          }
        }
        const childNodes = getChildNodes(node);
        if (childNodes) {
          for (let i = childNodes.length - 1; i >= 0; --i) {
            stack.push(childNodes[i]);
          }
        }
      }
    };
    const _initDocument = function _initDocument2(dirty) {
      let doc = null;
      let leadingWhitespace = null;
      if (FORCE_BODY) {
        dirty = "<remove></remove>" + dirty;
      } else {
        const matches = stringMatch(dirty, /^[\r\n\t ]+/);
        leadingWhitespace = matches && matches[0];
      }
      if (PARSER_MEDIA_TYPE === "application/xhtml+xml" && NAMESPACE === HTML_NAMESPACE) {
        dirty = '<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body>' + dirty + "</body></html>";
      }
      const dirtyPayload = trustedTypesPolicy ? _createTrustedHTML(dirty) : dirty;
      if (NAMESPACE === HTML_NAMESPACE) {
        try {
          doc = new DOMParser().parseFromString(dirtyPayload, PARSER_MEDIA_TYPE);
        } catch (_) {
        }
      }
      if (!doc || !doc.documentElement) {
        doc = implementation.createDocument(NAMESPACE, "template", null);
        try {
          doc.documentElement.innerHTML = IS_EMPTY_INPUT ? emptyHTML : dirtyPayload;
        } catch (_) {
        }
      }
      const body = doc.body || doc.documentElement;
      if (dirty && leadingWhitespace) {
        body.insertBefore(document2.createTextNode(leadingWhitespace), body.childNodes[0] || null);
      }
      if (NAMESPACE === HTML_NAMESPACE) {
        return getElementsByTagName.call(doc, WHOLE_DOCUMENT ? "html" : "body")[0];
      }
      return WHOLE_DOCUMENT ? doc.documentElement : body;
    };
    const _createNodeIterator = function _createNodeIterator2(root) {
      const doc = getOwnerDocument ? getOwnerDocument(root) : root.ownerDocument;
      return createNodeIterator.call(
        doc || root,
        root,
        // eslint-disable-next-line no-bitwise
        NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_COMMENT | NodeFilter.SHOW_TEXT | NodeFilter.SHOW_PROCESSING_INSTRUCTION | NodeFilter.SHOW_CDATA_SECTION,
        null
      );
    };
    const _stripTemplateExpressions = function _stripTemplateExpressions2(value) {
      value = stringReplace(value, MUSTACHE_EXPR$1, " ");
      value = stringReplace(value, ERB_EXPR$1, " ");
      value = stringReplace(value, TMPLIT_EXPR$1, " ");
      return value;
    };
    const _scrubTemplateExpressions2 = function _scrubTemplateExpressions(node) {
      var _node$querySelectorAl;
      node.normalize();
      const doc = getOwnerDocument ? getOwnerDocument(node) : node.ownerDocument;
      const walker = createNodeIterator.call(
        doc || node,
        node,
        // eslint-disable-next-line no-bitwise
        NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT | NodeFilter.SHOW_CDATA_SECTION | NodeFilter.SHOW_PROCESSING_INSTRUCTION,
        null
      );
      let currentNode = walker.nextNode();
      while (currentNode) {
        currentNode.data = _stripTemplateExpressions(currentNode.data);
        currentNode = walker.nextNode();
      }
      const templates = (_node$querySelectorAl = node.querySelectorAll) === null || _node$querySelectorAl === void 0 ? void 0 : _node$querySelectorAl.call(node, "template");
      if (templates) {
        arrayForEach(templates, (tmpl) => {
          if (_isDocumentFragment(tmpl.content)) {
            _scrubTemplateExpressions2(tmpl.content);
          }
        });
      }
    };
    const _isClobbered = function _isClobbered2(element2) {
      const realTagName = getNodeName ? getNodeName(element2) : null;
      if (typeof realTagName !== "string") {
        return false;
      }
      if (transformCaseFunc(realTagName) !== "form") {
        return false;
      }
      return typeof element2.nodeName !== "string" || typeof element2.textContent !== "string" || typeof element2.removeChild !== "function" || // Realm-safe NamedNodeMap detection: equality against the cached
      // prototype getter. Clobbered .attributes (e.g. <input name="attributes">)
      // makes the direct read diverge from the cached read; a clean form
      // (same-realm OR foreign-realm) has both reads pointing at the same
      // canonical NamedNodeMap.
      element2.attributes !== getAttributes(element2) || typeof element2.removeAttribute !== "function" || // A form descendant named "removeAttributeNode" or "getAttributeNode"
      // shadows these Attr-node methods via [LegacyOverrideBuiltIns].
      // _removeAttribute() / _stripAttributeNode() reach for
      // element.removeAttributeNode(attr) first; when it is shadowed the call
      // throws and the name-based fallback element.removeAttribute(name)
      // ASCII-lowercases its lookup key in an HTML document, silently missing
      // a case-preserved event-handler attribute (e.g. an ONANIMATIONSTART
      // that reached the sanitizer through an XML/XHTML parse). Flag the form
      // so it is removed wholesale, exactly as for the other shadowed methods.
      typeof element2.removeAttributeNode !== "function" || typeof element2.getAttributeNode !== "function" || typeof element2.setAttribute !== "function" || typeof element2.namespaceURI !== "string" || typeof element2.insertBefore !== "function" || typeof element2.hasChildNodes !== "function" || // NodeType clobbering probe. Cached Node.prototype.nodeType getter
      // returns the integer 1 for any Element regardless of realm; direct
      // read on a clobbered form (e.g. <input name="nodeType">) returns
      // the named child element. Cheap addition — nodeType is read from
      // an internal slot, no serialization cost — and removes a residual
      // clobbering surface used by several mXSS / PI / comment branches
      // in _sanitizeElements that compare currentNode.nodeType directly.
      element2.nodeType !== getNodeType(element2) || // HTMLFormElement has [LegacyOverrideBuiltIns]: a descendant named
      // "childNodes" shadows the prototype getter. Direct reads of
      // form.childNodes from a clobbered form return the named child
      // instead of the real NodeList, so any walk that reads it directly
      // skips the form's real children. Compare the direct read to the
      // cached Node.prototype getter — when the form's named-property
      // getter intercepts the read, the two values differ and we flag
      // the form. This catches every clobbering child type (input,
      // select, etc.) regardless of whether the named child happens to
      // carry a numeric .length, which a typeof-based probe would miss
      // (e.g. HTMLSelectElement.length is a defined unsigned-long).
      element2.childNodes !== getChildNodes(element2);
    };
    const _isDocumentFragment = function _isDocumentFragment2(value) {
      if (!getNodeType || typeof value !== "object" || value === null) {
        return false;
      }
      try {
        return getNodeType(value) === NODE_TYPE.documentFragment;
      } catch (_) {
        return false;
      }
    };
    const _isNode = function _isNode2(value) {
      if (!getNodeType || typeof value !== "object" || value === null) {
        return false;
      }
      try {
        return typeof getNodeType(value) === "number";
      } catch (_) {
        return false;
      }
    };
    function _executeHooks(hooks2, currentNode, data) {
      if (hooks2.length === 0) {
        return;
      }
      arrayForEach(hooks2, (hook) => {
        hook.call(DOMPurify, currentNode, data, CONFIG);
      });
    }
    const _isUnsafeNode = function _isUnsafeNode2(currentNode, tagName) {
      if (SAFE_FOR_XML && currentNode.hasChildNodes() && !_isNode(currentNode.firstElementChild) && regExpTest(ELEMENT_MARKUP_PROBE, currentNode.textContent) && regExpTest(ELEMENT_MARKUP_PROBE, currentNode.innerHTML)) {
        return true;
      }
      if (SAFE_FOR_XML && currentNode.namespaceURI === HTML_NAMESPACE && LITERAL_TEXT_ELEMENTS[tagName] && (_isNode(currentNode.firstElementChild) || typeof currentNode.textContent === "string" && regExpTest(LITERAL_TEXT_CLOSE[tagName], currentNode.textContent))) {
        return true;
      }
      if (currentNode.nodeType === NODE_TYPE.processingInstruction) {
        return true;
      }
      if (SAFE_FOR_XML && currentNode.nodeType === NODE_TYPE.comment && regExpTest(COMMENT_MARKUP_PROBE, currentNode.data)) {
        return true;
      }
      return false;
    };
    const _matchesNameCheck = function _matchesNameCheck2(check, name) {
      if (check instanceof RegExp) {
        return regExpTest(check, name);
      }
      if (check instanceof Function) {
        for (var _len = arguments.length, args = new Array(_len > 2 ? _len - 2 : 0), _key = 2; _key < _len; _key++) {
          args[_key - 2] = arguments[_key];
        }
        return Boolean(check(name, ...args));
      }
      return false;
    };
    const _sanitizeDisallowedNode = function _sanitizeDisallowedNode2(currentNode, tagName, root) {
      if (!FORBID_TAGS[tagName] && _isBasicCustomElement(tagName) && _matchesNameCheck(CUSTOM_ELEMENT_HANDLING.tagNameCheck, tagName)) {
        return false;
      }
      if (KEEP_CONTENT && !FORBID_CONTENTS[tagName]) {
        const parentNode = getParentNode(currentNode);
        const childNodes = getChildNodes(currentNode);
        if (childNodes && parentNode) {
          const childCount = childNodes.length;
          for (let i = childCount - 1; i >= 0; --i) {
            const hoisted = currentNode === root ? cloneNode(childNodes[i], true) : childNodes[i];
            parentNode.insertBefore(hoisted, getNextSibling(currentNode));
          }
        }
      }
      _forceRemove(currentNode);
      return true;
    };
    const _forkSharedAllowlist = function _forkSharedAllowlist2(hookList, set, defaultSet, setConfigSet) {
      if (hookList.length === 0) {
        return set;
      }
      return set === defaultSet || set === setConfigSet ? clone(set) : set;
    };
    const _handleHookDetachedNode = function _handleHookDetachedNode2(currentNode, root) {
      if (currentNode === root || getParentNode(currentNode) !== null) {
        return false;
      }
      if (IN_PLACE) {
        _neutralizeSubtree(currentNode);
      }
      return true;
    };
    const _sanitizeElements = function _sanitizeElements2(currentNode, root) {
      _executeHooks(hooks.beforeSanitizeElements, currentNode, null);
      if (_handleHookDetachedNode(currentNode, root)) {
        return true;
      }
      if (_isClobbered(currentNode)) {
        _forceRemove(currentNode);
        return true;
      }
      const tagName = transformCaseFunc(_readNodeName(currentNode));
      ALLOWED_TAGS = _forkSharedAllowlist(hooks.uponSanitizeElement, ALLOWED_TAGS, DEFAULT_ALLOWED_TAGS, SET_CONFIG_ALLOWED_TAGS);
      _executeHooks(hooks.uponSanitizeElement, currentNode, {
        tagName,
        allowedTags: ALLOWED_TAGS
      });
      if (_handleHookDetachedNode(currentNode, root)) {
        return true;
      }
      if (_isUnsafeNode(currentNode, tagName)) {
        _forceRemove(currentNode);
        return true;
      }
      if (FORBID_TAGS[tagName] || !(EXTRA_ELEMENT_HANDLING.tagCheck instanceof Function && EXTRA_ELEMENT_HANDLING.tagCheck(tagName)) && !ALLOWED_TAGS[tagName]) {
        const removed = _sanitizeDisallowedNode(currentNode, tagName, root);
        if (removed === false) {
          _executeHooks(hooks.afterSanitizeElements, currentNode, null);
        }
        return removed;
      }
      const nt = _readNodeType(currentNode);
      if (nt === NODE_TYPE.element && !_checkValidNamespace(currentNode)) {
        _forceRemove(currentNode);
        return true;
      }
      if ((tagName === "noscript" || tagName === "noembed" || tagName === "noframes") && regExpTest(FALLBACK_TAG_CLOSE, currentNode.innerHTML)) {
        _forceRemove(currentNode);
        return true;
      }
      if (SAFE_FOR_TEMPLATES && currentNode.nodeType === NODE_TYPE.text) {
        const content = _stripTemplateExpressions(currentNode.textContent);
        if (currentNode.textContent !== content) {
          arrayPush(DOMPurify.removed, {
            element: currentNode.cloneNode()
          });
          currentNode.textContent = content;
        }
      }
      _executeHooks(hooks.afterSanitizeElements, currentNode, null);
      return false;
    };
    const _isValidAttribute = function _isValidAttribute2(lcTag, lcName, value) {
      if (FORBID_ATTR[lcName]) {
        return false;
      }
      if (_isPatchLinkageAttribute(lcName, lcTag)) {
        return false;
      }
      if (SANITIZE_DOM && (lcName === "id" || lcName === "name") && (value in document2 || value in formElement)) {
        return false;
      }
      const nameIsPermitted = ALLOWED_ATTR[lcName] || EXTRA_ELEMENT_HANDLING.attributeCheck instanceof Function && EXTRA_ELEMENT_HANDLING.attributeCheck(lcName, lcTag);
      if (ALLOW_DATA_ATTR && regExpTest(DATA_ATTR$1, lcName)) {
        return true;
      }
      if (ALLOW_ARIA_ATTR && regExpTest(ARIA_ATTR$1, lcName)) {
        return true;
      }
      if (!nameIsPermitted) {
        return (
          // Condition a) covers a basically valid custom element tag name whose
          // tag passes the configured tagNameCheck and whose attribute name
          // passes the configured attributeNameCheck ...
          _isBasicCustomElement(lcTag) && _matchesNameCheck(CUSTOM_ELEMENT_HANDLING.tagNameCheck, lcTag) && _matchesNameCheck(CUSTOM_ELEMENT_HANDLING.attributeNameCheck, lcName, lcTag) || // Condition b) covers an `is` attribute whose value passes the
          // configured tagNameCheck while customized built-in elements are
          // allowed.
          lcName === "is" && CUSTOM_ELEMENT_HANDLING.allowCustomizedBuiltInElements && _matchesNameCheck(CUSTOM_ELEMENT_HANDLING.tagNameCheck, value)
        );
      }
      if (URI_SAFE_ATTRIBUTES[lcName]) {
        return true;
      }
      if (regExpTest(IS_ALLOWED_URI$1, stringReplace(value, ATTR_WHITESPACE$1, ""))) {
        return true;
      }
      if ((lcName === "src" || lcName === "xlink:href" || lcName === "href") && lcTag !== "script" && stringIndexOf(value, "data:") === 0 && DATA_URI_TAGS[lcTag]) {
        return true;
      }
      if (ALLOW_UNKNOWN_PROTOCOLS && !regExpTest(IS_SCRIPT_OR_DATA$1, stringReplace(value, ATTR_WHITESPACE$1, ""))) {
        return true;
      }
      return !value;
    };
    const RESERVED_CUSTOM_ELEMENT_NAMES = addToSet({}, ["annotation-xml", "color-profile", "font-face", "font-face-format", "font-face-name", "font-face-src", "font-face-uri", "missing-glyph"]);
    const _isBasicCustomElement = function _isBasicCustomElement2(tagName) {
      return !RESERVED_CUSTOM_ELEMENT_NAMES[stringToLowerCase(tagName)] && regExpTest(CUSTOM_ELEMENT$1, tagName);
    };
    const _applyTrustedTypesToAttribute = function _applyTrustedTypesToAttribute2(lcTag, lcName, namespaceURI, value) {
      if (trustedTypesPolicy && typeof trustedTypes === "object" && typeof trustedTypes.getAttributeType === "function" && !namespaceURI) {
        switch (trustedTypes.getAttributeType(lcTag, lcName)) {
          case "TrustedHTML": {
            return _createTrustedHTML(value);
          }
          case "TrustedScriptURL": {
            return _createTrustedScriptURL(value);
          }
        }
      }
      return value;
    };
    const _setAttributeValue = function _setAttributeValue2(currentNode, name, namespaceURI, value) {
      try {
        if (namespaceURI) {
          currentNode.setAttributeNS(namespaceURI, name, value);
        } else {
          currentNode.setAttribute(name, value);
        }
        if (_isClobbered(currentNode)) {
          _forceRemove(currentNode);
          return false;
        }
        return true;
      } catch (_) {
        _removeAttribute(name, currentNode);
        return false;
      }
    };
    const _sanitizeAttributes = function _sanitizeAttributes2(currentNode) {
      _executeHooks(hooks.beforeSanitizeAttributes, currentNode, null);
      const attributes = currentNode.attributes;
      if (!attributes || _isClobbered(currentNode)) {
        return;
      }
      ALLOWED_ATTR = _forkSharedAllowlist(hooks.uponSanitizeAttribute, ALLOWED_ATTR, DEFAULT_ALLOWED_ATTR, SET_CONFIG_ALLOWED_ATTR);
      const hookEvent = {
        attrName: "",
        attrValue: "",
        keepAttr: true,
        allowedAttributes: ALLOWED_ATTR,
        forceKeepAttr: void 0
      };
      let l = attributes.length;
      const lcTag = transformCaseFunc(currentNode.nodeName);
      while (l--) {
        const attr = attributes[l];
        const name = attr.name, namespaceURI = attr.namespaceURI, attrValue = attr.value;
        const lcName = transformCaseFunc(name);
        const initValue = attrValue;
        let value = name === "value" ? initValue : stringTrim(initValue);
        let recreatedNamedProp = false;
        hookEvent.attrName = lcName;
        hookEvent.attrValue = value;
        hookEvent.keepAttr = true;
        hookEvent.forceKeepAttr = void 0;
        _executeHooks(hooks.uponSanitizeAttribute, currentNode, hookEvent);
        value = hookEvent.attrValue;
        if (SANITIZE_NAMED_PROPS && (lcName === "id" || lcName === "name") && stringIndexOf(value, SANITIZE_NAMED_PROPS_PREFIX) !== 0) {
          _removeAttribute(name, currentNode, attr);
          value = SANITIZE_NAMED_PROPS_PREFIX + value;
          recreatedNamedProp = true;
        }
        if (SAFE_FOR_XML && regExpTest(/((--!?|])>)|<\/(style|script|title|xmp|textarea|noscript|iframe|noembed|noframes)/i, value)) {
          _removeAttribute(name, currentNode, attr);
          continue;
        }
        if (lcName === "attributename" && stringMatch(value, "href")) {
          _removeAttribute(name, currentNode, attr);
          continue;
        }
        if (hookEvent.forceKeepAttr) {
          continue;
        }
        if (!hookEvent.keepAttr) {
          _removeAttribute(name, currentNode, attr);
          continue;
        }
        if (!ALLOW_SELF_CLOSE_IN_ATTR && regExpTest(SELF_CLOSING_TAG, value)) {
          _removeAttribute(name, currentNode, attr);
          continue;
        }
        if (SAFE_FOR_TEMPLATES) {
          value = _stripTemplateExpressions(value);
        }
        if (!_isValidAttribute(lcTag, lcName, value)) {
          _removeAttribute(name, currentNode, attr);
          continue;
        }
        value = _applyTrustedTypesToAttribute(lcTag, lcName, namespaceURI, value);
        if (value !== initValue) {
          const cleanWrite = _setAttributeValue(currentNode, name, namespaceURI, value);
          if (cleanWrite && recreatedNamedProp) {
            arrayPop(DOMPurify.removed);
          }
        }
      }
      _executeHooks(hooks.afterSanitizeAttributes, currentNode, null);
    };
    const _sanitizeShadowDOM2 = function _sanitizeShadowDOM(fragment) {
      let shadowNode = null;
      const shadowIterator = _createNodeIterator(fragment);
      _executeHooks(hooks.beforeSanitizeShadowDOM, fragment, null);
      while (shadowNode = shadowIterator.nextNode()) {
        _executeHooks(hooks.uponSanitizeShadowNode, shadowNode, null);
        _sanitizeElements(shadowNode, fragment);
        _sanitizeAttributes(shadowNode);
        if (_isDocumentFragment(shadowNode.content)) {
          _sanitizeShadowDOM2(shadowNode.content);
        }
        if (_readNodeType(shadowNode) === NODE_TYPE.element) {
          const innerSr = getShadowRoot(shadowNode);
          if (_isDocumentFragment(innerSr)) {
            _sanitizeAttachedShadowRoots(innerSr);
            _sanitizeShadowDOM2(innerSr);
          }
        }
      }
      _executeHooks(hooks.afterSanitizeShadowDOM, fragment, null);
    };
    const _sanitizeAttachedShadowRoots = function _sanitizeAttachedShadowRoots2(root) {
      const stack = [{
        node: root,
        shadow: null
      }];
      while (stack.length > 0) {
        const item = stack.pop();
        if (item.shadow) {
          _sanitizeShadowDOM2(item.shadow);
          continue;
        }
        const node = item.node;
        const nodeType = _readNodeType(node);
        const isElement = nodeType === NODE_TYPE.element;
        const childNodes = getChildNodes(node);
        if (childNodes) {
          for (let i = childNodes.length - 1; i >= 0; --i) {
            stack.push({
              node: childNodes[i],
              shadow: null
            });
          }
        }
        if (isElement) {
          const rootName = getNodeName ? getNodeName(node) : null;
          if (typeof rootName === "string" && transformCaseFunc(rootName) === "template") {
            const content = node.content;
            if (_isDocumentFragment(content)) {
              stack.push({
                node: content,
                shadow: null
              });
            }
          }
        }
        if (isElement) {
          const sr = getShadowRoot(node);
          if (_isDocumentFragment(sr)) {
            stack.push({
              node: null,
              shadow: sr
            }, {
              node: sr,
              shadow: null
            });
          }
        }
      }
    };
    DOMPurify.sanitize = function(dirty) {
      let cfg = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
      let body = null;
      let importedNode = null;
      let currentNode = null;
      let returnNode = null;
      IS_EMPTY_INPUT = !dirty;
      if (IS_EMPTY_INPUT) {
        dirty = "<!-->";
      }
      if (typeof dirty !== "string" && !_isNode(dirty)) {
        dirty = stringifyValue(dirty);
        if (typeof dirty !== "string") {
          throw typeErrorCreate("dirty is not a string, aborting");
        }
      }
      if (!DOMPurify.isSupported) {
        return dirty;
      }
      if (SET_CONFIG) {
        ALLOWED_TAGS = SET_CONFIG_ALLOWED_TAGS;
        ALLOWED_ATTR = SET_CONFIG_ALLOWED_ATTR;
      } else {
        _parseConfig(cfg);
      }
      if (hooks.uponSanitizeElement.length > 0 || hooks.uponSanitizeAttribute.length > 0) {
        ALLOWED_TAGS = clone(ALLOWED_TAGS);
      }
      if (hooks.uponSanitizeAttribute.length > 0) {
        ALLOWED_ATTR = clone(ALLOWED_ATTR);
      }
      DOMPurify.removed = [];
      const inPlace = IN_PLACE && typeof dirty !== "string" && _isNode(dirty);
      if (inPlace) {
        _neutralizePatchLinkage(dirty);
        const nn = _readNodeName(dirty);
        if (typeof nn === "string") {
          const tagName = transformCaseFunc(nn);
          if (!ALLOWED_TAGS[tagName] || FORBID_TAGS[tagName]) {
            _neutralizeRoot(dirty);
            throw typeErrorCreate("root node is forbidden and cannot be sanitized in-place");
          }
        }
        if (_isClobbered(dirty)) {
          _neutralizeRoot(dirty);
          throw typeErrorCreate("root node is clobbered and cannot be sanitized in-place");
        }
        try {
          _sanitizeAttachedShadowRoots(dirty);
        } catch (error) {
          _neutralizeRoot(dirty);
          throw error;
        }
      } else if (_isNode(dirty)) {
        body = _initDocument("<!---->");
        importedNode = body.ownerDocument.importNode(dirty, true);
        if (importedNode.nodeType === NODE_TYPE.element && importedNode.nodeName === "BODY") {
          body = importedNode;
        } else if (importedNode.nodeName === "HTML") {
          body = importedNode;
        } else {
          body.appendChild(importedNode);
        }
        _sanitizeAttachedShadowRoots(body);
      } else {
        if (!RETURN_DOM && !SAFE_FOR_TEMPLATES && !WHOLE_DOCUMENT && // eslint-disable-next-line unicorn/prefer-includes
        dirty.indexOf("<") === -1) {
          return trustedTypesPolicy && RETURN_TRUSTED_TYPE ? _createTrustedHTML(dirty) : dirty;
        }
        body = _initDocument(dirty);
        if (!body) {
          return RETURN_DOM ? null : RETURN_TRUSTED_TYPE ? emptyHTML : "";
        }
      }
      if (body && FORCE_BODY) {
        _forceRemove(body.firstChild);
      }
      const walkRoot = inPlace ? dirty : body;
      try {
        const nodeIterator = _createNodeIterator(walkRoot);
        while (currentNode = nodeIterator.nextNode()) {
          _sanitizeElements(currentNode, walkRoot);
          _sanitizeAttributes(currentNode);
          if (_isDocumentFragment(currentNode.content)) {
            _sanitizeShadowDOM2(currentNode.content);
          }
        }
      } catch (error) {
        if (inPlace) {
          _neutralizeRoot(dirty);
          arrayForEach(DOMPurify.removed, (entry) => {
            if (entry.element) {
              _neutralizeSubtree(entry.element);
            }
          });
        }
        throw error;
      }
      if (inPlace) {
        arrayForEach(DOMPurify.removed, (entry) => {
          if (entry.element) {
            _neutralizeSubtree(entry.element);
          }
        });
        if (SAFE_FOR_TEMPLATES) {
          _scrubTemplateExpressions2(dirty);
        }
        return dirty;
      }
      if (RETURN_DOM) {
        if (SAFE_FOR_TEMPLATES) {
          _scrubTemplateExpressions2(body);
        }
        if (RETURN_DOM_FRAGMENT) {
          returnNode = createDocumentFragment.call(body.ownerDocument);
          while (body.firstChild) {
            returnNode.appendChild(body.firstChild);
          }
        } else {
          returnNode = body;
        }
        if (ALLOWED_ATTR.shadowroot || ALLOWED_ATTR.shadowrootmode) {
          returnNode = importNode.call(originalDocument, returnNode, true);
        }
        return returnNode;
      }
      let serializedHTML = WHOLE_DOCUMENT ? body.outerHTML : body.innerHTML;
      if (WHOLE_DOCUMENT && ALLOWED_TAGS["!doctype"] && body.ownerDocument && body.ownerDocument.doctype && body.ownerDocument.doctype.name && regExpTest(DOCTYPE_NAME, body.ownerDocument.doctype.name)) {
        serializedHTML = "<!DOCTYPE " + body.ownerDocument.doctype.name + ">\n" + serializedHTML;
      }
      if (SAFE_FOR_TEMPLATES) {
        serializedHTML = _stripTemplateExpressions(serializedHTML);
      }
      return trustedTypesPolicy && RETURN_TRUSTED_TYPE ? _createTrustedHTML(serializedHTML) : serializedHTML;
    };
    DOMPurify.setConfig = function() {
      let cfg = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
      _parseConfig(cfg);
      SET_CONFIG = true;
      SET_CONFIG_ALLOWED_TAGS = ALLOWED_TAGS;
      SET_CONFIG_ALLOWED_ATTR = ALLOWED_ATTR;
    };
    DOMPurify.clearConfig = function() {
      CONFIG = null;
      SET_CONFIG = false;
      SET_CONFIG_ALLOWED_TAGS = null;
      SET_CONFIG_ALLOWED_ATTR = null;
      trustedTypesPolicy = defaultTrustedTypesPolicy;
      emptyHTML = "";
    };
    DOMPurify.isValidAttribute = function(tag, attr, value) {
      if (!CONFIG) {
        _parseConfig({});
      }
      const lcTag = transformCaseFunc(tag);
      const lcName = transformCaseFunc(attr);
      return _isValidAttribute(lcTag, lcName, value);
    };
    DOMPurify.addHook = function(entryPoint, hookFunction) {
      if (typeof hookFunction !== "function") {
        return;
      }
      if (!objectHasOwnProperty(hooks, entryPoint)) {
        return;
      }
      arrayPush(hooks[entryPoint], hookFunction);
    };
    DOMPurify.removeHook = function(entryPoint, hookFunction) {
      if (!objectHasOwnProperty(hooks, entryPoint)) {
        return void 0;
      }
      if (hookFunction !== void 0) {
        const index = arrayLastIndexOf(hooks[entryPoint], hookFunction);
        return index === -1 ? void 0 : arraySplice(hooks[entryPoint], index, 1)[0];
      }
      return arrayPop(hooks[entryPoint]);
    };
    DOMPurify.removeHooks = function(entryPoint) {
      if (!objectHasOwnProperty(hooks, entryPoint)) {
        return;
      }
      hooks[entryPoint] = [];
    };
    DOMPurify.removeAllHooks = function() {
      hooks = _createHooksMap();
    };
    return DOMPurify;
  }
  var purify = createDOMPurify();

  // node_modules/@nextcloud/l10n/dist/chunks/translation-DoG5ZELJ.mjs
  var import_escape_html = __toESM(require_escape_html(), 1);
  globalThis._nc_l10n_locale ?? (globalThis._nc_l10n_locale = typeof document !== "undefined" && document.documentElement.dataset.locale || Intl.DateTimeFormat().resolvedOptions().locale.replaceAll(/-/g, "_"));
  globalThis._nc_l10n_language ?? (globalThis._nc_l10n_language = typeof document !== "undefined" && document.documentElement.lang || (globalThis.navigator?.language ?? "en"));
  function getAppTranslations(appId) {
    return {
      translations: globalThis._oc_l10n_registry_translations[appId] ?? {},
      pluralFunction: globalThis._oc_l10n_registry_plural_functions[appId] ?? ((number) => number)
    };
  }
  globalThis._oc_l10n_registry_translations ?? (globalThis._oc_l10n_registry_translations = {});
  globalThis._oc_l10n_registry_plural_functions ?? (globalThis._oc_l10n_registry_plural_functions = {});
  function translate(app, text2, placeholdersOrNumber, optionsOrNumber, options) {
    const vars = typeof placeholdersOrNumber === "object" ? placeholdersOrNumber : void 0;
    const number = typeof optionsOrNumber === "number" ? optionsOrNumber : typeof placeholdersOrNumber === "number" ? placeholdersOrNumber : void 0;
    const allOptions = {
      // defaults
      escape: true,
      sanitize: true,
      // overwrite with user config
      ...typeof options === "object" ? options : typeof optionsOrNumber === "object" ? optionsOrNumber : {}
    };
    const identity = (value) => value;
    const optSanitize = (allOptions.sanitize ? purify.sanitize : identity) || identity;
    const optEscape = allOptions.escape ? import_escape_html.default : identity;
    const isValidReplacement = (value) => typeof value === "string" || typeof value === "number";
    const _build = (text22, vars2, number2) => {
      return text22.replace(/%n/g, "" + number2).replace(/{([^{}]*)}/g, (match, key) => {
        if (vars2 === void 0 || !(key in vars2)) {
          return optEscape(match);
        }
        const replacement = vars2[key];
        if (isValidReplacement(replacement)) {
          return optEscape(`${replacement}`);
        } else if (typeof replacement === "object" && isValidReplacement(replacement.value)) {
          const escape = replacement.escape !== false ? import_escape_html.default : identity;
          return escape(`${replacement.value}`);
        } else {
          return optEscape(match);
        }
      });
    };
    const bundle = options?.bundle ?? getAppTranslations(app);
    let translation = bundle.translations[text2] || text2;
    translation = Array.isArray(translation) ? translation[0] : translation;
    if (typeof vars === "object" || number !== void 0) {
      return optSanitize(_build(
        translation,
        vars,
        number
      ));
    } else {
      return optSanitize(translation);
    }
  }

  // node_modules/@nextcloud/files/dist/index.mjs
  var FilesRegistry = class extends e {
  };
  function getRegistry() {
    var _a2;
    (_a2 = scopedGlobals).registry ?? (_a2.registry = new FilesRegistry());
    return scopedGlobals.registry;
  }
  var DefaultType = Object.freeze({
    DEFAULT: "default",
    HIDDEN: "hidden"
  });
  function registerFileAction(action) {
    var _a2;
    validateAction$1(action);
    (_a2 = scopedGlobals).fileActions ?? (_a2.fileActions = /* @__PURE__ */ new Map());
    if (scopedGlobals.fileActions.has(action.id)) {
      logger.error(`FileAction ${action.id} already registered`, { action });
      return;
    }
    scopedGlobals.fileActions.set(action.id, action);
    getRegistry().dispatchTypedEvent("register:action", new CustomEvent("register:action", { detail: action }));
  }
  function validateAction$1(action) {
    if (!action.id || typeof action.id !== "string") {
      throw new Error("Invalid id");
    }
    if (!action.displayName || typeof action.displayName !== "function") {
      throw new Error("Invalid displayName function");
    }
    if ("title" in action && typeof action.title !== "function") {
      throw new Error("Invalid title function");
    }
    if (!action.iconSvgInline || typeof action.iconSvgInline !== "function") {
      throw new Error("Invalid iconSvgInline function");
    }
    if (!action.exec || typeof action.exec !== "function") {
      throw new Error("Invalid exec function");
    }
    if ("enabled" in action && typeof action.enabled !== "function") {
      throw new Error("Invalid enabled function");
    }
    if ("execBatch" in action && typeof action.execBatch !== "function") {
      throw new Error("Invalid execBatch function");
    }
    if ("order" in action && typeof action.order !== "number") {
      throw new Error("Invalid order");
    }
    if (action.destructive !== void 0 && typeof action.destructive !== "boolean") {
      throw new Error("Invalid destructive flag");
    }
    if ("parent" in action && typeof action.parent !== "string") {
      throw new Error("Invalid parent");
    }
    if (action.default && !Object.values(DefaultType).includes(action.default)) {
      throw new Error("Invalid default");
    }
    if ("inline" in action && typeof action.inline !== "function") {
      throw new Error("Invalid inline function");
    }
    if ("renderInline" in action && typeof action.renderInline !== "function") {
      throw new Error("Invalid renderInline function");
    }
    if ("hotkey" in action && action.hotkey !== void 0) {
      if (typeof action.hotkey !== "object") {
        throw new Error("Invalid hotkey configuration");
      }
      if (typeof action.hotkey.key !== "string" || !action.hotkey.key) {
        throw new Error("Missing or invalid hotkey key");
      }
      if (typeof action.hotkey.description !== "string" || !action.hotkey.description) {
        throw new Error("Missing or invalid hotkey description");
      }
    }
  }
  var NewMenuEntryCategory = Object.freeze({
    /**
     * For actions where the user is intended to upload from their device
     */
    UploadFromDevice: 0,
    /**
     * For actions that create new nodes on the server without uploading
     */
    CreateNew: 1,
    /**
     * For everything not matching the other categories
     */
    Other: 2
  });
  var InvalidFilenameErrorReason = Object.freeze({
    ReservedName: "reserved name",
    Character: "character",
    Extension: "extension"
  });
  var FilesSortingMode = Object.freeze({
    Name: "basename",
    Modified: "mtime",
    Size: "size"
  });

  // node_modules/axios/lib/helpers/bind.js
  function bind(fn, thisArg) {
    return function wrap() {
      return fn.apply(thisArg, arguments);
    };
  }

  // node_modules/axios/lib/utils.js
  var { toString } = Object.prototype;
  var { getPrototypeOf: getPrototypeOf2 } = Object;
  var { iterator, toStringTag } = Symbol;
  var hasOwnProperty = (({ hasOwnProperty: hasOwnProperty2 }) => (obj, prop) => hasOwnProperty2.call(obj, prop))(Object.prototype);
  var isUnsafeObjectKey = (prop) => typeof prop === "string" && (prop === "__proto__" || prop === "constructor" || prop === "prototype");
  var isPrototypeBoundary = (obj, prototype2, source) => obj === Object.prototype || !source && prototype2 === null;
  var isSafeAndFullyMutable = (obj) => {
    if (!Object.isExtensible(obj)) {
      return false;
    }
    const props = Object.getOwnPropertyNames(obj);
    if (Object.getOwnPropertySymbols) {
      props.push(...Object.getOwnPropertySymbols(obj));
    }
    return props.every((prop) => {
      if (isUnsafeObjectKey(prop)) {
        return false;
      }
      const descriptor = Object.getOwnPropertyDescriptor(obj, prop);
      return !!descriptor && descriptor.configurable && descriptor.writable === true;
    });
  };
  var hasOwnInPrototypeChain = (thing, prop) => {
    let obj = thing;
    const seen = [];
    while (obj != null) {
      if (seen.indexOf(obj) !== -1) {
        return false;
      }
      seen.push(obj);
      const prototype2 = getPrototypeOf2(obj);
      if (isPrototypeBoundary(obj, prototype2, obj === thing)) {
        return false;
      }
      if (hasOwnProperty(obj, prop)) {
        return true;
      }
      obj = prototype2;
    }
    return false;
  };
  var getSafeProp = (obj, prop) => obj != null && hasOwnInPrototypeChain(obj, prop) ? obj[prop] : void 0;
  var toSafeFlatObject = (thing) => {
    if (thing == null || typeof thing !== "object" && typeof thing !== "function") {
      return thing;
    }
    const sourcePrototype = getPrototypeOf2(thing);
    if (sourcePrototype === null && isSafeAndFullyMutable(thing)) {
      return thing;
    }
    const result = /* @__PURE__ */ Object.create(null);
    const merged = /* @__PURE__ */ Object.create(null);
    const seen = [];
    let current = thing;
    while (current != null) {
      if (seen.indexOf(current) !== -1) {
        break;
      }
      seen.push(current);
      const prototype2 = current === thing ? sourcePrototype : getPrototypeOf2(current);
      if (isPrototypeBoundary(current, prototype2, current === thing)) {
        break;
      }
      const props = Object.getOwnPropertyNames(current);
      if (Object.getOwnPropertySymbols) {
        props.push(...Object.getOwnPropertySymbols(current));
      }
      for (const prop of props) {
        if (isUnsafeObjectKey(prop)) {
          continue;
        }
        if (!hasOwnProperty(merged, prop)) {
          result[prop] = thing[prop];
          merged[prop] = true;
        }
      }
      current = prototype2;
    }
    return result;
  };
  var kindOf = /* @__PURE__ */ ((cache) => (thing) => {
    const str = toString.call(thing);
    return cache[str] || (cache[str] = str.slice(8, -1).toLowerCase());
  })(/* @__PURE__ */ Object.create(null));
  var kindOfTest = (type) => {
    type = type.toLowerCase();
    return (thing) => kindOf(thing) === type;
  };
  var typeOfTest = (type) => (thing) => typeof thing === type;
  var { isArray } = Array;
  var isUndefined = typeOfTest("undefined");
  function isBuffer(val) {
    return val !== null && !isUndefined(val) && val.constructor !== null && !isUndefined(val.constructor) && isFunction(val.constructor.isBuffer) && val.constructor.isBuffer(val);
  }
  var isArrayBuffer = kindOfTest("ArrayBuffer");
  function isArrayBufferView(val) {
    let result;
    if (typeof ArrayBuffer !== "undefined" && ArrayBuffer.isView) {
      result = ArrayBuffer.isView(val);
    } else {
      result = val && val.buffer && isArrayBuffer(val.buffer);
    }
    return result;
  }
  var isString = typeOfTest("string");
  var isFunction = typeOfTest("function");
  var isNumber = typeOfTest("number");
  var isObject = (thing) => thing !== null && typeof thing === "object";
  var isBoolean = (thing) => thing === true || thing === false;
  var isPlainObject = (val) => {
    if (!isObject(val)) {
      return false;
    }
    const prototype2 = getPrototypeOf2(val);
    return (prototype2 === null || prototype2 === Object.prototype || getPrototypeOf2(prototype2) === null) && // Treat safe own/inherited Symbol.toStringTag or Symbol.iterator members as
    // evidence the value is tagged/iterable, while ignoring members reachable
    // only through shared or terminal prototype boundaries.
    !hasOwnInPrototypeChain(val, toStringTag) && !hasOwnInPrototypeChain(val, iterator);
  };
  var isEmptyObject = (val) => {
    if (!isObject(val) || isBuffer(val)) {
      return false;
    }
    try {
      return Object.keys(val).length === 0 && Object.getPrototypeOf(val) === Object.prototype;
    } catch (e2) {
      return false;
    }
  };
  var isDate = kindOfTest("Date");
  var isFile = kindOfTest("File");
  var isReactNativeBlob = (value) => {
    return !!(value && typeof value.uri !== "undefined");
  };
  var isReactNative = (formData) => formData && typeof formData.getParts !== "undefined";
  var isBlob = kindOfTest("Blob");
  var isFileList = kindOfTest("FileList");
  var isSet = kindOfTest("Set");
  var isStream = (val) => isObject(val) && isFunction(val.pipe);
  function getGlobal3() {
    if (typeof globalThis !== "undefined") return globalThis;
    if (typeof self !== "undefined") return self;
    if (typeof window !== "undefined") return window;
    if (typeof global !== "undefined") return global;
    return {};
  }
  var G = getGlobal3();
  var FormDataCtor = typeof G.FormData !== "undefined" ? G.FormData : void 0;
  var isFormData = (thing) => {
    if (!thing) return false;
    if (FormDataCtor && thing instanceof FormDataCtor) return true;
    const proto = getPrototypeOf2(thing);
    if (!proto || proto === Object.prototype) return false;
    if (!isFunction(thing.append)) return false;
    const kind = kindOf(thing);
    return kind === "formdata" || // detect form-data instance
    kind === "object" && isFunction(thing.toString) && thing.toString() === "[object FormData]";
  };
  var isURLSearchParams = kindOfTest("URLSearchParams");
  var [isReadableStream, isRequest, isResponse, isHeaders] = [
    "ReadableStream",
    "Request",
    "Response",
    "Headers"
  ].map(kindOfTest);
  var trim = (str) => {
    return str.trim ? str.trim() : str.replace(/^[\s\uFEFF\xA0]+|[\s\uFEFF\xA0]+$/g, "");
  };
  function forEach(obj, fn, { allOwnKeys = false } = {}) {
    if (obj === null || typeof obj === "undefined") {
      return;
    }
    let i;
    let l;
    if (typeof obj !== "object") {
      obj = [obj];
    }
    if (isArray(obj)) {
      for (i = 0, l = obj.length; i < l; i++) {
        fn.call(null, obj[i], i, obj);
      }
    } else {
      if (isBuffer(obj)) {
        return;
      }
      const keys = allOwnKeys ? Object.getOwnPropertyNames(obj) : Object.keys(obj);
      const len = keys.length;
      let key;
      for (i = 0; i < len; i++) {
        key = keys[i];
        fn.call(null, obj[key], key, obj);
      }
    }
  }
  function findKey(obj, key) {
    if (isBuffer(obj)) {
      return null;
    }
    key = key.toLowerCase();
    const keys = Object.keys(obj);
    let i = keys.length;
    let _key;
    while (i-- > 0) {
      _key = keys[i];
      if (key === _key.toLowerCase()) {
        return _key;
      }
    }
    return null;
  }
  var _global = (() => {
    if (typeof globalThis !== "undefined") return globalThis;
    return typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : global;
  })();
  var isContextDefined = (context) => !isUndefined(context) && context !== _global;
  function merge(...objs) {
    const { caseless, skipUndefined } = isContextDefined(this) && this || {};
    const result = {};
    const assignValue = (val, key) => {
      if (key === "__proto__" || key === "constructor" || key === "prototype") {
        return;
      }
      const targetKey = caseless && typeof key === "string" && findKey(result, key) || key;
      const existing = hasOwnProperty(result, targetKey) ? result[targetKey] : void 0;
      if (isPlainObject(existing) && isPlainObject(val)) {
        result[targetKey] = merge(existing, val);
      } else if (isPlainObject(val)) {
        result[targetKey] = merge({}, val);
      } else if (isArray(val)) {
        result[targetKey] = val.slice();
      } else if (!skipUndefined || !isUndefined(val)) {
        result[targetKey] = val;
      }
    };
    for (let i = 0, l = objs.length; i < l; i++) {
      const source = objs[i];
      if (!source || isBuffer(source)) {
        continue;
      }
      forEach(source, assignValue);
      if (typeof source !== "object" || isArray(source)) {
        continue;
      }
      const symbols = Object.getOwnPropertySymbols(source);
      for (let j = 0; j < symbols.length; j++) {
        const symbol = symbols[j];
        if (propertyIsEnumerable.call(source, symbol)) {
          assignValue(source[symbol], symbol);
        }
      }
    }
    return result;
  }
  var extend = (a, b, thisArg, { allOwnKeys } = {}) => {
    forEach(
      b,
      (val, key) => {
        if (thisArg && isFunction(val)) {
          Object.defineProperty(a, key, {
            // Null-proto descriptor so a polluted Object.prototype.get cannot
            // hijack defineProperty's accessor-vs-data resolution.
            __proto__: null,
            value: bind(val, thisArg),
            writable: true,
            enumerable: true,
            configurable: true
          });
        } else {
          Object.defineProperty(a, key, {
            __proto__: null,
            value: val,
            writable: true,
            enumerable: true,
            configurable: true
          });
        }
      },
      { allOwnKeys }
    );
    return a;
  };
  var stripBOM = (content) => {
    if (content.charCodeAt(0) === 65279) {
      content = content.slice(1);
    }
    return content;
  };
  var inherits = (constructor, superConstructor, props, descriptors) => {
    constructor.prototype = Object.create(superConstructor.prototype, descriptors);
    Object.defineProperty(constructor.prototype, "constructor", {
      __proto__: null,
      value: constructor,
      writable: true,
      enumerable: false,
      configurable: true
    });
    Object.defineProperty(constructor, "super", {
      __proto__: null,
      value: superConstructor.prototype
    });
    props && Object.assign(constructor.prototype, props);
  };
  var toFlatObject = (sourceObj, destObj, filter2, propFilter) => {
    let props;
    let i;
    let prop;
    const merged = {};
    destObj = destObj || {};
    if (sourceObj == null) return destObj;
    do {
      props = Object.getOwnPropertyNames(sourceObj);
      i = props.length;
      while (i-- > 0) {
        prop = props[i];
        if ((!propFilter || propFilter(prop, sourceObj, destObj)) && !merged[prop]) {
          destObj[prop] = sourceObj[prop];
          merged[prop] = true;
        }
      }
      sourceObj = filter2 !== false && getPrototypeOf2(sourceObj);
    } while (sourceObj && (!filter2 || filter2(sourceObj, destObj)) && sourceObj !== Object.prototype);
    return destObj;
  };
  var endsWith = (str, searchString, position) => {
    str = String(str);
    if (position === void 0 || position > str.length) {
      position = str.length;
    }
    position -= searchString.length;
    const lastIndex = str.indexOf(searchString, position);
    return lastIndex !== -1 && lastIndex === position;
  };
  var toArray = (thing) => {
    if (!thing) return null;
    if (isArray(thing)) return thing;
    let i = thing.length;
    if (!isNumber(i)) return null;
    const arr = new Array(i);
    while (i-- > 0) {
      arr[i] = thing[i];
    }
    return arr;
  };
  var isTypedArray = /* @__PURE__ */ ((TypedArray) => {
    return (thing) => {
      return TypedArray && thing instanceof TypedArray;
    };
  })(typeof Uint8Array !== "undefined" && getPrototypeOf2(Uint8Array));
  var forEachEntry = (obj, fn) => {
    const generator = obj && obj[iterator];
    const _iterator = generator.call(obj);
    let result;
    while ((result = _iterator.next()) && !result.done) {
      const pair = result.value;
      fn.call(obj, pair[0], pair[1]);
    }
  };
  var matchAll = (regExp, str) => {
    let matches;
    const arr = [];
    while ((matches = regExp.exec(str)) !== null) {
      arr.push(matches);
    }
    return arr;
  };
  var isHTMLForm = kindOfTest("HTMLFormElement");
  var toCamelCase = (str) => {
    return str.toLowerCase().replace(/[-_\s]([a-z\d])(\w*)/g, function replacer(m, p1, p2) {
      return p1.toUpperCase() + p2;
    });
  };
  var { propertyIsEnumerable } = Object.prototype;
  var isRegExp = kindOfTest("RegExp");
  var reduceDescriptors = (obj, reducer) => {
    const descriptors = Object.getOwnPropertyDescriptors(obj);
    const reducedDescriptors = {};
    forEach(descriptors, (descriptor, name) => {
      let ret;
      if ((ret = reducer(descriptor, name, obj)) !== false) {
        reducedDescriptors[name] = ret || descriptor;
      }
    });
    Object.defineProperties(obj, reducedDescriptors);
  };
  var freezeMethods = (obj) => {
    reduceDescriptors(obj, (descriptor, name) => {
      if (isFunction(obj) && ["arguments", "caller", "callee"].includes(name)) {
        return false;
      }
      const value = obj[name];
      if (!isFunction(value)) return;
      descriptor.enumerable = false;
      if ("writable" in descriptor) {
        descriptor.writable = false;
        return;
      }
      if (!descriptor.set) {
        descriptor.set = () => {
          throw Error("Can not rewrite read-only method '" + name + "'");
        };
      }
    });
  };
  var toObjectSet = (arrayOrString, delimiter) => {
    const obj = {};
    const define = (arr) => {
      arr.forEach((value) => {
        obj[value] = true;
      });
    };
    isArray(arrayOrString) ? define(arrayOrString) : define(String(arrayOrString).split(delimiter));
    return obj;
  };
  var noop = () => {
  };
  var toFiniteNumber = (value, defaultValue) => {
    return value != null && Number.isFinite(value = +value) ? value : defaultValue;
  };
  function isSpecCompliantForm(thing) {
    return !!(thing && isFunction(thing.append) && thing[toStringTag] === "FormData" && thing[iterator]);
  }
  var toJSONObject = (obj) => {
    const visited = /* @__PURE__ */ new WeakSet();
    const visit = (source) => {
      if (isObject(source)) {
        if (visited.has(source)) {
          return;
        }
        if (isBuffer(source)) {
          return source;
        }
        if (!("toJSON" in source)) {
          visited.add(source);
          let target;
          if (isSet(source)) {
            target = [];
            for (const value of source) {
              const reducedValue = visit(value);
              !isUndefined(reducedValue) && target.push(reducedValue);
            }
          } else {
            target = isArray(source) ? [] : {};
            forEach(source, (value, key) => {
              const reducedValue = visit(value);
              !isUndefined(reducedValue) && (target[key] = reducedValue);
            });
          }
          visited.delete(source);
          return target;
        }
      }
      return source;
    };
    return visit(obj);
  };
  var isAsyncFn = kindOfTest("AsyncFunction");
  var isThenable = (thing) => thing && (isObject(thing) || isFunction(thing)) && isFunction(thing.then) && isFunction(thing.catch);
  var _setImmediate = ((setImmediateSupported, postMessageSupported) => {
    if (setImmediateSupported) {
      return setImmediate;
    }
    return postMessageSupported ? ((token, callbacks) => {
      _global.addEventListener(
        "message",
        ({ source, data }) => {
          if (source === _global && data === token) {
            callbacks.length && callbacks.shift()();
          }
        },
        false
      );
      return (cb) => {
        callbacks.push(cb);
        _global.postMessage(token, "*");
      };
    })(`axios@${Math.random()}`, []) : (cb) => setTimeout(cb);
  })(typeof setImmediate === "function", isFunction(_global.postMessage));
  var asap = typeof queueMicrotask !== "undefined" ? queueMicrotask.bind(_global) : typeof process !== "undefined" && process.nextTick || _setImmediate;
  var isIterable = (thing) => thing != null && isFunction(thing[iterator]);
  var isSafeIterable = (thing) => thing != null && hasOwnInPrototypeChain(thing, iterator) && isIterable(thing);
  var utils_default = {
    isArray,
    isArrayBuffer,
    isBuffer,
    isFormData,
    isArrayBufferView,
    isString,
    isNumber,
    isBoolean,
    isObject,
    isPlainObject,
    isEmptyObject,
    isReadableStream,
    isRequest,
    isResponse,
    isHeaders,
    isUndefined,
    isDate,
    isFile,
    isReactNativeBlob,
    isReactNative,
    isBlob,
    isRegExp,
    isFunction,
    isStream,
    isURLSearchParams,
    isTypedArray,
    isFileList,
    forEach,
    merge,
    extend,
    trim,
    stripBOM,
    inherits,
    toFlatObject,
    kindOf,
    kindOfTest,
    endsWith,
    toArray,
    forEachEntry,
    matchAll,
    isHTMLForm,
    hasOwnProperty,
    hasOwnProp: hasOwnProperty,
    // an alias to avoid ESLint no-prototype-builtins detection
    hasOwnInPrototypeChain,
    getSafeProp,
    toSafeFlatObject,
    reduceDescriptors,
    freezeMethods,
    toObjectSet,
    toCamelCase,
    noop,
    toFiniteNumber,
    findKey,
    global: _global,
    isContextDefined,
    isSpecCompliantForm,
    toJSONObject,
    isAsyncFn,
    isThenable,
    setImmediate: _setImmediate,
    asap,
    isIterable,
    isSafeIterable
  };

  // node_modules/axios/lib/helpers/parseHeaders.js
  var ignoreDuplicateOf = utils_default.toObjectSet([
    "age",
    "authorization",
    "content-length",
    "content-type",
    "etag",
    "expires",
    "from",
    "host",
    "if-modified-since",
    "if-unmodified-since",
    "last-modified",
    "location",
    "max-forwards",
    "proxy-authorization",
    "referer",
    "retry-after",
    "user-agent"
  ]);
  var parseHeaders_default = (rawHeaders) => {
    const parsed = {};
    let key;
    let val;
    let i;
    rawHeaders && rawHeaders.split("\n").forEach(function parser(line) {
      i = line.indexOf(":");
      key = line.substring(0, i).trim().toLowerCase();
      val = line.substring(i + 1).trim();
      const hasKey = utils_default.hasOwnProp(parsed, key);
      if (!key || hasKey && utils_default.hasOwnProp(ignoreDuplicateOf, key)) {
        return;
      }
      if (key === "set-cookie") {
        if (hasKey) {
          parsed[key].push(val);
        } else {
          parsed[key] = [val];
        }
      } else {
        parsed[key] = hasKey ? parsed[key] + ", " + val : val;
      }
    });
    return parsed;
  };

  // node_modules/axios/lib/helpers/sanitizeHeaderValue.js
  function trimSPorHTAB(str) {
    let start = 0;
    let end = str.length;
    while (start < end) {
      const code = str.charCodeAt(start);
      if (code !== 9 && code !== 32) {
        break;
      }
      start += 1;
    }
    while (end > start) {
      const code = str.charCodeAt(end - 1);
      if (code !== 9 && code !== 32) {
        break;
      }
      end -= 1;
    }
    return start === 0 && end === str.length ? str : str.slice(start, end);
  }
  var INVALID_UNICODE_HEADER_VALUE_CHARS = new RegExp("[\\u0000-\\u0008\\u000a-\\u001f\\u007f]+", "g");
  var INVALID_BYTE_STRING_HEADER_VALUE_CHARS = new RegExp("[^\\u0009\\u0020-\\u007e\\u0080-\\u00ff]+", "g");
  function sanitizeValue(value, invalidChars) {
    if (utils_default.isArray(value)) {
      return value.map((item) => sanitizeValue(item, invalidChars));
    }
    return trimSPorHTAB(String(value).replace(invalidChars, ""));
  }
  var sanitizeHeaderValue = (value) => sanitizeValue(value, INVALID_UNICODE_HEADER_VALUE_CHARS);
  var sanitizeByteStringHeaderValue = (value) => sanitizeValue(value, INVALID_BYTE_STRING_HEADER_VALUE_CHARS);
  function toByteStringHeaderObject(headers) {
    const byteStringHeaders = /* @__PURE__ */ Object.create(null);
    utils_default.forEach(headers.toJSON(), (value, header) => {
      byteStringHeaders[header] = sanitizeByteStringHeaderValue(value);
    });
    return byteStringHeaders;
  }

  // node_modules/axios/lib/core/AxiosHeaders.js
  var $internals = Symbol("internals");
  function normalizeHeader(header) {
    return header && String(header).trim().toLowerCase();
  }
  function normalizeValue(value) {
    if (value === false || value == null) {
      return value;
    }
    return utils_default.isArray(value) ? value.map(normalizeValue) : sanitizeHeaderValue(String(value));
  }
  function parseTokens(str) {
    const tokens = /* @__PURE__ */ Object.create(null);
    const tokensRE = /([^\s,;=]+)\s*(?:=\s*([^,;]+))?/g;
    let match;
    while (match = tokensRE.exec(str)) {
      tokens[match[1]] = match[2];
    }
    return tokens;
  }
  var parameterNameRE = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/;
  function trimOWS(value) {
    let start = 0;
    let end = value.length;
    while (start < end) {
      const code = value.charCodeAt(start);
      if (code !== 9 && code !== 32) {
        break;
      }
      start += 1;
    }
    while (end > start) {
      const code = value.charCodeAt(end - 1);
      if (code !== 9 && code !== 32) {
        break;
      }
      end -= 1;
    }
    return start === 0 && end === value.length ? value : value.slice(start, end);
  }
  function decodeQuotedString(value) {
    const last = value.length - 1;
    if (last < 1 || value.charCodeAt(0) !== 34 || value.charCodeAt(last) !== 34) {
      return value;
    }
    let decoded = "";
    for (let i = 1; i < last; i++) {
      const code = value.charCodeAt(i);
      if (code === 34) {
        return value;
      }
      if (code === 92) {
        i += 1;
        if (i >= last) {
          return value;
        }
      }
      decoded += value[i];
    }
    return decoded;
  }
  function parseParameters(value) {
    const parameters = /* @__PURE__ */ Object.create(null);
    const str = String(value);
    let start = 0;
    let quoted = false;
    let escaped = false;
    function parseParameter(end) {
      const part = trimOWS(str.slice(start, end));
      const equals = part.indexOf("=");
      if (equals < 1) {
        return;
      }
      const name = trimOWS(part.slice(0, equals));
      if (!parameterNameRE.test(name)) {
        return;
      }
      const normalizedName = name.toLowerCase();
      if (normalizedName === "__proto__" || normalizedName === "constructor" || normalizedName === "prototype") {
        return;
      }
      const parameterValue = trimOWS(part.slice(equals + 1));
      parameters[normalizedName] = decodeQuotedString(parameterValue);
    }
    for (let i = 0; i < str.length; i++) {
      const code = str.charCodeAt(i);
      if (quoted) {
        if (escaped) {
          escaped = false;
        } else if (code === 92) {
          escaped = true;
        } else if (code === 34) {
          quoted = false;
        }
      } else if (code === 34) {
        quoted = true;
      } else if (code === 44 || code === 59) {
        parseParameter(i);
        start = i + 1;
      }
    }
    parseParameter(str.length);
    return parameters;
  }
  var isValidHeaderName = (str) => /^[-_a-zA-Z0-9^`|~,!#$%&'*+.]+$/.test(str.trim());
  function matchHeaderValue(context, value, header, filter2, isHeaderNameFilter) {
    if (utils_default.isFunction(filter2)) {
      return filter2.call(this, value, header);
    }
    if (isHeaderNameFilter) {
      value = header;
    }
    if (!utils_default.isString(value)) return;
    if (utils_default.isString(filter2)) {
      return value.indexOf(filter2) !== -1;
    }
    if (utils_default.isRegExp(filter2)) {
      return filter2.test(value);
    }
  }
  function formatHeader(header) {
    return header.trim().toLowerCase().replace(/([a-z\d])(\w*)/g, (w, char, str) => {
      return char.toUpperCase() + str;
    });
  }
  function buildAccessors(obj, header) {
    const accessorName = utils_default.toCamelCase(" " + header);
    ["get", "set", "has"].forEach((methodName) => {
      Object.defineProperty(obj, methodName + accessorName, {
        // Null-proto descriptor so a polluted Object.prototype.get cannot turn
        // this data descriptor into an accessor descriptor on the way in.
        __proto__: null,
        value: function(arg1, arg2, arg3) {
          return this[methodName].call(this, header, arg1, arg2, arg3);
        },
        configurable: true
      });
    });
  }
  var AxiosHeaders = class {
    constructor(headers) {
      headers && this.set(headers);
    }
    set(header, valueOrRewrite, rewrite) {
      const self2 = this;
      function setHeader(_value, _header, _rewrite) {
        const lHeader = normalizeHeader(_header);
        if (!lHeader) {
          return;
        }
        const key = utils_default.findKey(self2, lHeader);
        if (!key || self2[key] === void 0 || _rewrite === true || _rewrite === void 0 && self2[key] !== false) {
          self2[key || _header] = normalizeValue(_value);
        }
      }
      const setHeaders = (headers, _rewrite) => utils_default.forEach(headers, (_value, _header) => setHeader(_value, _header, _rewrite));
      if (utils_default.isPlainObject(header) || header instanceof this.constructor) {
        setHeaders(header, valueOrRewrite);
      } else if (utils_default.isString(header) && (header = header.trim()) && !isValidHeaderName(header)) {
        setHeaders(parseHeaders_default(header), valueOrRewrite);
      } else if (utils_default.isObject(header) && utils_default.isSafeIterable(header)) {
        let obj = /* @__PURE__ */ Object.create(null), dest, key;
        for (const entry of header) {
          if (!utils_default.isArray(entry)) {
            throw new TypeError("Object iterator must return a key-value pair");
          }
          key = entry[0];
          if (utils_default.hasOwnProp(obj, key)) {
            dest = obj[key];
            obj[key] = utils_default.isArray(dest) ? [...dest, entry[1]] : [dest, entry[1]];
          } else {
            obj[key] = entry[1];
          }
        }
        setHeaders(obj, valueOrRewrite);
      } else {
        header != null && setHeader(valueOrRewrite, header, rewrite);
      }
      return this;
    }
    get(header, parser) {
      header = normalizeHeader(header);
      if (header) {
        const key = utils_default.findKey(this, header);
        if (key) {
          const value = this[key];
          if (!parser) {
            return value;
          }
          if (parser === true) {
            return parseTokens(value);
          }
          if (utils_default.isFunction(parser)) {
            return parser.call(this, value, key);
          }
          if (utils_default.isRegExp(parser)) {
            return parser.exec(value);
          }
          throw new TypeError("parser must be boolean|regexp|function");
        }
      }
    }
    has(header, matcher) {
      header = normalizeHeader(header);
      if (header) {
        const key = utils_default.findKey(this, header);
        return !!(key && this[key] !== void 0 && (!matcher || matchHeaderValue(this, this[key], key, matcher)));
      }
      return false;
    }
    delete(header, matcher) {
      const self2 = this;
      let deleted = false;
      function deleteHeader(_header) {
        _header = normalizeHeader(_header);
        if (_header) {
          const key = utils_default.findKey(self2, _header);
          if (key && (!matcher || matchHeaderValue(self2, self2[key], key, matcher))) {
            delete self2[key];
            deleted = true;
          }
        }
      }
      if (utils_default.isArray(header)) {
        header.forEach(deleteHeader);
      } else {
        deleteHeader(header);
      }
      return deleted;
    }
    clear(matcher) {
      const keys = Object.keys(this);
      let i = keys.length;
      let deleted = false;
      while (i--) {
        const key = keys[i];
        if (!matcher || matchHeaderValue(this, this[key], key, matcher, true)) {
          delete this[key];
          deleted = true;
        }
      }
      return deleted;
    }
    normalize(format) {
      const self2 = this;
      const headers = {};
      utils_default.forEach(this, (value, header) => {
        const key = utils_default.findKey(headers, header);
        if (key) {
          self2[key] = normalizeValue(value);
          delete self2[header];
          return;
        }
        const normalized = format ? formatHeader(header) : String(header).trim();
        if (normalized !== header) {
          delete self2[header];
        }
        self2[normalized] = normalizeValue(value);
        headers[normalized] = true;
      });
      return this;
    }
    concat(...targets) {
      return this.constructor.concat(this, ...targets);
    }
    toJSON(asStrings) {
      const obj = /* @__PURE__ */ Object.create(null);
      utils_default.forEach(this, (value, header) => {
        value != null && value !== false && (obj[header] = asStrings && utils_default.isArray(value) ? value.join(", ") : value);
      });
      return obj;
    }
    [Symbol.iterator]() {
      return Object.entries(this.toJSON())[Symbol.iterator]();
    }
    toString() {
      return Object.entries(this.toJSON()).map(([header, value]) => header + ": " + value).join("\n");
    }
    getSetCookie() {
      const value = this.get("set-cookie");
      return utils_default.isArray(value) ? value : value == null || value === false ? [] : [value];
    }
    get [Symbol.toStringTag]() {
      return "AxiosHeaders";
    }
    static from(thing) {
      return thing instanceof this ? thing : new this(thing);
    }
    static parseParameters(value) {
      return parseParameters(value);
    }
    static concat(first, ...targets) {
      const computed = new this(first);
      targets.forEach((target) => computed.set(target));
      return computed;
    }
    static accessor(header) {
      const internals = this[$internals] = this[$internals] = {
        accessors: {}
      };
      const accessors = internals.accessors;
      const prototype2 = this.prototype;
      function defineAccessor(_header) {
        const lHeader = normalizeHeader(_header);
        if (!accessors[lHeader]) {
          buildAccessors(prototype2, _header);
          accessors[lHeader] = true;
        }
      }
      utils_default.isArray(header) ? header.forEach(defineAccessor) : defineAccessor(header);
      return this;
    }
  };
  AxiosHeaders.accessor([
    "Content-Type",
    "Content-Length",
    "Accept",
    "Accept-Encoding",
    "User-Agent",
    "Authorization"
  ]);
  utils_default.reduceDescriptors(AxiosHeaders.prototype, ({ value }, key) => {
    let mapped = key[0].toUpperCase() + key.slice(1);
    return {
      get: () => value,
      set(headerValue) {
        this[mapped] = headerValue;
      }
    };
  });
  utils_default.freezeMethods(AxiosHeaders);
  var AxiosHeaders_default = AxiosHeaders;

  // node_modules/axios/lib/core/AxiosError.js
  var REDACTED = "[REDACTED ****]";
  function hasOwnOrPrototypeToJSON(source) {
    if (utils_default.hasOwnProp(source, "toJSON")) {
      return true;
    }
    let prototype2 = Object.getPrototypeOf(source);
    while (prototype2 && prototype2 !== Object.prototype) {
      if (utils_default.hasOwnProp(prototype2, "toJSON")) {
        return true;
      }
      prototype2 = Object.getPrototypeOf(prototype2);
    }
    return false;
  }
  function redactConfig(config, redactKeys) {
    const lowerKeys = new Set(redactKeys.map((k) => String(k).toLowerCase()));
    const seen = [];
    const visit = (source) => {
      if (source === null || typeof source !== "object") return source;
      if (utils_default.isBuffer(source)) return source;
      if (seen.indexOf(source) !== -1) return void 0;
      if (source instanceof AxiosHeaders_default) {
        source = source.toJSON();
      }
      seen.push(source);
      let result;
      if (utils_default.isArray(source)) {
        result = [];
        source.forEach((v, i) => {
          const reducedValue = visit(v);
          if (!utils_default.isUndefined(reducedValue)) {
            result[i] = reducedValue;
          }
        });
      } else {
        if (!utils_default.isPlainObject(source) && hasOwnOrPrototypeToJSON(source)) {
          seen.pop();
          return source;
        }
        result = /* @__PURE__ */ Object.create(null);
        for (const [key, value] of Object.entries(source)) {
          const reducedValue = lowerKeys.has(key.toLowerCase()) ? REDACTED : visit(value);
          if (!utils_default.isUndefined(reducedValue)) {
            result[key] = reducedValue;
          }
        }
      }
      seen.pop();
      return result;
    };
    return visit(config);
  }
  function stringifySafely(value) {
    try {
      return String(value);
    } catch (err) {
      return "";
    }
  }
  function aggregateErrorMessage(error) {
    const message = error.errors.map((entry) => {
      try {
        return entry && entry.message ? stringifySafely(entry.message) : stringifySafely(entry);
      } catch (err) {
        return "";
      }
    }).filter(Boolean).join("; ");
    return message || error.name || "AggregateError";
  }
  var AxiosError = class _AxiosError extends Error {
    static from(error, code, config, request, response, customProps) {
      let message = error.message;
      if (!message && utils_default.isArray(error.errors) && error.errors.length) {
        message = aggregateErrorMessage(error);
      }
      const axiosError = new _AxiosError(message, code || error.code, config, request, response);
      Object.defineProperty(axiosError, "cause", {
        __proto__: null,
        value: error,
        writable: true,
        enumerable: false,
        configurable: true
      });
      axiosError.name = error.name;
      if (error.status != null && axiosError.status == null) {
        axiosError.status = error.status;
      }
      customProps && Object.assign(axiosError, customProps);
      return axiosError;
    }
    /**
     * Create an Error with the specified message, config, error code, request and response.
     *
     * @param {string} message The error message.
     * @param {string} [code] The error code (for example, 'ECONNABORTED').
     * @param {Object} [config] The config.
     * @param {Object} [request] The request.
     * @param {Object} [response] The response.
     *
     * @returns {Error} The created error.
     */
    constructor(message, code, config, request, response) {
      super(message);
      Object.defineProperty(this, "message", {
        // Null-proto descriptor so a polluted Object.prototype.get cannot turn
        // this data descriptor into an accessor descriptor on the way in.
        __proto__: null,
        value: message,
        enumerable: true,
        writable: true,
        configurable: true
      });
      this.name = "AxiosError";
      this.isAxiosError = true;
      code && (this.code = code);
      config && (this.config = config);
      request && (this.request = request);
      if (response) {
        this.response = response;
        this.status = response.status;
      }
    }
    toJSON() {
      const config = this.config;
      const redactKeys = config && utils_default.hasOwnProp(config, "redact") ? config.redact : void 0;
      const serializedConfig = utils_default.isArray(redactKeys) && redactKeys.length > 0 ? redactConfig(config, redactKeys) : utils_default.toJSONObject(config);
      return {
        // Standard
        message: this.message,
        name: this.name,
        // Microsoft
        description: this.description,
        number: this.number,
        // Mozilla
        fileName: this.fileName,
        lineNumber: this.lineNumber,
        columnNumber: this.columnNumber,
        stack: this.stack,
        // Axios
        config: serializedConfig,
        code: this.code,
        status: this.status
      };
    }
  };
  AxiosError.ERR_BAD_OPTION_VALUE = "ERR_BAD_OPTION_VALUE";
  AxiosError.ERR_BAD_OPTION = "ERR_BAD_OPTION";
  AxiosError.ECONNABORTED = "ECONNABORTED";
  AxiosError.ETIMEDOUT = "ETIMEDOUT";
  AxiosError.ECONNREFUSED = "ECONNREFUSED";
  AxiosError.ERR_NETWORK = "ERR_NETWORK";
  AxiosError.ERR_FR_TOO_MANY_REDIRECTS = "ERR_FR_TOO_MANY_REDIRECTS";
  AxiosError.ERR_DEPRECATED = "ERR_DEPRECATED";
  AxiosError.ERR_BAD_RESPONSE = "ERR_BAD_RESPONSE";
  AxiosError.ERR_BAD_REQUEST = "ERR_BAD_REQUEST";
  AxiosError.ERR_CANCELED = "ERR_CANCELED";
  AxiosError.ERR_NOT_SUPPORT = "ERR_NOT_SUPPORT";
  AxiosError.ERR_INVALID_URL = "ERR_INVALID_URL";
  AxiosError.ERR_FORM_DATA_DEPTH_EXCEEDED = "ERR_FORM_DATA_DEPTH_EXCEEDED";
  var AxiosError_default = AxiosError;

  // node_modules/axios/lib/helpers/null.js
  var null_default = null;

  // node_modules/axios/lib/helpers/toFormData.js
  var DEFAULT_FORM_DATA_MAX_DEPTH = 100;
  function isVisitable(thing) {
    return utils_default.isPlainObject(thing) || utils_default.isArray(thing);
  }
  function removeBrackets(key) {
    return utils_default.endsWith(key, "[]") ? key.slice(0, -2) : key;
  }
  function renderKey(path, key, dots) {
    if (!path) return key;
    return path.concat(key).map(function each(token, i) {
      token = removeBrackets(token);
      return !dots && i ? "[" + token + "]" : token;
    }).join(dots ? "." : "");
  }
  function isFlatArray(arr) {
    return utils_default.isArray(arr) && !arr.some(isVisitable);
  }
  var predicates = utils_default.toFlatObject(utils_default, {}, null, function filter(prop) {
    return /^is[A-Z]/.test(prop);
  });
  function toFormData(obj, formData, options) {
    if (!utils_default.isObject(obj)) {
      throw new TypeError("target must be an object");
    }
    formData = formData || new (null_default || FormData)();
    const option = (name, fallback) => {
      const value = utils_default.getSafeProp(options, name);
      return utils_default.isUndefined(value) ? fallback : value;
    };
    const metaTokens = option("metaTokens", true);
    const visitor = option("visitor") || defaultVisitor;
    const dots = option("dots", false);
    const indexes = option("indexes", false);
    const _Blob = option("Blob") || typeof Blob !== "undefined" && Blob;
    const maxDepth = option("maxDepth", DEFAULT_FORM_DATA_MAX_DEPTH);
    const useBlob = _Blob && utils_default.isSpecCompliantForm(formData);
    const stack = [];
    if (!utils_default.isFunction(visitor)) {
      throw new TypeError("visitor must be a function");
    }
    function convertValue(value) {
      if (value === null) return "";
      if (utils_default.isDate(value)) {
        return value.toISOString();
      }
      if (utils_default.isBoolean(value)) {
        return value.toString();
      }
      if (!useBlob && utils_default.isBlob(value)) {
        throw new AxiosError_default("Blob is not supported. Use a Buffer instead.");
      }
      if (utils_default.isArrayBuffer(value) || utils_default.isTypedArray(value)) {
        if (useBlob && typeof _Blob === "function") {
          return new _Blob([value]);
        }
        if (null_default && null_default.isBufferAvailable()) {
          return null_default.from(value);
        }
        throw new AxiosError_default(
          "Blob is not supported. Use a Buffer instead.",
          AxiosError_default.ERR_NOT_SUPPORT
        );
      }
      return value;
    }
    function throwIfMaxDepthExceeded(depth) {
      if (depth > maxDepth) {
        throw new AxiosError_default(
          "Object is too deeply nested (" + depth + " levels). Max depth: " + maxDepth,
          AxiosError_default.ERR_FORM_DATA_DEPTH_EXCEEDED
        );
      }
    }
    function stringifyWithDepthLimit(value, depth) {
      if (maxDepth === Infinity) {
        return JSON.stringify(value);
      }
      const ancestors = [];
      return JSON.stringify(value, function limitDepth(_key, currentValue) {
        if (!utils_default.isObject(currentValue)) {
          return currentValue;
        }
        while (ancestors.length && ancestors[ancestors.length - 1] !== this) {
          ancestors.pop();
        }
        ancestors.push(currentValue);
        throwIfMaxDepthExceeded(depth + ancestors.length - 1);
        return currentValue;
      });
    }
    function defaultVisitor(value, key, path) {
      let arr = value;
      if (utils_default.isReactNative(formData) && utils_default.isReactNativeBlob(value)) {
        formData.append(renderKey(path, key, dots), convertValue(value));
        return false;
      }
      if (value && !path && typeof value === "object") {
        if (utils_default.endsWith(key, "{}")) {
          key = metaTokens ? key : key.slice(0, -2);
          value = stringifyWithDepthLimit(value, 1);
        } else if (utils_default.isArray(value) && isFlatArray(value) || (utils_default.isFileList(value) || utils_default.endsWith(key, "[]")) && (arr = utils_default.toArray(value))) {
          key = removeBrackets(key);
          arr.forEach(function each(el, index) {
            !(utils_default.isUndefined(el) || el === null) && formData.append(
              // eslint-disable-next-line no-nested-ternary
              indexes === true ? renderKey([key], index, dots) : indexes === null ? key : key + "[]",
              convertValue(el)
            );
          });
          return false;
        }
      }
      if (isVisitable(value)) {
        return true;
      }
      formData.append(renderKey(path, key, dots), convertValue(value));
      return false;
    }
    const exposedHelpers = Object.assign(predicates, {
      defaultVisitor,
      convertValue,
      isVisitable
    });
    function build(value, path, depth = 0) {
      if (utils_default.isUndefined(value)) return;
      throwIfMaxDepthExceeded(depth);
      if (stack.indexOf(value) !== -1) {
        throw new Error("Circular reference detected in " + path.join("."));
      }
      stack.push(value);
      utils_default.forEach(value, function each(el, key) {
        const result = !(utils_default.isUndefined(el) || el === null) && visitor.call(formData, el, utils_default.isString(key) ? key.trim() : key, path, exposedHelpers);
        if (result === true) {
          build(el, path ? path.concat(key) : [key], depth + 1);
        }
      });
      stack.pop();
    }
    if (!utils_default.isObject(obj)) {
      throw new TypeError("data must be an object");
    }
    build(obj);
    return formData;
  }
  var toFormData_default = toFormData;

  // node_modules/axios/lib/helpers/AxiosURLSearchParams.js
  function encode(str) {
    const charMap = {
      "!": "%21",
      "'": "%27",
      "(": "%28",
      ")": "%29",
      "~": "%7E",
      "%20": "+"
    };
    return encodeURIComponent(str).replace(/[!'()~]|%20/g, function replacer(match) {
      return charMap[match];
    });
  }
  function AxiosURLSearchParams(params, options) {
    this._pairs = [];
    params && toFormData_default(params, this, options);
  }
  var prototype = AxiosURLSearchParams.prototype;
  prototype.append = function append(name, value) {
    this._pairs.push([name, value]);
  };
  prototype.toString = function toString2(encoder) {
    const _encode = encoder ? (value) => encoder.call(this, value, encode) : encode;
    return this._pairs.map(function each(pair) {
      return _encode(pair[0]) + "=" + _encode(pair[1]);
    }, "").join("&");
  };
  var AxiosURLSearchParams_default = AxiosURLSearchParams;

  // node_modules/axios/lib/helpers/buildURL.js
  function encode2(val) {
    return encodeURIComponent(val).replace(/%3A/gi, ":").replace(/%24/g, "$").replace(/%2C/gi, ",").replace(/%20/g, "+");
  }
  function buildURL(url, params, options) {
    if (!params) {
      return url;
    }
    url = url || "";
    const _options = utils_default.isFunction(options) ? {
      serialize: options
    } : options;
    const _encode = utils_default.getSafeProp(_options, "encode") || encode2;
    const serializeFn = utils_default.getSafeProp(_options, "serialize");
    let serializedParams;
    if (serializeFn) {
      serializedParams = serializeFn(params, _options);
    } else {
      serializedParams = utils_default.isURLSearchParams(params) ? params.toString() : new AxiosURLSearchParams_default(params, _options).toString(_encode);
    }
    if (serializedParams) {
      const hashmarkIndex = url.indexOf("#");
      if (hashmarkIndex !== -1) {
        url = url.slice(0, hashmarkIndex);
      }
      url += (url.indexOf("?") === -1 ? "?" : "&") + serializedParams;
    }
    return url;
  }

  // node_modules/axios/lib/core/InterceptorManager.js
  var $internals2 = Symbol("internals");
  function countHandlers(handlers) {
    return handlers ? handlers.length : 0;
  }
  function trimHandlers(handlers) {
    if (!handlers) {
      return;
    }
    while (handlers.length && handlers[handlers.length - 1] === null) {
      handlers.pop();
    }
  }
  function syncHandlerEntries(manager, internals) {
    const handlers = manager.handlers;
    const length = countHandlers(handlers);
    if (handlers !== internals.handlersRef) {
      internals.handlersRef = handlers;
      internals.handlerEntries.clear();
    } else if (length !== internals.handlersLength) {
      if (!length) {
        internals.handlerEntries.clear();
      } else {
        internals.handlerEntries.forEach(function removeStaleEntry(entry, id) {
          if (handlers[entry.index] !== entry.handler) {
            internals.handlerEntries.delete(id);
          }
        });
      }
    }
    internals.handlersLength = length;
  }
  var InterceptorManager = class {
    constructor() {
      this.handlers = [];
      this[$internals2] = {
        handlersRef: this.handlers,
        handlersLength: this.handlers.length,
        handlerEntries: /* @__PURE__ */ new Map(),
        iterationDepth: 0,
        nextId: 0
      };
    }
    /**
     * Add a new interceptor to the stack
     *
     * @param {Function} fulfilled The function to handle `then` for a `Promise`
     * @param {Function} rejected The function to handle `reject` for a `Promise`
     * @param {Object} options The options for the interceptor, synchronous and runWhen
     *
     * @return {Number} An ID used to remove interceptor later
     */
    use(fulfilled, rejected, options) {
      const handler = {
        fulfilled,
        rejected,
        synchronous: options ? options.synchronous : false,
        runWhen: options ? options.runWhen : null
      };
      const internals = this[$internals2];
      if (this.handlers == null) {
        this.handlers = [];
      }
      syncHandlerEntries(this, internals);
      const id = internals.nextId++;
      this.handlers.push(handler);
      internals.handlerEntries.set(id, {
        handler,
        index: this.handlers.length - 1
      });
      internals.handlersLength = this.handlers.length;
      return id;
    }
    /**
     * Remove an interceptor from the stack
     *
     * @param {Number} id The ID that was returned by `use`
     *
     * @returns {void}
     */
    eject(id) {
      const internals = this[$internals2];
      syncHandlerEntries(this, internals);
      const entry = internals.handlerEntries.get(id);
      if (entry) {
        internals.handlerEntries.delete(id);
        if (this.handlers[entry.index] !== entry.handler) {
          return;
        }
        this.handlers[entry.index] = null;
        if (!internals.iterationDepth) {
          trimHandlers(this.handlers);
          internals.handlersLength = this.handlers.length;
        }
      }
    }
    /**
     * Clear all interceptors from the stack
     *
     * @returns {void}
     */
    clear() {
      if (this.handlers) {
        this.handlers = [];
        syncHandlerEntries(this, this[$internals2]);
      }
    }
    /**
     * Iterate over all the registered interceptors
     *
     * This method is particularly useful for skipping over any
     * interceptors that may have become `null` calling `eject`.
     *
     * @param {Function} fn The function to call for each interceptor
     *
     * @returns {void}
     */
    forEach(fn) {
      const internals = this[$internals2];
      syncHandlerEntries(this, internals);
      internals.iterationDepth++;
      try {
        utils_default.forEach(this.handlers, function forEachHandler(h) {
          if (h !== null) {
            fn(h);
          }
        });
      } finally {
        if (!--internals.iterationDepth) {
          syncHandlerEntries(this, internals);
          trimHandlers(this.handlers);
          internals.handlersLength = countHandlers(this.handlers);
        }
      }
    }
  };
  var InterceptorManager_default = InterceptorManager;

  // node_modules/axios/lib/defaults/transitional.js
  var transitional_default = {
    silentJSONParsing: true,
    forcedJSONParsing: true,
    clarifyTimeoutError: false,
    legacyInterceptorReqResOrdering: true,
    advertiseZstdAcceptEncoding: false,
    validateStatusUndefinedResolves: true
  };

  // node_modules/axios/lib/platform/browser/classes/URLSearchParams.js
  var URLSearchParams_default = typeof URLSearchParams !== "undefined" ? URLSearchParams : AxiosURLSearchParams_default;

  // node_modules/axios/lib/platform/browser/classes/FormData.js
  var FormData_default = typeof FormData !== "undefined" ? FormData : null;

  // node_modules/axios/lib/platform/browser/classes/Blob.js
  var Blob_default = typeof Blob !== "undefined" ? Blob : null;

  // node_modules/axios/lib/platform/browser/index.js
  var browser_default = {
    isBrowser: true,
    classes: {
      URLSearchParams: URLSearchParams_default,
      FormData: FormData_default,
      Blob: Blob_default
    },
    protocols: ["http", "https", "file", "blob", "url", "data"]
  };

  // node_modules/axios/lib/platform/common/utils.js
  var utils_exports = {};
  __export(utils_exports, {
    hasBrowserEnv: () => hasBrowserEnv,
    hasStandardBrowserEnv: () => hasStandardBrowserEnv,
    hasStandardBrowserWebWorkerEnv: () => hasStandardBrowserWebWorkerEnv,
    navigator: () => _navigator,
    origin: () => origin
  });
  var hasBrowserEnv = typeof window !== "undefined" && typeof document !== "undefined";
  var _navigator = typeof navigator === "object" && navigator || void 0;
  var hasStandardBrowserEnv = hasBrowserEnv && (!_navigator || ["ReactNative", "NativeScript", "NS"].indexOf(_navigator.product) < 0);
  var hasStandardBrowserWebWorkerEnv = (() => {
    return typeof WorkerGlobalScope !== "undefined" && // eslint-disable-next-line no-undef
    self instanceof WorkerGlobalScope && typeof self.importScripts === "function";
  })();
  var origin = hasBrowserEnv && window.location.href || "http://localhost";

  // node_modules/axios/lib/platform/index.js
  var platform_default = {
    ...utils_exports,
    ...browser_default
  };

  // node_modules/axios/lib/helpers/toURLEncodedForm.js
  function toURLEncodedForm(data, options) {
    return toFormData_default(data, new platform_default.classes.URLSearchParams(), {
      visitor: function(value, key, path, helpers) {
        if (platform_default.isNode && utils_default.isBuffer(value)) {
          this.append(key, value.toString("base64"));
          return false;
        }
        return helpers.defaultVisitor.apply(this, arguments);
      },
      ...options
    });
  }

  // node_modules/axios/lib/helpers/formDataToJSON.js
  var MAX_DEPTH = DEFAULT_FORM_DATA_MAX_DEPTH;
  function throwIfDepthExceeded(index) {
    if (index > MAX_DEPTH) {
      throw new AxiosError_default(
        "FormData field is too deeply nested (" + index + " levels). Max depth: " + MAX_DEPTH,
        AxiosError_default.ERR_FORM_DATA_DEPTH_EXCEEDED
      );
    }
  }
  function parsePropPath(name) {
    const path = [];
    const pattern = /[^.[\]]+|\[([^.[\]]*)]/g;
    let match;
    while ((match = pattern.exec(name)) !== null) {
      throwIfDepthExceeded(path.length);
      path.push(match[0] === "[]" ? "" : match[1] || match[0]);
    }
    return path;
  }
  function arrayToObject(arr) {
    const obj = {};
    const keys = Object.keys(arr);
    let i;
    const len = keys.length;
    let key;
    for (i = 0; i < len; i++) {
      key = keys[i];
      obj[key] = arr[key];
    }
    return obj;
  }
  function formDataToJSON(formData) {
    function buildPath(path, value, target, index) {
      throwIfDepthExceeded(index);
      let name = path[index++];
      if (name === "__proto__") return true;
      const isNumericKey = Number.isFinite(+name);
      const isLast = index >= path.length;
      name = !name && utils_default.isArray(target) ? target.length : name;
      if (isLast) {
        if (utils_default.hasOwnProp(target, name)) {
          target[name] = utils_default.isArray(target[name]) ? target[name].concat(value) : [target[name], value];
        } else {
          target[name] = value;
        }
        return !isNumericKey;
      }
      if (!utils_default.hasOwnProp(target, name) || !utils_default.isObject(target[name])) {
        target[name] = [];
      }
      const result = buildPath(path, value, target[name], index);
      if (result && utils_default.isArray(target[name])) {
        target[name] = arrayToObject(target[name]);
      }
      return !isNumericKey;
    }
    if (utils_default.isFormData(formData) && utils_default.isFunction(formData.entries)) {
      const obj = {};
      utils_default.forEachEntry(formData, (name, value) => {
        buildPath(parsePropPath(name), value, obj, 0);
      });
      return obj;
    }
    return null;
  }
  var formDataToJSON_default = formDataToJSON;

  // node_modules/axios/lib/core/methodList.js
  var methodList = Object.freeze([
    "get",
    "delete",
    "head",
    "options",
    "post",
    "put",
    "patch",
    "purge",
    "link",
    "unlink",
    "query"
  ]);
  var methodList_default = methodList;

  // node_modules/axios/lib/defaults/index.js
  var own = (obj, key) => obj != null && utils_default.hasOwnProp(obj, key) ? obj[key] : void 0;
  function stringifySafely2(rawValue, parser, encoder) {
    if (utils_default.isString(rawValue)) {
      try {
        (parser || JSON.parse)(rawValue);
        return utils_default.trim(rawValue);
      } catch (e2) {
        if (e2.name !== "SyntaxError") {
          throw e2;
        }
      }
    }
    return (encoder || JSON.stringify)(rawValue);
  }
  var defaults = {
    transitional: transitional_default,
    adapter: ["xhr", "http", "fetch"],
    transformRequest: [
      function transformRequest(data, headers) {
        const contentType = headers.getContentType() || "";
        const hasJSONContentType = contentType.indexOf("application/json") > -1;
        const isObjectPayload = utils_default.isObject(data);
        if (isObjectPayload && utils_default.isHTMLForm(data)) {
          data = new FormData(data);
        }
        const isFormData2 = utils_default.isFormData(data);
        if (isFormData2) {
          return hasJSONContentType ? JSON.stringify(formDataToJSON_default(data)) : data;
        }
        if (utils_default.isArrayBuffer(data) || utils_default.isBuffer(data) || utils_default.isStream(data) || utils_default.isFile(data) || utils_default.isBlob(data) || utils_default.isReadableStream(data)) {
          return data;
        }
        if (utils_default.isArrayBufferView(data)) {
          return data.buffer;
        }
        if (utils_default.isURLSearchParams(data)) {
          headers.setContentType("application/x-www-form-urlencoded;charset=utf-8", false);
          return data.toString();
        }
        let isFileList2;
        if (isObjectPayload) {
          const formSerializer = own(this, "formSerializer");
          if (contentType.indexOf("application/x-www-form-urlencoded") > -1) {
            return toURLEncodedForm(data, formSerializer).toString();
          }
          if ((isFileList2 = utils_default.isFileList(data)) || contentType.indexOf("multipart/form-data") > -1) {
            const env = own(this, "env");
            const _FormData = env && env.FormData;
            return toFormData_default(
              isFileList2 ? { "files[]": data } : data,
              _FormData && new _FormData(),
              formSerializer
            );
          }
        }
        if (isObjectPayload || hasJSONContentType) {
          headers.setContentType("application/json", false);
          return stringifySafely2(data);
        }
        return data;
      }
    ],
    transformResponse: [
      function transformResponse(data) {
        const transitional2 = own(this, "transitional") || defaults.transitional;
        const forcedJSONParsing = transitional2 && transitional2.forcedJSONParsing;
        const responseType = own(this, "responseType");
        const JSONRequested = responseType === "json";
        if (utils_default.isResponse(data) || utils_default.isReadableStream(data)) {
          return data;
        }
        if (data && utils_default.isString(data) && (forcedJSONParsing && !responseType || JSONRequested)) {
          const silentJSONParsing = transitional2 && transitional2.silentJSONParsing;
          const strictJSONParsing = !silentJSONParsing && JSONRequested;
          try {
            return JSON.parse(data, own(this, "parseReviver"));
          } catch (e2) {
            if (strictJSONParsing) {
              if (e2.name === "SyntaxError") {
                throw AxiosError_default.from(e2, AxiosError_default.ERR_BAD_RESPONSE, this, null, own(this, "response"));
              }
              throw e2;
            }
          }
        }
        return data;
      }
    ],
    /**
     * A timeout in milliseconds to abort a request. If set to 0 (default) a
     * timeout is not created.
     */
    timeout: 0,
    xsrfCookieName: "XSRF-TOKEN",
    xsrfHeaderName: "X-XSRF-TOKEN",
    maxContentLength: -1,
    maxBodyLength: -1,
    env: {
      FormData: platform_default.classes.FormData,
      Blob: platform_default.classes.Blob
    },
    validateStatus: function validateStatus(status) {
      return status >= 200 && status < 300;
    },
    headers: {
      common: {
        Accept: "application/json, text/plain, */*",
        "Content-Type": void 0
      }
    }
  };
  utils_default.forEach(methodList_default, (method) => {
    defaults.headers[method] = {};
  });
  var defaults_default = defaults;

  // node_modules/axios/lib/core/transformData.js
  function transformData(fns, response) {
    const config = this || defaults_default;
    const context = response || config;
    const headers = AxiosHeaders_default.from(context.headers);
    let data = context.data;
    utils_default.forEach(fns, function transform(fn) {
      data = fn.call(config, data, headers.normalize(), response ? response.status : void 0);
    });
    headers.normalize();
    return data;
  }

  // node_modules/axios/lib/cancel/isCancel.js
  function isCancel(value) {
    return !!(value && value.__CANCEL__);
  }

  // node_modules/axios/lib/cancel/CanceledError.js
  var CanceledError = class extends AxiosError_default {
    /**
     * A `CanceledError` is an object that is thrown when an operation is canceled.
     *
     * @param {string=} message The message.
     * @param {Object=} config The config.
     * @param {Object=} request The request.
     *
     * @returns {CanceledError} The created error.
     */
    constructor(message, config, request) {
      super(message == null ? "canceled" : message, AxiosError_default.ERR_CANCELED, config, request);
      this.name = "CanceledError";
      this.__CANCEL__ = true;
    }
  };
  var CanceledError_default = CanceledError;

  // node_modules/axios/lib/core/settle.js
  function settle(resolve, reject, response) {
    const validateStatus2 = response.config.validateStatus;
    if (!response.status || !validateStatus2 || validateStatus2(response.status)) {
      resolve(response);
    } else {
      reject(new AxiosError_default(
        "Request failed with status code " + response.status,
        response.status >= 400 && response.status < 500 ? AxiosError_default.ERR_BAD_REQUEST : AxiosError_default.ERR_BAD_RESPONSE,
        response.config,
        response.request,
        response
      ));
    }
  }

  // node_modules/axios/lib/helpers/normalizeURLForProtocolCheck.js
  var urlParserControlCharacters = /[\t\n\r]/g;
  function normalizeURLForProtocolCheck(url) {
    if (typeof url !== "string") {
      return url;
    }
    let start = 0;
    while (start < url.length && url.charCodeAt(start) <= 32) {
      start++;
    }
    return url.slice(start).replace(urlParserControlCharacters, "");
  }

  // node_modules/axios/lib/helpers/parseProtocol.js
  function parseProtocol(url) {
    const match = /^([-+\w]{1,25}):(?:\/\/)?/.exec(url);
    return match && match[1] || "";
  }

  // node_modules/axios/lib/helpers/speedometer.js
  function speedometer(samplesCount, min) {
    samplesCount = samplesCount || 10;
    const bytes = new Array(samplesCount);
    const timestamps = new Array(samplesCount);
    let head = 0;
    let tail = 0;
    let firstSampleTS;
    min = min !== void 0 ? min : 1e3;
    return function push(chunkLength) {
      const now = Date.now();
      const startedAt = timestamps[tail];
      if (!firstSampleTS) {
        firstSampleTS = now;
      }
      bytes[head] = chunkLength;
      timestamps[head] = now;
      let i = tail;
      let bytesCount = 0;
      while (i !== head) {
        bytesCount += bytes[i++];
        i = i % samplesCount;
      }
      head = (head + 1) % samplesCount;
      if (head === tail) {
        tail = (tail + 1) % samplesCount;
      }
      if (now - firstSampleTS < min) {
        return;
      }
      const passed = startedAt && now - startedAt;
      return passed ? Math.round(bytesCount * 1e3 / passed) : void 0;
    };
  }
  var speedometer_default = speedometer;

  // node_modules/axios/lib/helpers/throttle.js
  function throttle(fn, freq) {
    let timestamp = 0;
    let threshold = 1e3 / freq;
    let lastArgs;
    let timer;
    const invoke = (args, now = Date.now()) => {
      timestamp = now;
      lastArgs = null;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      fn(...args);
    };
    const throttled = (...args) => {
      const now = Date.now();
      const passed = now - timestamp;
      if (passed >= threshold) {
        invoke(args, now);
      } else {
        lastArgs = args;
        if (!timer) {
          timer = setTimeout(() => {
            timer = null;
            invoke(lastArgs);
          }, threshold - passed);
        }
      }
    };
    const flush = () => lastArgs && invoke(lastArgs);
    const flushWith = (...args) => invoke(args);
    return [throttled, flush, flushWith];
  }
  var throttle_default = throttle;

  // node_modules/axios/lib/helpers/progressEventReducer.js
  var progressEventReducer = (listener, isDownloadStream, freq = 3) => {
    let bytesNotified = 0;
    const _speedometer = speedometer_default(50, 250);
    return throttle_default((e2) => {
      if (!e2 || !utils_default.isNumber(e2.loaded)) {
        return;
      }
      const rawLoaded = e2.loaded;
      const total = e2.lengthComputable ? e2.total : void 0;
      const loaded = Math.max(0, total != null ? Math.min(rawLoaded, total) : rawLoaded);
      const progressBytes = Math.max(0, loaded - bytesNotified);
      const rate = _speedometer(progressBytes);
      bytesNotified = Math.max(bytesNotified, loaded);
      const data = {
        loaded,
        total,
        progress: total ? loaded / total : void 0,
        bytes: progressBytes,
        rate: rate ? rate : void 0,
        estimated: rate && total ? (total - loaded) / rate : void 0,
        event: e2,
        lengthComputable: total != null,
        [isDownloadStream ? "download" : "upload"]: true
      };
      listener(data);
    }, freq);
  };
  var progressEventDecorator = (total, throttled) => {
    const lengthComputable = total != null;
    return [
      (loaded) => throttled[0]({
        lengthComputable,
        total,
        loaded
      }),
      throttled[1]
    ];
  };
  var asyncDecorator = (fn, scheduler = utils_default.asap) => (...args) => scheduler(() => fn(...args));

  // node_modules/axios/lib/helpers/isURLSameOrigin.js
  var isURLSameOrigin_default = platform_default.hasStandardBrowserEnv ? /* @__PURE__ */ ((origin2, isMSIE) => (url) => {
    url = new URL(url, platform_default.origin);
    return origin2.protocol === url.protocol && origin2.host === url.host && (isMSIE || origin2.port === url.port);
  })(
    new URL(platform_default.origin),
    platform_default.navigator && /(msie|trident)/i.test(platform_default.navigator.userAgent)
  ) : () => true;

  // node_modules/axios/lib/helpers/cookies.js
  var cookies_default = platform_default.hasStandardBrowserEnv ? (
    // Standard browser envs support document.cookie
    {
      write(name, value, expires, path, domain, secure, sameSite) {
        if (typeof document === "undefined") return;
        const cookie = [`${name}=${encodeURIComponent(value)}`];
        if (utils_default.isNumber(expires)) {
          cookie.push(`expires=${new Date(expires).toUTCString()}`);
        }
        if (utils_default.isString(path)) {
          cookie.push(`path=${path}`);
        }
        if (utils_default.isString(domain)) {
          cookie.push(`domain=${domain}`);
        }
        if (secure === true) {
          cookie.push("secure");
        }
        if (utils_default.isString(sameSite)) {
          cookie.push(`SameSite=${sameSite}`);
        }
        document.cookie = cookie.join("; ");
      },
      read(name) {
        if (typeof document === "undefined") return null;
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].replace(/^\s+/, "");
          const eq = cookie.indexOf("=");
          if (eq !== -1 && cookie.slice(0, eq) === name) {
            try {
              return decodeURIComponent(cookie.slice(eq + 1));
            } catch (e2) {
              return cookie.slice(eq + 1);
            }
          }
        }
        return null;
      },
      remove(name) {
        this.write(name, "", Date.now() - 864e5, "/");
      }
    }
  ) : (
    // Non-standard browser env (web workers, react-native) lack needed support.
    {
      write() {
      },
      read() {
        return null;
      },
      remove() {
      }
    }
  );

  // node_modules/axios/lib/helpers/isAbsoluteURL.js
  function isAbsoluteURL(url) {
    if (typeof url !== "string") {
      return false;
    }
    return /^([a-z][a-z\d+\-.]*:)?\/\//i.test(url);
  }

  // node_modules/axios/lib/helpers/combineURLs.js
  function combineURLs(baseURL, relativeURL) {
    if (!relativeURL) {
      return baseURL;
    }
    let end = baseURL.length;
    while (end > 0 && baseURL.charCodeAt(end - 1) === 47) {
      end--;
    }
    return baseURL.slice(0, end) + "/" + relativeURL.replace(/^\/+/, "");
  }

  // node_modules/axios/lib/core/buildFullPath.js
  var malformedHttpProtocol = /^https?:(?!\/\/)/i;
  function redactFragment(fragment) {
    if (!fragment) {
      return fragment;
    }
    return fragment.replace(/(^|&)([^=&]*=)?[^&]+/g, (match, separator, parameterName = "") => {
      return `${separator}${parameterName}${REDACTED}`;
    });
  }
  function redactSensitiveURLParts(url) {
    const redactedURL = url.replace(/^(https?:\/{0,2})[^/?#]*@/i, `$1${REDACTED}@`);
    const fragmentIndex = redactedURL.indexOf("#");
    const urlWithoutFragment = fragmentIndex === -1 ? redactedURL : redactedURL.slice(0, fragmentIndex);
    const redactedURLWithoutFragment = urlWithoutFragment.replace(
      /([?&][^=&#]*=)[^&#]*/g,
      `$1${REDACTED}`
    );
    if (fragmentIndex === -1) {
      return redactedURLWithoutFragment;
    }
    return `${redactedURLWithoutFragment}#${redactFragment(redactedURL.slice(fragmentIndex + 1))}`;
  }
  function assertValidHttpProtocolURL(url, config) {
    if (typeof url === "string") {
      const normalizedURL = normalizeURLForProtocolCheck(url);
      if (malformedHttpProtocol.test(normalizedURL)) {
        throw new AxiosError_default(
          `Invalid URL ${JSON.stringify(redactSensitiveURLParts(normalizedURL))}: missing "//" after protocol`,
          AxiosError_default.ERR_INVALID_URL,
          config
        );
      }
    }
  }
  function buildFullPath(baseURL, requestedURL, allowAbsoluteUrls, config) {
    assertValidHttpProtocolURL(requestedURL, config);
    let isRelativeUrl = !isAbsoluteURL(requestedURL);
    if (baseURL && (isRelativeUrl || allowAbsoluteUrls === false)) {
      assertValidHttpProtocolURL(baseURL, config);
      return combineURLs(baseURL, requestedURL);
    }
    return requestedURL;
  }

  // node_modules/axios/lib/core/mergeConfig.js
  var headersToObject = (thing) => thing instanceof AxiosHeaders_default ? { ...thing } : thing;
  var ownEnumerableKeys = (thing) => {
    if (Object.getOwnPropertySymbols && Object.getOwnPropertyDescriptor) {
      return Object.keys(thing).concat(
        Object.getOwnPropertySymbols(thing).filter(
          (symbol) => Object.getOwnPropertyDescriptor(thing, symbol).enumerable
        )
      );
    }
    return Object.keys(thing);
  };
  function mergeConfig(config1, config2) {
    config1 = config1 || {};
    config2 = config2 || {};
    const config = /* @__PURE__ */ Object.create(null);
    Object.defineProperty(config, "hasOwnProperty", {
      // Null-proto descriptor so a polluted Object.prototype.get cannot turn
      // this data descriptor into an accessor descriptor on the way in.
      __proto__: null,
      value: Object.prototype.hasOwnProperty,
      enumerable: false,
      writable: true,
      configurable: true
    });
    function getMergedValue(target, source, prop, caseless) {
      if (utils_default.isPlainObject(target) && utils_default.isPlainObject(source)) {
        return utils_default.merge.call({ caseless }, target, source);
      } else if (utils_default.isPlainObject(source)) {
        return utils_default.merge({}, source);
      } else if (utils_default.isArray(source)) {
        return source.slice();
      }
      return source;
    }
    function mergeDeepProperties(a, b, prop, caseless) {
      if (!utils_default.isUndefined(b)) {
        return getMergedValue(a, b, prop, caseless);
      } else if (!utils_default.isUndefined(a)) {
        return getMergedValue(void 0, a, prop, caseless);
      }
    }
    function valueFromConfig2(a, b) {
      if (!utils_default.isUndefined(b)) {
        return getMergedValue(void 0, b);
      }
    }
    function defaultToConfig2(a, b) {
      if (!utils_default.isUndefined(b)) {
        return getMergedValue(void 0, b);
      } else if (!utils_default.isUndefined(a)) {
        return getMergedValue(void 0, a);
      }
    }
    function getMergedTransitionalOption(prop) {
      const transitional2 = utils_default.hasOwnProp(config2, "transitional") ? config2.transitional : void 0;
      if (!utils_default.isUndefined(transitional2)) {
        if (utils_default.isPlainObject(transitional2)) {
          if (utils_default.hasOwnProp(transitional2, prop)) {
            return transitional2[prop];
          }
        } else {
          return void 0;
        }
      }
      const transitional1 = utils_default.hasOwnProp(config1, "transitional") ? config1.transitional : void 0;
      if (utils_default.isPlainObject(transitional1) && utils_default.hasOwnProp(transitional1, prop)) {
        return transitional1[prop];
      }
      return void 0;
    }
    function mergeDirectKeys(a, b, prop) {
      if (utils_default.hasOwnProp(config2, prop)) {
        return getMergedValue(a, b);
      } else if (utils_default.hasOwnProp(config1, prop)) {
        return getMergedValue(void 0, a);
      }
    }
    const mergeMap = {
      url: valueFromConfig2,
      method: valueFromConfig2,
      data: valueFromConfig2,
      baseURL: defaultToConfig2,
      transformRequest: defaultToConfig2,
      transformResponse: defaultToConfig2,
      paramsSerializer: defaultToConfig2,
      timeout: defaultToConfig2,
      timeoutErrorMessage: defaultToConfig2,
      withCredentials: defaultToConfig2,
      withXSRFToken: defaultToConfig2,
      adapter: defaultToConfig2,
      responseType: defaultToConfig2,
      xsrfCookieName: defaultToConfig2,
      xsrfHeaderName: defaultToConfig2,
      onUploadProgress: defaultToConfig2,
      onDownloadProgress: defaultToConfig2,
      decompress: defaultToConfig2,
      maxContentLength: defaultToConfig2,
      maxBodyLength: defaultToConfig2,
      beforeRedirect: defaultToConfig2,
      transport: defaultToConfig2,
      httpAgent: defaultToConfig2,
      httpsAgent: defaultToConfig2,
      cancelToken: defaultToConfig2,
      socketPath: defaultToConfig2,
      allowedSocketPaths: defaultToConfig2,
      responseEncoding: defaultToConfig2,
      validateStatus: mergeDirectKeys,
      headers: (a, b, prop) => mergeDeepProperties(headersToObject(a), headersToObject(b), prop, true)
    };
    utils_default.forEach(ownEnumerableKeys({ ...config1, ...config2 }), function computeConfigValue(prop) {
      if (prop === "__proto__" || prop === "constructor" || prop === "prototype") return;
      const merge2 = utils_default.hasOwnProp(mergeMap, prop) ? mergeMap[prop] : mergeDeepProperties;
      const a = utils_default.hasOwnProp(config1, prop) ? config1[prop] : void 0;
      const b = utils_default.hasOwnProp(config2, prop) ? config2[prop] : void 0;
      const configValue = merge2(a, b, prop);
      utils_default.isUndefined(configValue) && merge2 !== mergeDirectKeys || (config[prop] = configValue);
    });
    if (utils_default.hasOwnProp(config2, "validateStatus") && utils_default.isUndefined(config2.validateStatus) && getMergedTransitionalOption("validateStatusUndefinedResolves") === false) {
      if (utils_default.hasOwnProp(config1, "validateStatus")) {
        config.validateStatus = getMergedValue(void 0, config1.validateStatus);
      } else {
        delete config.validateStatus;
      }
    }
    return config;
  }

  // node_modules/axios/lib/core/setFormDataHeaders.js
  var FORM_DATA_CONTENT_HEADERS = ["content-type", "content-length"];
  function setFormDataHeaders(headers, formHeaders, policy) {
    if (policy !== "content-only") {
      headers.set(formHeaders);
      return;
    }
    Object.entries(formHeaders || {}).forEach(([key, val]) => {
      if (FORM_DATA_CONTENT_HEADERS.includes(key.toLowerCase())) {
        headers.set(key, val);
      }
    });
  }

  // node_modules/axios/lib/helpers/resolveConfig.js
  var encodeUTF8 = (str) => encodeURIComponent(str).replace(
    /%([0-9A-F]{2})/gi,
    (_, hex) => String.fromCharCode(parseInt(hex, 16))
  );
  function resolveConfig(config) {
    const newConfig = mergeConfig({}, config);
    const own2 = (key) => utils_default.hasOwnProp(newConfig, key) ? newConfig[key] : void 0;
    const data = own2("data");
    let withXSRFToken = own2("withXSRFToken");
    const xsrfHeaderName = own2("xsrfHeaderName");
    const xsrfCookieName = own2("xsrfCookieName");
    let headers = own2("headers");
    const auth = own2("auth");
    const baseURL = own2("baseURL");
    const allowAbsoluteUrls = own2("allowAbsoluteUrls");
    const url = own2("url");
    newConfig.headers = headers = AxiosHeaders_default.from(headers);
    newConfig.url = buildURL(
      buildFullPath(baseURL, url, allowAbsoluteUrls, newConfig),
      own2("params"),
      own2("paramsSerializer")
    );
    if (auth) {
      const username = utils_default.getSafeProp(auth, "username") || "";
      const password = utils_default.getSafeProp(auth, "password") || "";
      try {
        headers.set(
          "Authorization",
          "Basic " + btoa(username + ":" + (password ? encodeUTF8(password) : ""))
        );
      } catch (e2) {
        throw AxiosError_default.from(e2, AxiosError_default.ERR_BAD_OPTION_VALUE, config);
      }
    }
    if (utils_default.isFormData(data)) {
      const getHeaders = utils_default.getSafeProp(data, "getHeaders");
      if (platform_default.hasStandardBrowserEnv || platform_default.hasStandardBrowserWebWorkerEnv || utils_default.isReactNative(data)) {
        headers.setContentType(void 0);
      } else if (utils_default.isFunction(getHeaders)) {
        setFormDataHeaders(headers, getHeaders.call(data), own2("formDataHeaderPolicy"));
      }
    }
    if (platform_default.hasStandardBrowserEnv) {
      if (utils_default.isFunction(withXSRFToken)) {
        withXSRFToken = withXSRFToken(newConfig);
      }
      const shouldSendXSRF = withXSRFToken === true || withXSRFToken == null && isURLSameOrigin_default(newConfig.url);
      if (shouldSendXSRF) {
        const xsrfValue = xsrfHeaderName && xsrfCookieName && cookies_default.read(xsrfCookieName);
        if (xsrfValue) {
          headers.set(xsrfHeaderName, xsrfValue);
        }
      }
    }
    return newConfig;
  }
  var resolveConfig_default = resolveConfig;

  // node_modules/axios/lib/adapters/xhr.js
  var isXHRAdapterSupported = typeof XMLHttpRequest !== "undefined";
  var xhr_default = isXHRAdapterSupported && function(config) {
    return new Promise(function dispatchXhrRequest(resolve, reject) {
      const _config = resolveConfig_default(config);
      let requestData = _config.data;
      const requestHeaders = AxiosHeaders_default.from(_config.headers).normalize();
      let { responseType, onUploadProgress, onDownloadProgress } = _config;
      let onCanceled;
      let uploadThrottled, downloadThrottled;
      let flushUpload, flushDownload, flushDownloadWithEvent;
      function done() {
        flushUpload && flushUpload();
        flushDownload && flushDownload();
        _config.cancelToken && _config.cancelToken.unsubscribe(onCanceled);
        _config.signal && _config.signal.removeEventListener("abort", onCanceled);
      }
      let request = new XMLHttpRequest();
      request.open(_config.method.toUpperCase(), _config.url, true);
      request.timeout = _config.timeout;
      function onloadend(event) {
        if (!request) {
          return;
        }
        if (request.status === 0 && (parseProtocol(normalizeURLForProtocolCheck(_config.url)) || parseProtocol(platform_default.origin)) !== "file" && !(request.responseURL && request.responseURL.startsWith("file:"))) {
          reject(new AxiosError_default("Request aborted", AxiosError_default.ECONNABORTED, config, request));
          done();
          request = null;
          return;
        }
        try {
          if (event) {
            flushDownloadWithEvent && flushDownloadWithEvent(event);
          } else {
            flushDownload && flushDownload();
          }
        } catch (err) {
          setTimeout(() => {
            throw err;
          });
        }
        if (!request) {
          return;
        }
        const responseHeaders = AxiosHeaders_default.from(
          "getAllResponseHeaders" in request && request.getAllResponseHeaders()
        );
        const responseData = !responseType || responseType === "text" || responseType === "json" ? request.responseText : request.response;
        const response = {
          data: responseData,
          status: request.status,
          statusText: request.statusText,
          headers: responseHeaders,
          config,
          request
        };
        settle(
          function _resolve(value) {
            resolve(value);
            done();
          },
          function _reject(err) {
            reject(err);
            done();
          },
          response
        );
        request = null;
      }
      if ("onloadend" in request) {
        request.onloadend = onloadend;
      } else {
        request.onreadystatechange = function handleLoad() {
          if (!request || request.readyState !== 4) {
            return;
          }
          if (request.status === 0 && !(request.responseURL && request.responseURL.startsWith("file:"))) {
            return;
          }
          setTimeout(onloadend);
        };
      }
      request.onabort = function handleAbort() {
        if (!request) {
          return;
        }
        reject(new AxiosError_default("Request aborted", AxiosError_default.ECONNABORTED, config, request));
        done();
        request = null;
      };
      request.onerror = function handleError(event) {
        const msg = event && event.message ? event.message : "Network Error";
        const err = new AxiosError_default(msg, AxiosError_default.ERR_NETWORK, config, request);
        err.event = event || null;
        reject(err);
        done();
        request = null;
      };
      request.ontimeout = function handleTimeout() {
        let timeoutErrorMessage = _config.timeout ? "timeout of " + _config.timeout + "ms exceeded" : "timeout exceeded";
        const transitional2 = _config.transitional || transitional_default;
        if (_config.timeoutErrorMessage) {
          timeoutErrorMessage = _config.timeoutErrorMessage;
        }
        reject(
          new AxiosError_default(
            timeoutErrorMessage,
            transitional2.clarifyTimeoutError ? AxiosError_default.ETIMEDOUT : AxiosError_default.ECONNABORTED,
            config,
            request
          )
        );
        done();
        request = null;
      };
      requestData === void 0 && requestHeaders.setContentType(null);
      if ("setRequestHeader" in request) {
        utils_default.forEach(toByteStringHeaderObject(requestHeaders), function setRequestHeader(val, key) {
          request.setRequestHeader(key, val);
        });
      }
      if (!utils_default.isUndefined(_config.withCredentials)) {
        request.withCredentials = !!_config.withCredentials;
      }
      if (responseType && responseType !== "json") {
        request.responseType = _config.responseType;
      }
      if (onDownloadProgress) {
        [downloadThrottled, flushDownload, flushDownloadWithEvent] = progressEventReducer(
          onDownloadProgress,
          true
        );
        request.addEventListener("progress", downloadThrottled);
      }
      if (onUploadProgress && request.upload) {
        [uploadThrottled, flushUpload] = progressEventReducer(onUploadProgress);
        request.upload.addEventListener("progress", uploadThrottled);
        request.upload.addEventListener("loadend", flushUpload);
      }
      if (_config.cancelToken || _config.signal) {
        onCanceled = (cancel) => {
          if (!request) {
            return;
          }
          reject(!cancel || cancel.type ? new CanceledError_default(null, config, request) : cancel);
          request.abort();
          done();
          request = null;
        };
        _config.cancelToken && _config.cancelToken.subscribe(onCanceled);
        if (_config.signal) {
          _config.signal.aborted ? onCanceled() : _config.signal.addEventListener("abort", onCanceled);
        }
      }
      const protocol = parseProtocol(_config.url);
      if (protocol && !platform_default.protocols.includes(protocol)) {
        reject(
          new AxiosError_default(
            "Unsupported protocol " + protocol + ":",
            AxiosError_default.ERR_BAD_REQUEST,
            config
          )
        );
        done();
        return;
      }
      request.send(requestData || null);
    });
  };

  // node_modules/axios/lib/helpers/composeSignals.js
  var composeSignals = (signals, timeout) => {
    signals = signals ? signals.filter(Boolean) : [];
    if (!timeout && !signals.length) {
      return;
    }
    const controller = new AbortController();
    let aborted = false;
    const onabort = function(reason) {
      if (!aborted) {
        aborted = true;
        unsubscribe2();
        const err = reason instanceof Error ? reason : this.reason;
        controller.abort(
          err instanceof AxiosError_default ? err : new CanceledError_default(err instanceof Error ? err.message : err)
        );
      }
    };
    let timer = timeout && setTimeout(() => {
      timer = null;
      onabort(new AxiosError_default(`timeout of ${timeout}ms exceeded`, AxiosError_default.ETIMEDOUT));
    }, timeout);
    const unsubscribe2 = () => {
      if (!signals) {
        return;
      }
      timer && clearTimeout(timer);
      timer = null;
      signals.forEach((signal2) => {
        signal2.unsubscribe ? signal2.unsubscribe(onabort) : signal2.removeEventListener("abort", onabort);
      });
      signals = null;
    };
    signals.forEach((signal2) => {
      if (aborted) {
        return;
      }
      if (signal2.aborted) {
        onabort.call(signal2);
        return;
      }
      signal2.addEventListener("abort", onabort, { once: true });
    });
    const { signal } = controller;
    signal.unsubscribe = () => utils_default.asap(unsubscribe2);
    return signal;
  };
  var composeSignals_default = composeSignals;

  // node_modules/axios/lib/helpers/trackStream.js
  var streamChunk = function* (chunk, chunkSize) {
    let len = chunk.byteLength;
    if (!chunkSize || len < chunkSize) {
      yield chunk;
      return;
    }
    let pos = 0;
    let end;
    while (pos < len) {
      end = pos + chunkSize;
      yield chunk.slice(pos, end);
      pos = end;
    }
  };
  var readBytes = async function* (iterable, chunkSize) {
    for await (const chunk of readStream(iterable)) {
      yield* streamChunk(chunk, chunkSize);
    }
  };
  var readStream = async function* (stream) {
    if (stream[Symbol.asyncIterator]) {
      yield* stream;
      return;
    }
    const reader = stream.getReader();
    try {
      for (; ; ) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        yield value;
      }
    } finally {
      await reader.cancel();
    }
  };
  var trackStream = (stream, chunkSize, onProgress, onFinish) => {
    const iterator2 = readBytes(stream, chunkSize);
    let bytes = 0;
    let done;
    let _onFinish = (e2) => {
      if (!done) {
        done = true;
        onFinish && onFinish(e2);
      }
    };
    return new ReadableStream(
      {
        async pull(controller) {
          try {
            const { done: done2, value } = await iterator2.next();
            if (done2) {
              _onFinish();
              controller.close();
              return;
            }
            let len = value.byteLength;
            if (onProgress) {
              let loadedBytes = bytes += len;
              onProgress(loadedBytes);
            }
            controller.enqueue(new Uint8Array(value));
          } catch (err) {
            _onFinish(err);
            throw err;
          }
        },
        cancel(reason) {
          _onFinish(reason);
          return iterator2.return();
        }
      },
      {
        highWaterMark: 2
      }
    );
  };

  // node_modules/axios/lib/helpers/estimateDataURLDecodedBytes.js
  var isHexDigit = (charCode) => charCode >= 48 && charCode <= 57 || charCode >= 65 && charCode <= 70 || charCode >= 97 && charCode <= 102;
  var isPercentEncodedByte = (str, i, len) => i + 2 < len && isHexDigit(str.charCodeAt(i + 1)) && isHexDigit(str.charCodeAt(i + 2));
  var hexValue = (charCode) => charCode <= 57 ? charCode - 48 : (charCode & 223) - 55;
  var isBase64Char = (charCode) => charCode >= 65 && charCode <= 90 || // A-Z
  charCode >= 97 && charCode <= 122 || // a-z
  charCode >= 48 && charCode <= 57 || // 0-9
  charCode === 43 || // +
  charCode === 47 || // /
  charCode === 45 || // - (base64url)
  charCode === 95;
  var isBase64Whitespace = (charCode) => charCode === 9 || charCode === 10 || charCode === 12 || charCode === 13 || charCode === 32;
  var base64Bytes = (significant) => {
    const groups = Math.floor(significant / 4);
    const remainder = significant % 4;
    return groups * 3 + (remainder === 2 ? 1 : remainder === 3 ? 2 : 0);
  };
  var estimateBase64BufferAllocation = (body) => {
    const len = body.length;
    let padding = 0;
    if (len > 0 && body.charCodeAt(len - 1) === 61) {
      padding++;
      if (len > 1 && body.charCodeAt(len - 2) === 61) {
        padding++;
      }
    }
    return Math.floor((len - padding) * 3 / 4);
  };
  var estimatePercentDecodedBase64Bytes = (body) => {
    const len = body.length;
    let significant = 0;
    let padding = 0;
    let invalid = false;
    for (let i = 0; i < len; i++) {
      let code = body.charCodeAt(i);
      if (code === 37 && isPercentEncodedByte(body, i, len)) {
        code = hexValue(body.charCodeAt(i + 1)) * 16 + hexValue(body.charCodeAt(i + 2));
        i += 2;
      }
      if (isBase64Whitespace(code)) {
        continue;
      }
      if (code === 61) {
        padding++;
        continue;
      }
      if (!isBase64Char(code) || padding > 0) {
        invalid = true;
        continue;
      }
      significant++;
    }
    if (invalid || padding > 2 || padding > 0 && (significant + padding) % 4 !== 0 || significant % 4 === 1) {
      return estimateBase64BufferAllocation(body);
    }
    return base64Bytes(significant);
  };
  var estimateDataURLBytes = (url, estimateBase64) => {
    if (!url || typeof url !== "string") return 0;
    if (!url.startsWith("data:")) return 0;
    const comma = url.indexOf(",");
    if (comma < 0) return 0;
    const meta = url.slice(5, comma);
    const body = url.slice(comma + 1);
    const isBase64 = /;base64/i.test(meta);
    if (isBase64) {
      return estimateBase64(body);
    }
    let bytes = 0;
    for (let i = 0, len = body.length; i < len; i++) {
      const c = body.charCodeAt(i);
      if (c === 37 && isPercentEncodedByte(body, i, len)) {
        bytes += 1;
        i += 2;
      } else if (c < 128) {
        bytes += 1;
      } else if (c < 2048) {
        bytes += 2;
      } else if (c >= 55296 && c <= 56319 && i + 1 < len) {
        const next = body.charCodeAt(i + 1);
        if (next >= 56320 && next <= 57343) {
          bytes += 4;
          i++;
        } else {
          bytes += 3;
        }
      } else {
        bytes += 3;
      }
    }
    return bytes;
  };
  function estimateDataURLDecodedBytes(url) {
    const fragmentIndex = typeof url === "string" ? url.indexOf("#") : -1;
    return estimateDataURLBytes(
      fragmentIndex === -1 ? url : url.slice(0, fragmentIndex),
      estimatePercentDecodedBase64Bytes
    );
  }

  // node_modules/axios/lib/env/data.js
  var VERSION = "1.20.0";

  // node_modules/axios/lib/adapters/fetch.js
  var DEFAULT_CHUNK_SIZE = 64 * 1024;
  var DEFAULT_REQUEST_OPTIONS = {
    cache: "default",
    redirect: "follow",
    referrer: "about:client",
    referrerPolicy: "",
    mode: "cors",
    integrity: "",
    keepalive: false,
    priority: "auto",
    window: null
  };
  var { isFunction: isFunction2 } = utils_default;
  var encodeUTF82 = (str) => encodeURIComponent(str).replace(
    /%([0-9A-F]{2})/gi,
    (_, hex) => String.fromCharCode(parseInt(hex, 16))
  );
  var decodeURIComponentSafe = (value) => {
    if (!utils_default.isString(value)) {
      return value;
    }
    try {
      return decodeURIComponent(value);
    } catch (error) {
      return value;
    }
  };
  var test = (fn, ...args) => {
    try {
      return !!fn(...args);
    } catch (e2) {
      return false;
    }
  };
  var maybeWithAuthCredentials = (url) => {
    const protocolIndex = url.indexOf("://");
    let urlToCheck = url;
    if (protocolIndex !== -1) {
      urlToCheck = urlToCheck.slice(protocolIndex + 3);
    }
    return urlToCheck.includes("@") || urlToCheck.includes(":");
  };
  var factory = (env) => {
    const globalObject = utils_default.global !== void 0 && utils_default.global !== null ? utils_default.global : globalThis;
    const { ReadableStream: ReadableStream2, TextEncoder } = globalObject;
    env = utils_default.merge.call(
      {
        skipUndefined: true
      },
      {
        Request: globalObject.Request,
        Response: globalObject.Response
      },
      env
    );
    const { fetch: envFetch, Request, Response } = env;
    const isFetchSupported = envFetch ? isFunction2(envFetch) : typeof fetch === "function";
    const isRequestSupported = isFunction2(Request);
    const isResponseSupported = isFunction2(Response);
    if (!isFetchSupported) {
      return false;
    }
    const isReadableStreamSupported = isFetchSupported && isFunction2(ReadableStream2);
    const encodeText = isFetchSupported && (typeof TextEncoder === "function" ? /* @__PURE__ */ ((encoder) => (str) => encoder.encode(str))(new TextEncoder()) : async (str) => new Uint8Array(await new Request(str).arrayBuffer()));
    const supportsRequestStream = isRequestSupported && isReadableStreamSupported && test(() => {
      let duplexAccessed = false;
      const request = new Request(platform_default.origin, {
        body: new ReadableStream2(),
        method: "POST",
        get duplex() {
          duplexAccessed = true;
          return "half";
        }
      });
      const hasContentType = request.headers.has("Content-Type");
      if (request.body != null) {
        request.body.cancel();
      }
      return duplexAccessed && !hasContentType;
    });
    const supportsResponseStream = isResponseSupported && isReadableStreamSupported && test(() => utils_default.isReadableStream(new Response("").body));
    const resolvers = {
      stream: supportsResponseStream && ((res) => res.body)
    };
    isFetchSupported && (() => {
      ["text", "arrayBuffer", "blob", "formData", "stream"].forEach((type) => {
        !resolvers[type] && (resolvers[type] = (res, config) => {
          let method = res && res[type];
          if (method) {
            return method.call(res);
          }
          throw new AxiosError_default(
            `Response type '${type}' is not supported`,
            AxiosError_default.ERR_NOT_SUPPORT,
            config
          );
        });
      });
    })();
    const getBodyLength = async (body) => {
      if (body == null) {
        return 0;
      }
      if (utils_default.isBlob(body)) {
        return body.size;
      }
      if (utils_default.isSpecCompliantForm(body)) {
        const _request = new Request(platform_default.origin, {
          method: "POST",
          body
        });
        return (await _request.arrayBuffer()).byteLength;
      }
      if (utils_default.isArrayBufferView(body) || utils_default.isArrayBuffer(body)) {
        return body.byteLength;
      }
      if (utils_default.isURLSearchParams(body)) {
        body = body + "";
      }
      if (utils_default.isString(body)) {
        return (await encodeText(body)).byteLength;
      }
    };
    const resolveBodyLength = async (headers, body) => {
      const length = utils_default.toFiniteNumber(headers.getContentLength());
      return length == null ? getBodyLength(body) : length;
    };
    return async (config) => {
      let {
        url,
        method,
        data,
        signal,
        cancelToken,
        timeout,
        onDownloadProgress,
        onUploadProgress,
        responseType,
        headers,
        withCredentials = "same-origin",
        fetchOptions,
        maxContentLength,
        maxBodyLength,
        maxRedirects
      } = resolveConfig_default(config);
      const hasMaxContentLength = utils_default.isNumber(maxContentLength) && maxContentLength > -1;
      const hasMaxBodyLength = utils_default.isNumber(maxBodyLength) && maxBodyLength > -1;
      const own2 = (key) => utils_default.hasOwnProp(config, key) ? config[key] : void 0;
      let _fetch = envFetch || fetch;
      responseType = responseType ? (responseType + "").toLowerCase() : "text";
      let composedSignal = composeSignals_default(
        [signal, cancelToken && cancelToken.toAbortSignal()],
        timeout
      );
      let request = null;
      const unsubscribe2 = composedSignal && composedSignal.unsubscribe && (() => {
        composedSignal.unsubscribe();
      });
      let requestContentLength;
      let pendingBodyError = null;
      const maxBodyLengthError = () => new AxiosError_default(
        "Request body larger than maxBodyLength limit",
        AxiosError_default.ERR_BAD_REQUEST,
        config,
        request
      );
      try {
        let auth = void 0;
        const configAuth = own2("auth");
        if (configAuth) {
          const username = utils_default.getSafeProp(configAuth, "username") || "";
          const password = utils_default.getSafeProp(configAuth, "password") || "";
          auth = {
            username,
            password
          };
        }
        if (maybeWithAuthCredentials(url)) {
          const parsedURL = new URL(url, platform_default.origin);
          if (!auth && (parsedURL.username || parsedURL.password)) {
            const urlUsername = decodeURIComponentSafe(parsedURL.username);
            const urlPassword = decodeURIComponentSafe(parsedURL.password);
            auth = {
              username: urlUsername,
              password: urlPassword
            };
          }
          if (parsedURL.username || parsedURL.password) {
            parsedURL.username = "";
            parsedURL.password = "";
            url = parsedURL.href;
          }
        }
        if (auth) {
          headers.delete("authorization");
          headers.set(
            "Authorization",
            "Basic " + btoa(encodeUTF82((auth.username || "") + ":" + (auth.password || "")))
          );
        }
        if (hasMaxContentLength && typeof url === "string" && url.startsWith("data:")) {
          const estimated = estimateDataURLDecodedBytes(url);
          if (estimated > maxContentLength) {
            throw new AxiosError_default(
              "maxContentLength size of " + maxContentLength + " exceeded",
              AxiosError_default.ERR_BAD_RESPONSE,
              config,
              request
            );
          }
        }
        if (hasMaxBodyLength && method !== "get" && method !== "head") {
          const outboundLength = await getBodyLength(data);
          if (typeof outboundLength === "number" && isFinite(outboundLength)) {
            requestContentLength = outboundLength;
            if (outboundLength > maxBodyLength) {
              throw maxBodyLengthError();
            }
          }
        }
        const mustEnforceStreamBody = hasMaxBodyLength && (utils_default.isReadableStream(data) || utils_default.isStream(data));
        const trackRequestStream = (stream, onProgress, flush) => trackStream(
          stream,
          DEFAULT_CHUNK_SIZE,
          (loadedBytes) => {
            if (hasMaxBodyLength && loadedBytes > maxBodyLength) {
              throw pendingBodyError = maxBodyLengthError();
            }
            onProgress && onProgress(loadedBytes);
          },
          flush
        );
        if (supportsRequestStream && method !== "get" && method !== "head" && (onUploadProgress || mustEnforceStreamBody)) {
          requestContentLength = requestContentLength == null ? await resolveBodyLength(headers, data) : requestContentLength;
          if (requestContentLength !== 0 || mustEnforceStreamBody) {
            let _request = new Request(url, {
              method: "POST",
              body: data,
              duplex: "half"
            });
            let contentTypeHeader;
            if (utils_default.isFormData(data) && (contentTypeHeader = _request.headers.get("content-type"))) {
              headers.setContentType(contentTypeHeader);
            }
            if (_request.body) {
              const [onProgress, flush] = onUploadProgress && progressEventDecorator(
                requestContentLength,
                progressEventReducer(asyncDecorator(onUploadProgress))
              ) || [];
              data = trackRequestStream(_request.body, onProgress, flush);
            }
          }
        } else if (mustEnforceStreamBody && !isRequestSupported && isReadableStreamSupported && method !== "get" && method !== "head") {
          data = trackRequestStream(data);
        } else if (mustEnforceStreamBody && isRequestSupported && !supportsRequestStream && method !== "get" && method !== "head") {
          throw new AxiosError_default(
            "Stream request bodies are not supported by the current fetch implementation",
            AxiosError_default.ERR_NOT_SUPPORT,
            config,
            request
          );
        }
        if (!utils_default.isString(withCredentials)) {
          withCredentials = withCredentials ? "include" : "omit";
        }
        const isCredentialsSupported = isRequestSupported && "credentials" in Request.prototype;
        if (utils_default.isFormData(data)) {
          const contentType = headers.getContentType();
          if (contentType && /^multipart\/form-data/i.test(contentType) && !/boundary=/i.test(contentType)) {
            headers.delete("content-type");
          }
        }
        headers.set("User-Agent", "axios/" + VERSION, false);
        const safeFetchOptions = fetchOptions == null ? fetchOptions : Object.assign(/* @__PURE__ */ Object.create(null), fetchOptions);
        if (safeFetchOptions) {
          delete safeFetchOptions.body;
          delete safeFetchOptions.headers;
          delete safeFetchOptions.method;
          delete safeFetchOptions.signal;
          delete safeFetchOptions.duplex;
          delete safeFetchOptions.credentials;
        }
        const resolvedOptions = Object.assign(/* @__PURE__ */ Object.create(null), safeFetchOptions, {
          signal: composedSignal,
          method: method.toUpperCase(),
          headers: toByteStringHeaderObject(headers.normalize()),
          body: data,
          duplex: "half",
          credentials: isCredentialsSupported ? withCredentials : void 0
        });
        if (isRequestSupported) {
          utils_default.forEach(DEFAULT_REQUEST_OPTIONS, (value, key) => {
            if (resolvedOptions[key] === void 0) {
              resolvedOptions[key] = value;
            }
          });
          if (resolvedOptions.signal === void 0) {
            resolvedOptions.signal = null;
          }
          if (resolvedOptions.body === void 0) {
            resolvedOptions.body = null;
          }
        }
        if (maxRedirects === 0) {
          resolvedOptions.redirect = "manual";
          if (safeFetchOptions) {
            safeFetchOptions.redirect = "manual";
          }
        }
        request = isRequestSupported && new Request(url, resolvedOptions);
        let response = await (isRequestSupported ? _fetch(request, safeFetchOptions) : _fetch(url, resolvedOptions));
        const responseHeaders = AxiosHeaders_default.from(response.headers);
        if (hasMaxContentLength) {
          const declaredLength = utils_default.toFiniteNumber(responseHeaders.getContentLength());
          if (declaredLength != null && declaredLength > maxContentLength) {
            throw new AxiosError_default(
              "maxContentLength size of " + maxContentLength + " exceeded",
              AxiosError_default.ERR_BAD_RESPONSE,
              config,
              request
            );
          }
        }
        const isStreamResponse = supportsResponseStream && (responseType === "stream" || responseType === "response");
        if (supportsResponseStream && response.body && (onDownloadProgress || hasMaxContentLength || isStreamResponse && unsubscribe2)) {
          const options = {};
          ["status", "statusText", "headers"].forEach((prop) => {
            options[prop] = response[prop];
          });
          const responseContentLength = utils_default.toFiniteNumber(responseHeaders.getContentLength());
          const [onProgress, flush] = onDownloadProgress && progressEventDecorator(
            responseContentLength,
            progressEventReducer(asyncDecorator(onDownloadProgress), true)
          ) || [];
          let bytesRead = 0;
          const onChunkProgress = (loadedBytes) => {
            if (hasMaxContentLength) {
              bytesRead = loadedBytes;
              if (bytesRead > maxContentLength) {
                throw new AxiosError_default(
                  "maxContentLength size of " + maxContentLength + " exceeded",
                  AxiosError_default.ERR_BAD_RESPONSE,
                  config,
                  request
                );
              }
            }
            onProgress && onProgress(loadedBytes);
          };
          response = new Response(
            trackStream(response.body, DEFAULT_CHUNK_SIZE, onChunkProgress, () => {
              flush && flush();
              unsubscribe2 && unsubscribe2();
            }),
            options
          );
        }
        responseType = responseType || "text";
        let responseData = await resolvers[utils_default.findKey(resolvers, responseType) || "text"](
          response,
          config
        );
        if (hasMaxContentLength && !supportsResponseStream && !isStreamResponse) {
          let materializedSize;
          if (responseData != null) {
            if (typeof responseData.byteLength === "number") {
              materializedSize = responseData.byteLength;
            } else if (typeof responseData.size === "number") {
              materializedSize = responseData.size;
            } else if (typeof responseData === "string") {
              materializedSize = typeof TextEncoder === "function" ? new TextEncoder().encode(responseData).byteLength : responseData.length;
            }
          }
          if (typeof materializedSize === "number" && materializedSize > maxContentLength) {
            throw new AxiosError_default(
              "maxContentLength size of " + maxContentLength + " exceeded",
              AxiosError_default.ERR_BAD_RESPONSE,
              config,
              request
            );
          }
        }
        !isStreamResponse && unsubscribe2 && unsubscribe2();
        return await new Promise((resolve, reject) => {
          settle(resolve, reject, {
            data: responseData,
            headers: AxiosHeaders_default.from(response.headers),
            status: response.status,
            statusText: response.statusText,
            config,
            request
          });
        });
      } catch (err) {
        unsubscribe2 && unsubscribe2();
        if (composedSignal && composedSignal.aborted && composedSignal.reason instanceof AxiosError_default) {
          const canceledError = composedSignal.reason;
          canceledError.config = config;
          request && (canceledError.request = request);
          if (err !== canceledError) {
            Object.defineProperty(canceledError, "cause", {
              __proto__: null,
              value: err,
              writable: true,
              enumerable: false,
              configurable: true
            });
          }
          throw canceledError;
        }
        if (pendingBodyError) {
          request && !pendingBodyError.request && (pendingBodyError.request = request);
          throw pendingBodyError;
        }
        if (err instanceof AxiosError_default) {
          request && !err.request && (err.request = request);
          throw err;
        }
        if (err && err.name === "TypeError" && /Load failed|fetch/i.test(err.message)) {
          const networkError = new AxiosError_default(
            "Network Error",
            AxiosError_default.ERR_NETWORK,
            config,
            request,
            err && err.response
          );
          Object.defineProperty(networkError, "cause", {
            __proto__: null,
            value: err.cause || err,
            writable: true,
            enumerable: false,
            configurable: true
          });
          throw networkError;
        }
        throw AxiosError_default.from(err, err && err.code, config, request, err && err.response);
      }
    };
  };
  var seedCache = /* @__PURE__ */ new Map();
  var getFetch = (config) => {
    let env = config && config.env || {};
    const { fetch: fetch2, Request, Response } = env;
    const seeds = [Request, Response, fetch2];
    let len = seeds.length, i = len, seed, target, map = seedCache;
    while (i--) {
      seed = seeds[i];
      target = map.get(seed);
      target === void 0 && map.set(seed, target = i ? /* @__PURE__ */ new Map() : factory(env));
      map = target;
    }
    return target;
  };
  var adapter = getFetch();

  // node_modules/axios/lib/adapters/adapters.js
  var knownAdapters = {
    http: null_default,
    xhr: xhr_default,
    fetch: {
      get: getFetch
    }
  };
  utils_default.forEach(knownAdapters, (fn, value) => {
    if (fn) {
      try {
        Object.defineProperty(fn, "name", { __proto__: null, value });
      } catch (e2) {
      }
      Object.defineProperty(fn, "adapterName", { __proto__: null, value });
    }
  });
  var renderReason = (reason) => `- ${reason}`;
  var isResolvedHandle = (adapter2) => utils_default.isFunction(adapter2) || adapter2 === null || adapter2 === false;
  function getAdapter(adapters, config) {
    adapters = utils_default.isArray(adapters) ? adapters : [adapters];
    const { length } = adapters;
    let nameOrAdapter;
    let adapter2;
    const rejectedReasons = {};
    for (let i = 0; i < length; i++) {
      nameOrAdapter = adapters[i];
      let id;
      adapter2 = nameOrAdapter;
      if (!isResolvedHandle(nameOrAdapter)) {
        adapter2 = knownAdapters[(id = String(nameOrAdapter)).toLowerCase()];
        if (adapter2 === void 0) {
          throw new AxiosError_default(`Unknown adapter '${id}'`);
        }
      }
      if (adapter2 && (utils_default.isFunction(adapter2) || (adapter2 = adapter2.get(config)))) {
        break;
      }
      rejectedReasons[id || "#" + i] = adapter2;
    }
    if (!adapter2) {
      const reasons = Object.entries(rejectedReasons).map(
        ([id, state]) => `adapter ${id} ` + (state === false ? "is not supported by the environment" : "is not available in the build")
      );
      let s = length ? reasons.length > 1 ? "since :\n" + reasons.map(renderReason).join("\n") : " " + renderReason(reasons[0]) : "as no adapter specified";
      throw new AxiosError_default(
        `There is no suitable adapter to dispatch the request ` + s,
        AxiosError_default.ERR_NOT_SUPPORT
      );
    }
    return adapter2;
  }
  var adapters_default = {
    /**
     * Resolve an adapter from a list of adapter names or functions.
     * @type {Function}
     */
    getAdapter,
    /**
     * Exposes all known adapters
     * @type {Object<string, Function|Object>}
     */
    adapters: knownAdapters
  };

  // node_modules/axios/lib/core/dispatchRequest.js
  function throwIfCancellationRequested(config) {
    if (config.cancelToken) {
      config.cancelToken.throwIfRequested();
    }
    if (config.signal && config.signal.aborted) {
      throw new CanceledError_default(null, config);
    }
  }
  function dispatchRequest(_config) {
    const config = utils_default.toSafeFlatObject(_config);
    throwIfCancellationRequested(config);
    config.headers = AxiosHeaders_default.from(utils_default.getSafeProp(config, "headers"));
    config.data = transformData.call(config, config.transformRequest);
    if (["post", "put", "patch"].indexOf(config.method) !== -1) {
      config.headers.setContentType("application/x-www-form-urlencoded", false);
    }
    const adapter2 = adapters_default.getAdapter(config.adapter || defaults_default.adapter, config);
    return adapter2(config).then(
      function onAdapterResolution(response) {
        throwIfCancellationRequested(config);
        config.response = response;
        try {
          response.data = transformData.call(config, config.transformResponse, response);
        } finally {
          delete config.response;
        }
        response.headers = AxiosHeaders_default.from(response.headers);
        return response;
      },
      function onAdapterRejection(reason) {
        if (!isCancel(reason)) {
          throwIfCancellationRequested(config);
          if (reason && reason.response) {
            config.response = reason.response;
            try {
              reason.response.data = transformData.call(
                config,
                config.transformResponse,
                reason.response
              );
            } finally {
              delete config.response;
            }
            reason.response.headers = AxiosHeaders_default.from(reason.response.headers);
          }
        }
        return Promise.reject(reason);
      }
    );
  }

  // node_modules/axios/lib/helpers/validator.js
  var validators = {};
  ["object", "boolean", "number", "function", "string", "symbol"].forEach((type, i) => {
    validators[type] = function validator(thing) {
      return typeof thing === type || "a" + (i < 1 ? "n " : " ") + type;
    };
  });
  var deprecatedWarnings = {};
  validators.transitional = function transitional(validator, version, message) {
    function formatMessage(opt, desc) {
      return "[Axios v" + VERSION + "] Transitional option '" + opt + "'" + desc + (message ? ". " + message : "");
    }
    return (value, opt, opts) => {
      if (validator === false) {
        throw new AxiosError_default(
          formatMessage(opt, " has been removed" + (version ? " in " + version : "")),
          AxiosError_default.ERR_DEPRECATED
        );
      }
      if (version && !deprecatedWarnings[opt]) {
        deprecatedWarnings[opt] = true;
        console.warn(
          formatMessage(
            opt,
            " has been deprecated since v" + version + " and will be removed in the near future"
          )
        );
      }
      return validator ? validator(value, opt, opts) : true;
    };
  };
  validators.spelling = function spelling(correctSpelling) {
    return (value, opt) => {
      console.warn(`${opt} is likely a misspelling of ${correctSpelling}`);
      return true;
    };
  };
  function assertOptions(options, schema, allowUnknown) {
    if (typeof options !== "object" || options === null) {
      throw new AxiosError_default("options must be an object", AxiosError_default.ERR_BAD_OPTION_VALUE);
    }
    const keys = Object.keys(options);
    let i = keys.length;
    while (i-- > 0) {
      const opt = keys[i];
      const validator = Object.prototype.hasOwnProperty.call(schema, opt) ? schema[opt] : void 0;
      if (validator) {
        const value = options[opt];
        const result = value === void 0 || validator(value, opt, options);
        if (result !== true) {
          throw new AxiosError_default(
            "option " + opt + " must be " + result,
            AxiosError_default.ERR_BAD_OPTION_VALUE
          );
        }
        continue;
      }
      if (allowUnknown !== true) {
        throw new AxiosError_default("Unknown option " + opt, AxiosError_default.ERR_BAD_OPTION);
      }
    }
  }
  var validator_default = {
    assertOptions,
    validators
  };

  // node_modules/axios/lib/core/Axios.js
  var validators2 = validator_default.validators;
  var Axios = class {
    constructor(instanceConfig) {
      this.defaults = instanceConfig || {};
      this.interceptors = {
        request: new InterceptorManager_default(),
        response: new InterceptorManager_default()
      };
    }
    /**
     * Dispatch a request
     *
     * @param {String|Object} configOrUrl The config specific for this request (merged with this.defaults)
     * @param {?Object} config
     *
     * @returns {Promise} The Promise to be fulfilled
     */
    async request(configOrUrl, config) {
      try {
        return await this._request(configOrUrl, config);
      } catch (err) {
        if (err instanceof Error) {
          try {
            let dummy = {};
            Error.captureStackTrace ? Error.captureStackTrace(dummy) : dummy = new Error();
            const dummyStack = dummy.stack;
            let stack = "";
            if (typeof dummyStack === "string") {
              const firstNewlineIndex = dummyStack.indexOf("\n");
              stack = firstNewlineIndex === -1 ? "" : dummyStack.slice(firstNewlineIndex + 1);
            }
            if (!err.stack) {
              err.stack = stack;
            } else if (stack) {
              const firstNewlineIndex = stack.indexOf("\n");
              const secondNewlineIndex = firstNewlineIndex === -1 ? -1 : stack.indexOf("\n", firstNewlineIndex + 1);
              const stackWithoutTwoTopLines = secondNewlineIndex === -1 ? "" : stack.slice(secondNewlineIndex + 1);
              if (!String(err.stack).endsWith(stackWithoutTwoTopLines)) {
                err.stack += "\n" + stack;
              }
            }
          } catch (e2) {
          }
        }
        throw err;
      }
    }
    _request(configOrUrl, config) {
      if (typeof configOrUrl === "string") {
        config = config || {};
        config.url = configOrUrl;
      } else {
        config = configOrUrl || {};
      }
      config = mergeConfig(this.defaults, config);
      const { transitional: transitional2, paramsSerializer, headers } = config;
      if (transitional2 !== void 0) {
        validator_default.assertOptions(
          transitional2,
          {
            silentJSONParsing: validators2.transitional(validators2.boolean),
            forcedJSONParsing: validators2.transitional(validators2.boolean),
            clarifyTimeoutError: validators2.transitional(validators2.boolean),
            legacyInterceptorReqResOrdering: validators2.transitional(validators2.boolean),
            advertiseZstdAcceptEncoding: validators2.transitional(validators2.boolean),
            validateStatusUndefinedResolves: validators2.transitional(validators2.boolean)
          },
          false
        );
      }
      if (paramsSerializer != null) {
        if (utils_default.isFunction(paramsSerializer)) {
          config.paramsSerializer = {
            serialize: paramsSerializer
          };
        } else {
          validator_default.assertOptions(
            paramsSerializer,
            {
              encode: validators2.function,
              serialize: validators2.function
            },
            true
          );
        }
      }
      if (config.allowAbsoluteUrls !== void 0) {
      } else if (this.defaults.allowAbsoluteUrls !== void 0) {
        config.allowAbsoluteUrls = this.defaults.allowAbsoluteUrls;
      } else {
        config.allowAbsoluteUrls = true;
      }
      validator_default.assertOptions(
        config,
        {
          baseUrl: validators2.spelling("baseURL"),
          withXsrfToken: validators2.spelling("withXSRFToken")
        },
        true
      );
      config.method = (utils_default.getSafeProp(config, "method") || utils_default.getSafeProp(this.defaults, "method") || "get").toLowerCase();
      let contextHeaders = headers && utils_default.merge(headers.common, headers[config.method]);
      headers && utils_default.forEach(methodList_default.concat("common"), (method) => {
        delete headers[method];
      });
      config.headers = AxiosHeaders_default.concat(contextHeaders, headers);
      const requestInterceptorChain = [];
      let synchronousRequestInterceptors = true;
      this.interceptors.request.forEach(function unshiftRequestInterceptors(interceptor) {
        if (typeof interceptor.runWhen === "function" && interceptor.runWhen(config) === false) {
          return;
        }
        synchronousRequestInterceptors = synchronousRequestInterceptors && interceptor.synchronous;
        const transitional3 = config.transitional || transitional_default;
        const legacyInterceptorReqResOrdering = transitional3 && transitional3.legacyInterceptorReqResOrdering;
        if (legacyInterceptorReqResOrdering) {
          requestInterceptorChain.unshift(interceptor.fulfilled, interceptor.rejected);
        } else {
          requestInterceptorChain.push(interceptor.fulfilled, interceptor.rejected);
        }
      });
      const responseInterceptorChain = [];
      this.interceptors.response.forEach(function pushResponseInterceptors(interceptor) {
        responseInterceptorChain.push(interceptor.fulfilled, interceptor.rejected);
      });
      let promise;
      let i = 0;
      let len;
      if (!synchronousRequestInterceptors) {
        const chain = [dispatchRequest.bind(this), void 0];
        chain.unshift(...requestInterceptorChain);
        chain.push(...responseInterceptorChain);
        len = chain.length;
        promise = Promise.resolve(config);
        while (i < len) {
          promise = promise.then(chain[i++], chain[i++]);
        }
        return promise;
      }
      len = requestInterceptorChain.length;
      let newConfig = config;
      while (i < len) {
        const onFulfilled = requestInterceptorChain[i++];
        const onRejected = requestInterceptorChain[i++];
        try {
          newConfig = onFulfilled ? onFulfilled(newConfig) : newConfig;
        } catch (error) {
          if (!onRejected) {
            promise = Promise.reject(error);
            break;
          }
          try {
            const rejectedResult = onRejected.call(this, error);
            if (utils_default.isThenable(rejectedResult)) {
              promise = Promise.resolve(rejectedResult).then(
                () => dispatchRequest.call(this, newConfig)
              );
            }
          } catch (rejectedError) {
            promise = Promise.reject(rejectedError);
          }
          break;
        }
      }
      if (!promise) {
        try {
          promise = dispatchRequest.call(this, newConfig);
        } catch (error) {
          promise = Promise.reject(error);
        }
      }
      i = 0;
      len = responseInterceptorChain.length;
      while (i < len) {
        promise = promise.then(responseInterceptorChain[i++], responseInterceptorChain[i++]);
      }
      return promise;
    }
    getUri(config) {
      config = mergeConfig(this.defaults, config);
      const fullPath = buildFullPath(config.baseURL, config.url, config.allowAbsoluteUrls, config);
      return buildURL(fullPath, config.params, config.paramsSerializer);
    }
  };
  utils_default.forEach(["delete", "get", "head", "options"], function forEachMethodNoData(method) {
    Axios.prototype[method] = function(url, config) {
      return this.request(
        mergeConfig(config || {}, {
          method,
          url,
          data: config && utils_default.hasOwnProp(config, "data") ? config.data : void 0
        })
      );
    };
  });
  utils_default.forEach(["post", "put", "patch", "query"], function forEachMethodWithData(method) {
    function generateHTTPMethod(isForm) {
      return function httpMethod(url, data, config) {
        return this.request(
          mergeConfig(config || {}, {
            method,
            headers: isForm ? {
              "Content-Type": "multipart/form-data"
            } : {},
            url,
            data
          })
        );
      };
    }
    Axios.prototype[method] = generateHTTPMethod();
    if (method !== "query") {
      Axios.prototype[method + "Form"] = generateHTTPMethod(true);
    }
  });
  var Axios_default = Axios;

  // node_modules/axios/lib/cancel/CancelToken.js
  var CancelToken = class _CancelToken {
    constructor(executor) {
      if (typeof executor !== "function") {
        throw new TypeError("executor must be a function.");
      }
      let resolvePromise;
      this.promise = new Promise(function promiseExecutor(resolve) {
        resolvePromise = resolve;
      });
      const token = this;
      this.promise.then((cancel) => {
        if (!token._listeners) return;
        let i = token._listeners.length;
        while (i-- > 0) {
          token._listeners[i](cancel);
        }
        token._listeners = null;
      });
      this.promise.then = (onfulfilled) => {
        let _resolve;
        const promise = new Promise((resolve) => {
          token.subscribe(resolve);
          _resolve = resolve;
        }).then(onfulfilled);
        promise.cancel = function reject() {
          token.unsubscribe(_resolve);
        };
        return promise;
      };
      executor(function cancel(message, config, request) {
        if (token.reason) {
          return;
        }
        token.reason = new CanceledError_default(message, config, request);
        resolvePromise(token.reason);
      });
    }
    /**
     * Throws a `CanceledError` if cancellation has been requested.
     */
    throwIfRequested() {
      if (this.reason) {
        throw this.reason;
      }
    }
    /**
     * Subscribe to the cancel signal
     */
    subscribe(listener) {
      if (this.reason) {
        listener(this.reason);
        return;
      }
      if (this._listeners) {
        this._listeners.push(listener);
      } else {
        this._listeners = [listener];
      }
    }
    /**
     * Unsubscribe from the cancel signal
     */
    unsubscribe(listener) {
      if (!this._listeners) {
        return;
      }
      const index = this._listeners.indexOf(listener);
      if (index !== -1) {
        this._listeners.splice(index, 1);
      }
    }
    toAbortSignal() {
      const controller = new AbortController();
      const abort = (err) => {
        controller.abort(err);
      };
      this.subscribe(abort);
      controller.signal.unsubscribe = () => this.unsubscribe(abort);
      return controller.signal;
    }
    /**
     * Returns an object that contains a new `CancelToken` and a function that, when called,
     * cancels the `CancelToken`.
     */
    static source() {
      let cancel;
      const token = new _CancelToken(function executor(c) {
        cancel = c;
      });
      return {
        token,
        cancel
      };
    }
  };
  var CancelToken_default = CancelToken;

  // node_modules/axios/lib/helpers/spread.js
  function spread(callback) {
    return function wrap(arr) {
      return callback.apply(null, arr);
    };
  }

  // node_modules/axios/lib/helpers/isAxiosError.js
  function isAxiosError(payload) {
    return utils_default.isObject(payload) && payload.isAxiosError === true;
  }

  // node_modules/axios/lib/helpers/HttpStatusCode.js
  var HttpStatusCode = {
    Continue: 100,
    SwitchingProtocols: 101,
    Processing: 102,
    EarlyHints: 103,
    Ok: 200,
    Created: 201,
    Accepted: 202,
    NonAuthoritativeInformation: 203,
    NoContent: 204,
    ResetContent: 205,
    PartialContent: 206,
    MultiStatus: 207,
    AlreadyReported: 208,
    ImUsed: 226,
    MultipleChoices: 300,
    MovedPermanently: 301,
    Found: 302,
    SeeOther: 303,
    NotModified: 304,
    UseProxy: 305,
    Unused: 306,
    TemporaryRedirect: 307,
    PermanentRedirect: 308,
    BadRequest: 400,
    Unauthorized: 401,
    PaymentRequired: 402,
    Forbidden: 403,
    NotFound: 404,
    MethodNotAllowed: 405,
    NotAcceptable: 406,
    ProxyAuthenticationRequired: 407,
    RequestTimeout: 408,
    Conflict: 409,
    Gone: 410,
    LengthRequired: 411,
    PreconditionFailed: 412,
    /**
     * @deprecated Use `ContentTooLarge` instead.
     */
    PayloadTooLarge: 413,
    ContentTooLarge: 413,
    UriTooLong: 414,
    UnsupportedMediaType: 415,
    RangeNotSatisfiable: 416,
    ExpectationFailed: 417,
    ImATeapot: 418,
    MisdirectedRequest: 421,
    /**
     * @deprecated Use `UnprocessableContent` instead.
     */
    UnprocessableEntity: 422,
    UnprocessableContent: 422,
    Locked: 423,
    FailedDependency: 424,
    TooEarly: 425,
    UpgradeRequired: 426,
    PreconditionRequired: 428,
    TooManyRequests: 429,
    RequestHeaderFieldsTooLarge: 431,
    UnavailableForLegalReasons: 451,
    InternalServerError: 500,
    NotImplemented: 501,
    BadGateway: 502,
    ServiceUnavailable: 503,
    GatewayTimeout: 504,
    HttpVersionNotSupported: 505,
    VariantAlsoNegotiates: 506,
    InsufficientStorage: 507,
    LoopDetected: 508,
    NotExtended: 510,
    NetworkAuthenticationRequired: 511,
    WebServerReturnsAnUnknownError: 520,
    WebServerIsDown: 521,
    ConnectionTimedOut: 522,
    OriginIsUnreachable: 523,
    TimeoutOccurred: 524,
    SslHandshakeFailed: 525,
    InvalidSslCertificate: 526
  };
  Object.entries(HttpStatusCode).forEach(([key, value]) => {
    if (HttpStatusCode[value] === void 0) {
      HttpStatusCode[value] = key;
    }
  });
  var HttpStatusCode_default = HttpStatusCode;

  // node_modules/axios/lib/axios.js
  function createInstance(defaultConfig) {
    const context = new Axios_default(defaultConfig);
    const instance = bind(Axios_default.prototype.request, context);
    utils_default.extend(instance, Axios_default.prototype, context, { allOwnKeys: true });
    utils_default.extend(instance, context, null, { allOwnKeys: true });
    instance.create = function create3(instanceConfig) {
      return createInstance(mergeConfig(defaultConfig, instanceConfig));
    };
    return instance;
  }
  var axios = createInstance(defaults_default);
  axios.Axios = Axios_default;
  axios.CanceledError = CanceledError_default;
  axios.CancelToken = CancelToken_default;
  axios.isCancel = isCancel;
  axios.VERSION = VERSION;
  axios.toFormData = toFormData_default;
  axios.AxiosError = AxiosError_default;
  axios.Cancel = axios.CanceledError;
  axios.all = function all(promises) {
    return Promise.all(promises);
  };
  axios.spread = spread;
  axios.isAxiosError = isAxiosError;
  axios.mergeConfig = mergeConfig;
  axios.AxiosHeaders = AxiosHeaders_default;
  axios.formToJSON = (thing) => formDataToJSON_default(utils_default.isHTMLForm(thing) ? new FormData(thing) : thing);
  axios.getAdapter = adapters_default.getAdapter;
  axios.HttpStatusCode = HttpStatusCode_default;
  axios.default = axios;
  var axios_default = axios;

  // node_modules/axios/index.js
  var {
    Axios: Axios2,
    AxiosError: AxiosError2,
    CanceledError: CanceledError2,
    isCancel: isCancel2,
    CancelToken: CancelToken2,
    VERSION: VERSION2,
    all: all2,
    Cancel,
    isAxiosError: isAxiosError2,
    spread: spread2,
    toFormData: toFormData2,
    AxiosHeaders: AxiosHeaders2,
    HttpStatusCode: HttpStatusCode2,
    formToJSON,
    getAdapter: getAdapter2,
    mergeConfig: mergeConfig2,
    create: create2
  } = axios_default;

  // node_modules/@nextcloud/axios/dist/client.js
  function getCancelableClient() {
    const client = axios_default.create({
      headers: {
        requesttoken: getRequestToken() ?? "",
        "X-Requested-With": "XMLHttpRequest"
      }
    });
    onRequestTokenUpdate((token) => {
      client.defaults.headers.requesttoken = token;
    });
    return Object.assign(client, {
      CancelToken: axios_default.CancelToken,
      isCancel: axios_default.isCancel
    });
  }

  // node_modules/@nextcloud/axios/dist/interceptors/csrf-token.js
  var RETRY_KEY = "_nextcloudCsrfTokenReloaded";
  function onCsrfTokenError(axios2) {
    return async (error) => {
      if (!isAxiosError2(error)) {
        throw error;
      }
      const { config, response, request } = error;
      const responseURL = request?.responseURL;
      if (config && !(RETRY_KEY in config) && response?.status === 412 && response?.data?.message === "CSRF check failed") {
        console.warn(`Request to ${responseURL} failed because of a CSRF mismatch. Fetching a new token.`);
        const token = await fetchRequestToken();
        axios2.defaults.headers.requesttoken = token;
        return axios2({
          ...config,
          [RETRY_KEY]: true,
          headers: {
            ...config.headers,
            requesttoken: token
          }
        });
      }
      throw error;
    };
  }

  // node_modules/@nextcloud/axios/dist/interceptors/maintenance-mode.js
  var RETRY_DELAY_KEY = "_nextcloudMaintenanceModeRetryDelay";
  function onMaintenanceModeError(axios2) {
    return async (error) => {
      if (!isAxiosError2(error)) {
        throw error;
      }
      const { config, response, request } = error;
      const responseURL = request?.responseURL;
      const status = response?.status;
      const headers = response?.headers;
      let retryDelay = config?.[RETRY_DELAY_KEY] ?? 1;
      if (status === 503 && headers?.["x-nextcloud-maintenance-mode"] === "1" && config?.retryIfMaintenanceMode) {
        retryDelay *= 2;
        if (retryDelay > 32) {
          console.error("Retry delay exceeded one minute, giving up.", { responseURL });
          throw error;
        }
        console.warn(`Request to ${responseURL} failed because of maintenance mode. Retrying in ${retryDelay}s`);
        await new Promise((resolve) => {
          setTimeout(resolve, retryDelay * 1e3);
        });
        return axios2({
          ...config,
          [RETRY_DELAY_KEY]: retryDelay
        });
      }
      throw error;
    };
  }

  // node_modules/@nextcloud/axios/dist/interceptors/not-logged-in.js
  async function onNotLoggedInError(error) {
    if (isAxiosError2(error)) {
      const { config, response, request } = error;
      const responseURL = request?.responseURL;
      const status = response?.status;
      if (status === 401 && response?.data?.message === "Current user is not logged in" && config?.reloadExpiredSession && globalThis.location?.reload) {
        console.error(`Request to ${responseURL} failed because the user session expired. Reloading the page \u2026`);
        if (globalThis.OC?.reload) {
          globalThis.OC.reload();
        } else {
          globalThis.location.reload();
        }
      }
    }
    throw error;
  }

  // node_modules/@nextcloud/axios/dist/index.js
  var cancelableClient = getCancelableClient();
  cancelableClient.interceptors.response.use((r) => r, onCsrfTokenError(cancelableClient));
  cancelableClient.interceptors.response.use((r) => r, onMaintenanceModeError(cancelableClient));
  cancelableClient.interceptors.response.use((r) => r, onNotLoggedInError);
  var dist_default = cancelableClient;

  // src/tags.js
  var FIELDS = [
    ["title", "\u66F2\u540D"],
    ["artist", "\u30A2\u30FC\u30C6\u30A3\u30B9\u30C8"],
    ["album", "\u30A2\u30EB\u30D0\u30E0"],
    ["albumartist", "\u30A2\u30EB\u30D0\u30E0\u30A2\u30FC\u30C6\u30A3\u30B9\u30C8"],
    ["tracknumber", "\u30C8\u30E9\u30C3\u30AF\u756A\u53F7"],
    ["discnumber", "\u30C7\u30A3\u30B9\u30AF\u756A\u53F7"],
    ["date", "\u5E74"],
    ["genre", "\u30B8\u30E3\u30F3\u30EB"]
  ];
  var toast = (method, message) => {
    if (window.OCP?.Toast?.[method]) {
      window.OCP.Toast[method](message);
    }
  };
  function element(tag, text2, style) {
    const node = document.createElement(tag);
    if (text2) {
      node.textContent = text2;
    }
    if (style) {
      node.style.cssText = style;
    }
    return node;
  }
  async function openEditor(fileId) {
    let tags;
    try {
      const response = await dist_default.get(generateUrl("/apps/shake_tags/tags"), {
        params: { fileId }
      });
      tags = response.data.tags || {};
    } catch (error) {
      toast("error", error?.response?.data?.error || translate("shake_tags", "\u30BF\u30B0\u3092\u8AAD\u307F\u8FBC\u3081\u307E\u305B\u3093"));
      return false;
    }
    return new Promise((resolve) => {
      const overlay = element("div", "", "position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10000;display:flex;align-items:center;justify-content:center");
      const box = element("div", "", "background:var(--color-main-background,#fff);color:var(--color-main-text,#222);padding:20px;border-radius:8px;width:min(520px,92vw);max-height:90vh;overflow:auto");
      box.appendChild(element("h3", translate("shake_tags", "\u30BF\u30B0\u3092\u7DE8\u96C6"), "margin-top:0"));
      const inputs = {};
      for (const [key, label] of FIELDS) {
        const row = element("label", "", "display:block;margin:6px 0");
        row.appendChild(element("span", label, "display:block;font-size:12px;opacity:.8"));
        const input = document.createElement("input");
        input.type = "text";
        input.className = "input";
        input.style.cssText = "width:100%";
        input.value = tags[key] && tags[key][0] || "";
        inputs[key] = input;
        row.appendChild(input);
        box.appendChild(row);
      }
      const candidateBox = element("div", "", "margin:8px 0");
      box.appendChild(candidateBox);
      const actions = element("div", "", "display:flex;gap:8px;margin-top:12px;flex-wrap:wrap");
      box.appendChild(actions);
      const close = (value) => {
        overlay.remove();
        resolve(value);
      };
      const search = element("button", translate("shake_tags", "MusicBrainz\u3067\u691C\u7D22"), "");
      search.className = "button";
      search.addEventListener("click", async () => {
        candidateBox.textContent = "";
        candidateBox.appendChild(element(
          "p",
          translate("shake_tags", "\u691C\u7D22\u4E2D..."),
          "font-size:13px;opacity:.8"
        ));
        try {
          const response = await dist_default.get(generateUrl("/apps/shake_tags/search"), {
            params: {
              artist: inputs.artist.value,
              title: inputs.title.value,
              album: inputs.album.value
            }
          });
          const candidates = response.data.candidates || [];
          candidateBox.textContent = "";
          if (candidates.length === 0) {
            candidateBox.appendChild(element(
              "p",
              translate("shake_tags", "\u5019\u88DC\u304C\u898B\u3064\u304B\u308A\u307E\u305B\u3093"),
              "font-size:13px;opacity:.8"
            ));
            return;
          }
          candidateBox.appendChild(element(
            "span",
            translate("shake_tags", "\u5019\u88DC"),
            "display:block;font-size:12px;opacity:.8"
          ));
          for (const candidate of candidates) {
            const button = element(
              "button",
              `${candidate.title} / ${candidate.artist} / ${candidate.album} (${candidate.date})`,
              "display:block;width:100%;text-align:left;margin:4px 0"
            );
            button.className = "button";
            button.addEventListener("click", () => {
              inputs.title.value = candidate.title || inputs.title.value;
              inputs.artist.value = candidate.artist || inputs.artist.value;
              inputs.album.value = candidate.album || inputs.album.value;
              inputs.albumartist.value = inputs.albumartist.value || candidate.artist || "";
              if (candidate.date) {
                inputs.date.value = candidate.date;
              }
              candidateBox.textContent = "";
            });
            candidateBox.appendChild(button);
          }
        } catch (error) {
          candidateBox.textContent = "";
          toast("error", error?.response?.data?.error || translate("shake_tags", "MusicBrainz\u3092\u691C\u7D22\u3067\u304D\u307E\u305B\u3093"));
        }
      });
      actions.appendChild(search);
      const save = element("button", translate("shake_tags", "\u4FDD\u5B58"), "");
      save.className = "button primary";
      save.addEventListener("click", async () => {
        const payload = {};
        for (const [key] of FIELDS) {
          const value = inputs[key].value.trim();
          if (value !== "") {
            payload[key] = value;
          }
        }
        try {
          const response = await dist_default.post(generateUrl("/apps/shake_tags/tags"), {
            fileId,
            tags: payload
          });
          toast("success", response.data.changed === false ? translate("shake_tags", "\u5909\u66F4\u306F\u3042\u308A\u307E\u305B\u3093\u3067\u3057\u305F") : translate("shake_tags", "\u30BF\u30B0\u3092\u4FDD\u5B58\u3057\u307E\u3057\u305F"));
          close(true);
        } catch (error) {
          toast("error", error?.response?.data?.error || translate("shake_tags", "\u30BF\u30B0\u3092\u4FDD\u5B58\u3067\u304D\u307E\u305B\u3093"));
        }
      });
      actions.appendChild(save);
      const cancel = element("button", translate("shake_tags", "\u30AD\u30E3\u30F3\u30BB\u30EB"), "");
      cancel.className = "button";
      cancel.addEventListener("click", () => close(false));
      actions.appendChild(cancel);
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) {
          close(false);
        }
      });
      overlay.appendChild(box);
      document.body.appendChild(overlay);
    });
  }
  registerFileAction({
    id: "shake-tags",
    displayName: () => translate("shake_tags", "\u30BF\u30B0\u3092\u7DE8\u96C6"),
    iconSvgInline: () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M21.41 11.58l-9-9A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 .59 1.42l9 9A2 2 0 0 0 13 22a2 2 0 0 0 1.41-.59l7-7A2 2 0 0 0 21.41 11.58zM6.5 8A1.5 1.5 0 1 1 8 6.5 1.5 1.5 0 0 1 6.5 8z"/></svg>',
    enabled: ({ nodes }) => nodes.length === 1 && nodes[0].type === FileType.File && (nodes[0].extension || "").toLowerCase().replace(/^\./, "") === "mp3",
    exec: ({ nodes }) => openEditor(nodes[0].fileid),
    order: 27
  });
})();
/*! Bundled license information:

escape-html/index.js:
  (*!
   * escape-html
   * Copyright(c) 2012-2013 TJ Holowaychuk
   * Copyright(c) 2015 Andreas Lubbe
   * Copyright(c) 2015 Tiancheng "Timothy" Gu
   * MIT Licensed
   *)

@nextcloud/event-bus/dist/index.mjs:
@nextcloud/l10n/dist/chunks/translation-DoG5ZELJ.mjs:
@nextcloud/l10n/dist/chunks/translation-DoG5ZELJ.mjs:
  (*!
   * SPDX-FileCopyrightText: 2019 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

@nextcloud/router/dist/index.mjs:
@nextcloud/l10n/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2025 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

@nextcloud/auth/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2024 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

dompurify/dist/purify.es.mjs:
  (*! @license DOMPurify 3.4.15 | (c) Cure53 and other contributors | Released under the Apache license 2.0 and Mozilla Public License 2.0 | github.com/cure53/DOMPurify/blob/3.4.15/LICENSE *)

@nextcloud/l10n/dist/chunks/translation-DoG5ZELJ.mjs:
@nextcloud/l10n/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2022 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

@nextcloud/files/dist/index.mjs:
@nextcloud/files/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2023 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: AGPL-3.0-or-later
   *)

@nextcloud/axios/dist/client.js:
  (*!
   * SPDX-License-Identifier: GPL-3.0-or-later
   * SPDX-FileCopyrightText: 2025 Nextcloud GmbH and Nextcloud contributors
   *)
*/
