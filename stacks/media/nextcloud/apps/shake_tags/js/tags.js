(() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __typeError = (msg) => {
    throw TypeError(msg);
  };
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __require = /* @__PURE__ */ ((x2) => typeof require !== "undefined" ? require : typeof Proxy !== "undefined" ? new Proxy(x2, {
    get: (a2, b2) => (typeof require !== "undefined" ? require : a2)[b2]
  }) : x2)(function(x2) {
    if (typeof require !== "undefined") return require.apply(this, arguments);
    throw Error('Dynamic require of "' + x2 + '" is not supported');
  });
  var __commonJS = (cb, mod) => function __require2() {
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
  var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
  var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
  var __privateAdd = (obj, member, value) => member.has(obj) ? __typeError("Cannot add the same private member more than once") : member instanceof WeakSet ? member.add(obj) : member.set(obj, value);
  var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
  var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);

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
      var re3 = exports.re = [];
      var safeRe = exports.safeRe = [];
      var src = exports.src = [];
      var safeSrc = exports.safeSrc = [];
      var t2 = exports.t = {};
      var R2 = 0;
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
        const index = R2++;
        debug(name, index, value);
        t2[name] = index;
        src[index] = value;
        safeSrc[index] = safe;
        re3[index] = new RegExp(value, isGlobal ? "g" : void 0);
        safeRe[index] = new RegExp(safe, isGlobal ? "g" : void 0);
      };
      createToken("NUMERICIDENTIFIER", "0|[1-9]\\d*");
      createToken("NUMERICIDENTIFIERLOOSE", "\\d+");
      createToken("NONNUMERICIDENTIFIER", `\\d*[a-zA-Z-]${LETTERDASHNUMBER}*`);
      createToken("MAINVERSION", `(${src[t2.NUMERICIDENTIFIER]})\\.(${src[t2.NUMERICIDENTIFIER]})\\.(${src[t2.NUMERICIDENTIFIER]})`);
      createToken("MAINVERSIONLOOSE", `(${src[t2.NUMERICIDENTIFIERLOOSE]})\\.(${src[t2.NUMERICIDENTIFIERLOOSE]})\\.(${src[t2.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASEIDENTIFIER", `(?:${src[t2.NONNUMERICIDENTIFIER]}|${src[t2.NUMERICIDENTIFIER]})`);
      createToken("PRERELEASEIDENTIFIERLOOSE", `(?:${src[t2.NONNUMERICIDENTIFIER]}|${src[t2.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASE", `(?:-(${src[t2.PRERELEASEIDENTIFIER]}(?:\\.${src[t2.PRERELEASEIDENTIFIER]})*))`);
      createToken("PRERELEASELOOSE", `(?:-?(${src[t2.PRERELEASEIDENTIFIERLOOSE]}(?:\\.${src[t2.PRERELEASEIDENTIFIERLOOSE]})*))`);
      createToken("BUILDIDENTIFIER", `${LETTERDASHNUMBER}+`);
      createToken("BUILD", `(?:\\+(${src[t2.BUILDIDENTIFIER]}(?:\\.${src[t2.BUILDIDENTIFIER]})*))`);
      createToken("FULLPLAIN", `v?${src[t2.MAINVERSION]}${src[t2.PRERELEASE]}?${src[t2.BUILD]}?`);
      createToken("FULL", `^${src[t2.FULLPLAIN]}$`);
      createToken("LOOSEPLAIN", `[v=\\s]*${src[t2.MAINVERSIONLOOSE]}${src[t2.PRERELEASELOOSE]}?${src[t2.BUILD]}?`);
      createToken("LOOSE", `^${src[t2.LOOSEPLAIN]}$`);
      createToken("GTLT", "((?:<|>)?=?)");
      createToken("XRANGEIDENTIFIERLOOSE", `${src[t2.NUMERICIDENTIFIERLOOSE]}|x|X|\\*`);
      createToken("XRANGEIDENTIFIER", `${src[t2.NUMERICIDENTIFIER]}|x|X|\\*`);
      createToken("XRANGEPLAIN", `[v=\\s]*(${src[t2.XRANGEIDENTIFIER]})(?:\\.(${src[t2.XRANGEIDENTIFIER]})(?:\\.(${src[t2.XRANGEIDENTIFIER]})(?:${src[t2.PRERELEASE]})?${src[t2.BUILD]}?)?)?`);
      createToken("XRANGEPLAINLOOSE", `[v=\\s]*(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:${src[t2.PRERELEASELOOSE]})?${src[t2.BUILD]}?)?)?`);
      createToken("XRANGE", `^${src[t2.GTLT]}\\s*${src[t2.XRANGEPLAIN]}$`);
      createToken("XRANGELOOSE", `^${src[t2.GTLT]}\\s*${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("COERCEPLAIN", `${"(^|[^\\d])(\\d{1,"}${MAX_SAFE_COMPONENT_LENGTH}})(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?`);
      createToken("COERCE", `${src[t2.COERCEPLAIN]}(?:$|[^\\d])`);
      createToken("COERCEFULL", src[t2.COERCEPLAIN] + `(?:${src[t2.PRERELEASE]})?(?:${src[t2.BUILD]})?(?:$|[^\\d])`);
      createToken("COERCERTL", src[t2.COERCE], true);
      createToken("COERCERTLFULL", src[t2.COERCEFULL], true);
      createToken("LONETILDE", "(?:~>?)");
      createToken("TILDETRIM", `(\\s*)${src[t2.LONETILDE]}\\s+`, true);
      exports.tildeTrimReplace = "$1~";
      createToken("TILDE", `^${src[t2.LONETILDE]}${src[t2.XRANGEPLAIN]}$`);
      createToken("TILDELOOSE", `^${src[t2.LONETILDE]}${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("LONECARET", "(?:\\^)");
      createToken("CARETTRIM", `(\\s*)${src[t2.LONECARET]}\\s+`, true);
      exports.caretTrimReplace = "$1^";
      createToken("CARET", `^${src[t2.LONECARET]}${src[t2.XRANGEPLAIN]}$`);
      createToken("CARETLOOSE", `^${src[t2.LONECARET]}${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("COMPARATORLOOSE", `^${src[t2.GTLT]}\\s*(${src[t2.LOOSEPLAIN]})$|^$`);
      createToken("COMPARATOR", `^${src[t2.GTLT]}\\s*(${src[t2.FULLPLAIN]})$|^$`);
      createToken("COMPARATORTRIM", `(\\s*)${src[t2.GTLT]}\\s*(${src[t2.LOOSEPLAIN]}|${src[t2.XRANGEPLAIN]})`, true);
      exports.comparatorTrimReplace = "$1$2$3";
      createToken("HYPHENRANGE", `^\\s*(${src[t2.XRANGEPLAIN]})\\s+-\\s+(${src[t2.XRANGEPLAIN]})\\s*$`);
      createToken("HYPHENRANGELOOSE", `^\\s*(${src[t2.XRANGEPLAINLOOSE]})\\s+-\\s+(${src[t2.XRANGEPLAINLOOSE]})\\s*$`);
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
      var compareIdentifiers = (a2, b2) => {
        if (typeof a2 === "number" && typeof b2 === "number") {
          return a2 === b2 ? 0 : a2 < b2 ? -1 : 1;
        }
        const anum = numeric.test(a2);
        const bnum = numeric.test(b2);
        if (anum && bnum) {
          a2 = +a2;
          b2 = +b2;
        }
        return a2 === b2 ? 0 : anum && !bnum ? -1 : bnum && !anum ? 1 : a2 < b2 ? -1 : 1;
      };
      var rcompareIdentifiers = (a2, b2) => compareIdentifiers(b2, a2);
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
      var { safeRe: re3, t: t2 } = require_re();
      var parseOptions = require_parse_options();
      var { compareIdentifiers } = require_identifiers();
      var isPrereleaseIdentifier = (prerelease, identifier) => {
        const identifiers2 = identifier.split(".");
        if (identifiers2.length > prerelease.length) {
          return false;
        }
        for (let i2 = 0; i2 < identifiers2.length; i2++) {
          if (compareIdentifiers(prerelease[i2], identifiers2[i2]) !== 0) {
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
          const m2 = version.trim().match(options.loose ? re3[t2.LOOSE] : re3[t2.FULL]);
          if (!m2) {
            throw new TypeError(`Invalid Version: ${version}`);
          }
          this.raw = version;
          this.major = +m2[1];
          this.minor = +m2[2];
          this.patch = +m2[3];
          if (this.major > MAX_SAFE_INTEGER || this.major < 0) {
            throw new TypeError("Invalid major version");
          }
          if (this.minor > MAX_SAFE_INTEGER || this.minor < 0) {
            throw new TypeError("Invalid minor version");
          }
          if (this.patch > MAX_SAFE_INTEGER || this.patch < 0) {
            throw new TypeError("Invalid patch version");
          }
          if (!m2[4]) {
            this.prerelease = [];
          } else {
            this.prerelease = m2[4].split(".").map((id) => {
              if (/^[0-9]+$/.test(id)) {
                const num = +id;
                if (num >= 0 && num < MAX_SAFE_INTEGER) {
                  return num;
                }
              }
              return id;
            });
          }
          this.build = m2[5] ? m2[5].split(".") : [];
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
          let i2 = 0;
          do {
            const a2 = this.prerelease[i2];
            const b2 = other.prerelease[i2];
            debug("prerelease compare", i2, a2, b2);
            if (a2 === void 0 && b2 === void 0) {
              return 0;
            } else if (b2 === void 0) {
              return 1;
            } else if (a2 === void 0) {
              return -1;
            } else if (a2 === b2) {
              continue;
            } else {
              return compareIdentifiers(a2, b2);
            }
          } while (++i2);
        }
        compareBuild(other) {
          if (!(other instanceof _SemVer)) {
            other = new _SemVer(other, this.options);
          }
          let i2 = 0;
          do {
            const a2 = this.build[i2];
            const b2 = other.build[i2];
            debug("build compare", i2, a2, b2);
            if (a2 === void 0 && b2 === void 0) {
              return 0;
            } else if (b2 === void 0) {
              return 1;
            } else if (a2 === void 0) {
              return -1;
            } else if (a2 === b2) {
              continue;
            } else {
              return compareIdentifiers(a2, b2);
            }
          } while (++i2);
        }
        // preminor will bump the version up to the next minor release, and immediately
        // down to pre-release. premajor and prepatch work the same way.
        inc(release, identifier, identifierBase) {
          if (release.startsWith("pre")) {
            if (!identifier && identifierBase === false) {
              throw new Error("invalid increment argument: identifier is empty");
            }
            if (identifier) {
              const match = `-${identifier}`.match(this.options.loose ? re3[t2.PRERELEASELOOSE] : re3[t2.PRERELEASE]);
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
                let i2 = this.prerelease.length;
                while (--i2 >= 0) {
                  if (typeof this.prerelease[i2] === "number") {
                    this.prerelease[i2]++;
                    i2 = -2;
                  }
                }
                if (i2 === -1) {
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
      var major2 = (a2, loose) => new SemVer(a2, loose).major;
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
        } catch (er2) {
          if (!throwErrors) {
            return null;
          }
          throw er2;
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
        const v2 = parse(version, options);
        return v2 ? v2.version : null;
      };
      module.exports = valid2;
    }
  });

  // node_modules/cancelable-promise/umd/CancelablePromise.js
  var require_CancelablePromise = __commonJS({
    "node_modules/cancelable-promise/umd/CancelablePromise.js"(exports) {
      function _typeof(obj) {
        "@babel/helpers - typeof";
        return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(obj2) {
          return typeof obj2;
        } : function(obj2) {
          return obj2 && "function" == typeof Symbol && obj2.constructor === Symbol && obj2 !== Symbol.prototype ? "symbol" : typeof obj2;
        }, _typeof(obj);
      }
      (function(global2, factory2) {
        if (typeof define === "function" && define.amd) {
          define(["exports"], factory2);
        } else if (typeof exports !== "undefined") {
          factory2(exports);
        } else {
          var mod = {
            exports: {}
          };
          factory2(mod.exports);
          global2.CancelablePromise = mod.exports;
        }
      })(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : exports, function(_exports) {
        "use strict";
        Object.defineProperty(_exports, "__esModule", {
          value: true
        });
        _exports.CancelablePromise = void 0;
        _exports.cancelable = cancelable;
        _exports.default = void 0;
        _exports.isCancelablePromise = isCancelablePromise;
        function _inherits(subClass, superClass) {
          if (typeof superClass !== "function" && superClass !== null) {
            throw new TypeError("Super expression must either be null or a function");
          }
          subClass.prototype = Object.create(superClass && superClass.prototype, { constructor: { value: subClass, writable: true, configurable: true } });
          Object.defineProperty(subClass, "prototype", { writable: false });
          if (superClass) _setPrototypeOf(subClass, superClass);
        }
        function _setPrototypeOf(o2, p2) {
          _setPrototypeOf = Object.setPrototypeOf ? Object.setPrototypeOf.bind() : function _setPrototypeOf2(o3, p3) {
            o3.__proto__ = p3;
            return o3;
          };
          return _setPrototypeOf(o2, p2);
        }
        function _createSuper(Derived) {
          var hasNativeReflectConstruct = _isNativeReflectConstruct();
          return function _createSuperInternal() {
            var Super = _getPrototypeOf(Derived), result;
            if (hasNativeReflectConstruct) {
              var NewTarget = _getPrototypeOf(this).constructor;
              result = Reflect.construct(Super, arguments, NewTarget);
            } else {
              result = Super.apply(this, arguments);
            }
            return _possibleConstructorReturn(this, result);
          };
        }
        function _possibleConstructorReturn(self2, call) {
          if (call && (_typeof(call) === "object" || typeof call === "function")) {
            return call;
          } else if (call !== void 0) {
            throw new TypeError("Derived constructors may only return object or undefined");
          }
          return _assertThisInitialized(self2);
        }
        function _assertThisInitialized(self2) {
          if (self2 === void 0) {
            throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
          }
          return self2;
        }
        function _isNativeReflectConstruct() {
          if (typeof Reflect === "undefined" || !Reflect.construct) return false;
          if (Reflect.construct.sham) return false;
          if (typeof Proxy === "function") return true;
          try {
            Boolean.prototype.valueOf.call(Reflect.construct(Boolean, [], function() {
            }));
            return true;
          } catch (e3) {
            return false;
          }
        }
        function _getPrototypeOf(o2) {
          _getPrototypeOf = Object.setPrototypeOf ? Object.getPrototypeOf.bind() : function _getPrototypeOf2(o3) {
            return o3.__proto__ || Object.getPrototypeOf(o3);
          };
          return _getPrototypeOf(o2);
        }
        function _createForOfIteratorHelper(o2, allowArrayLike) {
          var it2 = typeof Symbol !== "undefined" && o2[Symbol.iterator] || o2["@@iterator"];
          if (!it2) {
            if (Array.isArray(o2) || (it2 = _unsupportedIterableToArray2(o2)) || allowArrayLike && o2 && typeof o2.length === "number") {
              if (it2) o2 = it2;
              var i2 = 0;
              var F2 = function F3() {
              };
              return { s: F2, n: function n2() {
                if (i2 >= o2.length) return { done: true };
                return { done: false, value: o2[i2++] };
              }, e: function e3(_e3) {
                throw _e3;
              }, f: F2 };
            }
            throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
          }
          var normalCompletion = true, didErr = false, err;
          return { s: function s2() {
            it2 = it2.call(o2);
          }, n: function n2() {
            var step = it2.next();
            normalCompletion = step.done;
            return step;
          }, e: function e3(_e22) {
            didErr = true;
            err = _e22;
          }, f: function f() {
            try {
              if (!normalCompletion && it2.return != null) it2.return();
            } finally {
              if (didErr) throw err;
            }
          } };
        }
        function _unsupportedIterableToArray2(o2, minLen) {
          if (!o2) return;
          if (typeof o2 === "string") return _arrayLikeToArray2(o2, minLen);
          var n2 = Object.prototype.toString.call(o2).slice(8, -1);
          if (n2 === "Object" && o2.constructor) n2 = o2.constructor.name;
          if (n2 === "Map" || n2 === "Set") return Array.from(o2);
          if (n2 === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n2)) return _arrayLikeToArray2(o2, minLen);
        }
        function _arrayLikeToArray2(arr, len) {
          if (len == null || len > arr.length) len = arr.length;
          for (var i2 = 0, arr2 = new Array(len); i2 < len; i2++) {
            arr2[i2] = arr[i2];
          }
          return arr2;
        }
        function _classCallCheck(instance, Constructor) {
          if (!(instance instanceof Constructor)) {
            throw new TypeError("Cannot call a class as a function");
          }
        }
        function _defineProperties(target, props) {
          for (var i2 = 0; i2 < props.length; i2++) {
            var descriptor = props[i2];
            descriptor.enumerable = descriptor.enumerable || false;
            descriptor.configurable = true;
            if ("value" in descriptor) descriptor.writable = true;
            Object.defineProperty(target, descriptor.key, descriptor);
          }
        }
        function _createClass(Constructor, protoProps, staticProps) {
          if (protoProps) _defineProperties(Constructor.prototype, protoProps);
          if (staticProps) _defineProperties(Constructor, staticProps);
          Object.defineProperty(Constructor, "prototype", { writable: false });
          return Constructor;
        }
        function _defineProperty(obj, key, value) {
          if (key in obj) {
            Object.defineProperty(obj, key, { value, enumerable: true, configurable: true, writable: true });
          } else {
            obj[key] = value;
          }
          return obj;
        }
        function _classPrivateFieldInitSpec(obj, privateMap, value) {
          _checkPrivateRedeclaration(obj, privateMap);
          privateMap.set(obj, value);
        }
        function _checkPrivateRedeclaration(obj, privateCollection) {
          if (privateCollection.has(obj)) {
            throw new TypeError("Cannot initialize the same private elements twice on an object");
          }
        }
        function _classPrivateFieldGet(receiver, privateMap) {
          var descriptor = _classExtractFieldDescriptor(receiver, privateMap, "get");
          return _classApplyDescriptorGet(receiver, descriptor);
        }
        function _classApplyDescriptorGet(receiver, descriptor) {
          if (descriptor.get) {
            return descriptor.get.call(receiver);
          }
          return descriptor.value;
        }
        function _classPrivateFieldSet(receiver, privateMap, value) {
          var descriptor = _classExtractFieldDescriptor(receiver, privateMap, "set");
          _classApplyDescriptorSet(receiver, descriptor, value);
          return value;
        }
        function _classExtractFieldDescriptor(receiver, privateMap, action) {
          if (!privateMap.has(receiver)) {
            throw new TypeError("attempted to " + action + " private field on non-instance");
          }
          return privateMap.get(receiver);
        }
        function _classApplyDescriptorSet(receiver, descriptor, value) {
          if (descriptor.set) {
            descriptor.set.call(receiver, value);
          } else {
            if (!descriptor.writable) {
              throw new TypeError("attempted to set read only private field");
            }
            descriptor.value = value;
          }
        }
        var toStringTag2 = typeof Symbol !== "undefined" ? Symbol.toStringTag : "@@toStringTag";
        var _internals = /* @__PURE__ */ new WeakMap();
        var _promise = /* @__PURE__ */ new WeakMap();
        var CancelablePromiseInternal = /* @__PURE__ */ (function() {
          function CancelablePromiseInternal2(_ref2) {
            var _ref$executor = _ref2.executor, executor = _ref$executor === void 0 ? function() {
            } : _ref$executor, _ref$internals = _ref2.internals, internals = _ref$internals === void 0 ? defaultInternals() : _ref$internals, _ref$promise = _ref2.promise, promise = _ref$promise === void 0 ? new Promise(function(resolve, reject) {
              return executor(resolve, reject, function(onCancel) {
                internals.onCancelList.push(onCancel);
              });
            }) : _ref$promise;
            _classCallCheck(this, CancelablePromiseInternal2);
            _classPrivateFieldInitSpec(this, _internals, {
              writable: true,
              value: void 0
            });
            _classPrivateFieldInitSpec(this, _promise, {
              writable: true,
              value: void 0
            });
            _defineProperty(this, toStringTag2, "CancelablePromise");
            this.cancel = this.cancel.bind(this);
            _classPrivateFieldSet(this, _internals, internals);
            _classPrivateFieldSet(this, _promise, promise || new Promise(function(resolve, reject) {
              return executor(resolve, reject, function(onCancel) {
                internals.onCancelList.push(onCancel);
              });
            }));
          }
          _createClass(CancelablePromiseInternal2, [{
            key: "then",
            value: function then(onfulfilled, onrejected) {
              return makeCancelable(_classPrivateFieldGet(this, _promise).then(createCallback(onfulfilled, _classPrivateFieldGet(this, _internals)), createCallback(onrejected, _classPrivateFieldGet(this, _internals))), _classPrivateFieldGet(this, _internals));
            }
          }, {
            key: "catch",
            value: function _catch(onrejected) {
              return makeCancelable(_classPrivateFieldGet(this, _promise).catch(createCallback(onrejected, _classPrivateFieldGet(this, _internals))), _classPrivateFieldGet(this, _internals));
            }
          }, {
            key: "finally",
            value: function _finally(onfinally, runWhenCanceled) {
              var _this = this;
              if (runWhenCanceled) {
                _classPrivateFieldGet(this, _internals).onCancelList.push(onfinally);
              }
              return makeCancelable(_classPrivateFieldGet(this, _promise).finally(createCallback(function() {
                if (onfinally) {
                  if (runWhenCanceled) {
                    _classPrivateFieldGet(_this, _internals).onCancelList = _classPrivateFieldGet(_this, _internals).onCancelList.filter(function(callback) {
                      return callback !== onfinally;
                    });
                  }
                  return onfinally();
                }
              }, _classPrivateFieldGet(this, _internals))), _classPrivateFieldGet(this, _internals));
            }
          }, {
            key: "cancel",
            value: function cancel() {
              _classPrivateFieldGet(this, _internals).isCanceled = true;
              var callbacks = _classPrivateFieldGet(this, _internals).onCancelList;
              _classPrivateFieldGet(this, _internals).onCancelList = [];
              var _iterator = _createForOfIteratorHelper(callbacks), _step;
              try {
                for (_iterator.s(); !(_step = _iterator.n()).done; ) {
                  var callback = _step.value;
                  if (typeof callback === "function") {
                    try {
                      callback();
                    } catch (err) {
                      console.error(err);
                    }
                  }
                }
              } catch (err) {
                _iterator.e(err);
              } finally {
                _iterator.f();
              }
            }
          }, {
            key: "isCanceled",
            value: function isCanceled() {
              return _classPrivateFieldGet(this, _internals).isCanceled === true;
            }
          }]);
          return CancelablePromiseInternal2;
        })();
        var CancelablePromise2 = /* @__PURE__ */ (function(_CancelablePromiseInt) {
          _inherits(CancelablePromise3, _CancelablePromiseInt);
          var _super = _createSuper(CancelablePromise3);
          function CancelablePromise3(executor) {
            _classCallCheck(this, CancelablePromise3);
            return _super.call(this, {
              executor
            });
          }
          return _createClass(CancelablePromise3);
        })(CancelablePromiseInternal);
        _exports.CancelablePromise = CancelablePromise2;
        _defineProperty(CancelablePromise2, "all", function all3(iterable) {
          return makeAllCancelable(iterable, Promise.all(iterable));
        });
        _defineProperty(CancelablePromise2, "allSettled", function allSettled(iterable) {
          return makeAllCancelable(iterable, Promise.allSettled(iterable));
        });
        _defineProperty(CancelablePromise2, "any", function any(iterable) {
          return makeAllCancelable(iterable, Promise.any(iterable));
        });
        _defineProperty(CancelablePromise2, "race", function race(iterable) {
          return makeAllCancelable(iterable, Promise.race(iterable));
        });
        _defineProperty(CancelablePromise2, "resolve", function resolve(value) {
          return cancelable(Promise.resolve(value));
        });
        _defineProperty(CancelablePromise2, "reject", function reject(reason) {
          return cancelable(Promise.reject(reason));
        });
        _defineProperty(CancelablePromise2, "isCancelable", isCancelablePromise);
        var _default = CancelablePromise2;
        _exports.default = _default;
        function cancelable(promise) {
          return makeCancelable(promise, defaultInternals());
        }
        function isCancelablePromise(promise) {
          return promise instanceof CancelablePromise2 || promise instanceof CancelablePromiseInternal;
        }
        function createCallback(onResult, internals) {
          if (onResult) {
            return function(arg) {
              if (!internals.isCanceled) {
                var result = onResult(arg);
                if (isCancelablePromise(result)) {
                  internals.onCancelList.push(result.cancel);
                }
                return result;
              }
              return arg;
            };
          }
        }
        function makeCancelable(promise, internals) {
          return new CancelablePromiseInternal({
            internals,
            promise
          });
        }
        function makeAllCancelable(iterable, promise) {
          var internals = defaultInternals();
          internals.onCancelList.push(function() {
            var _iterator2 = _createForOfIteratorHelper(iterable), _step2;
            try {
              for (_iterator2.s(); !(_step2 = _iterator2.n()).done; ) {
                var resolvable = _step2.value;
                if (isCancelablePromise(resolvable)) {
                  resolvable.cancel();
                }
              }
            } catch (err) {
              _iterator2.e(err);
            } finally {
              _iterator2.f();
            }
          });
          return new CancelablePromiseInternal({
            internals,
            promise
          });
        }
        function defaultInternals() {
          return {
            isCanceled: false,
            onCancelList: []
          };
        }
      });
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
        var escape2;
        var html2 = "";
        var index = 0;
        var lastIndex = 0;
        for (index = match.index; index < str.length; index++) {
          switch (str.charCodeAt(index)) {
            case 34:
              escape2 = "&quot;";
              break;
            case 38:
              escape2 = "&amp;";
              break;
            case 39:
              escape2 = "&#39;";
              break;
            case 60:
              escape2 = "&lt;";
              break;
            case 62:
              escape2 = "&gt;";
              break;
            default:
              continue;
          }
          if (lastIndex !== index) {
            html2 += str.substring(lastIndex, index);
          }
          lastIndex = index + 1;
          html2 += escape2;
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
        (this.handlers.get(name) || []).filter((h2) => h2 !== handler)
      );
    }
    emit(name, ...event) {
      const handlers = this.handlers.get(name) || [];
      handlers.forEach((h2) => {
        try {
          ;
          h2(event[0]);
        } catch (e3) {
          console.error("could not invoke event listener", e3);
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
  var linkToRemoteBase = (service) => "/remote.php/" + service;
  var generateRemoteUrl = (service, options) => {
    const baseURL = options?.baseURL ?? getBaseUrl();
    return baseURL + linkToRemoteBase(service);
  };
  var _generateUrlPath = (url, params, options) => {
    const allOptions = Object.assign({
      escape: true
    }, options || {});
    const _build = function(text2, vars) {
      vars = vars || {};
      return text2.replace(
        /{([^{}]*)}/g,
        function(a2, b2) {
          const r2 = vars[b2];
          if (allOptions.escape) {
            return typeof r2 === "string" || typeof r2 === "number" ? encodeURIComponent(r2.toString()) : encodeURIComponent(a2);
          } else {
            return typeof r2 === "string" || typeof r2 === "number" ? r2.toString() : a2;
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
  var getBaseUrl = () => window.location.protocol + "//" + window.location.host + getRootUrl();
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

  // node_modules/@nextcloud/initial-state/dist/index.js
  function loadState(app, key, fallback) {
    const selector = `#initial-state-${app}-${key}`;
    if (window._nc_initial_state?.has(selector)) {
      return window._nc_initial_state.get(selector);
    } else if (!window._nc_initial_state) {
      window._nc_initial_state = /* @__PURE__ */ new Map();
    }
    const elem = document.querySelector(selector);
    if (elem === null) {
      if (fallback !== void 0) {
        return fallback;
      }
      throw new Error(`Could not find initial state ${key} of ${app}`);
    }
    try {
      const parsedValue = JSON.parse(atob(elem.value));
      window._nc_initial_state.set(selector, parsedValue);
      return parsedValue;
    } catch (error) {
      console.error("[@nextcloud/initial-state] Could not parse initial state", { key, app, error });
      if (fallback !== void 0) {
        return fallback;
      }
      throw new Error(`Could not parse initial state ${key} of ${app}`, { cause: error });
    }
  }

  // node_modules/@nextcloud/sharing/dist/public.js
  function isPublicShare() {
    return loadState("files_sharing", "isPublic", null) ?? document.querySelector('input#isPublic[type="hidden"][name="isPublic"][value="1"]') !== null;
  }
  function getSharingToken() {
    return loadState("files_sharing", "sharingToken", null) ?? document.querySelector('input#sharingToken[type="hidden"]')?.value ?? null;
  }

  // node_modules/@nextcloud/files/dist/chunks/dav-Rt1kTtvI.mjs
  var import_cancelable_promise = __toESM(require_CancelablePromise(), 1);

  // node_modules/webdav/dist/web/index.js
  var t = { 2(t2) {
    function e3(t3, e4, i2) {
      t3 instanceof RegExp && (t3 = n2(t3, i2)), e4 instanceof RegExp && (e4 = n2(e4, i2));
      var s2 = r2(t3, e4, i2);
      return s2 && { start: s2[0], end: s2[1], pre: i2.slice(0, s2[0]), body: i2.slice(s2[0] + t3.length, s2[1]), post: i2.slice(s2[1] + e4.length) };
    }
    function n2(t3, e4) {
      var n3 = e4.match(t3);
      return n3 ? n3[0] : null;
    }
    function r2(t3, e4, n3) {
      var r3, i2, s2, o2, a2, h2 = n3.indexOf(t3), l2 = n3.indexOf(e4, h2 + 1), u2 = h2;
      if (h2 >= 0 && l2 > 0) {
        for (r3 = [], s2 = n3.length; u2 >= 0 && !a2; ) u2 == h2 ? (r3.push(u2), h2 = n3.indexOf(t3, u2 + 1)) : 1 == r3.length ? a2 = [r3.pop(), l2] : ((i2 = r3.pop()) < s2 && (s2 = i2, o2 = l2), l2 = n3.indexOf(e4, u2 + 1)), u2 = h2 < l2 && h2 >= 0 ? h2 : l2;
        r3.length && (a2 = [s2, o2]);
      }
      return a2;
    }
    t2.exports = e3, e3.range = r2;
  }, 101(t2, e3, n2) {
    var r2;
    t2 = n2.nmd(t2), (function() {
      var i2 = (t2 && t2.exports, "object" == typeof global && global);
      i2.global !== i2 && i2.window;
      var s2 = function(t3) {
        this.message = t3;
      };
      (s2.prototype = new Error()).name = "InvalidCharacterError";
      var o2 = function(t3) {
        throw new s2(t3);
      }, a2 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", h2 = /[\t\n\f\r ]/g, l2 = { encode: function(t3) {
        t3 = String(t3), /[^\0-\xFF]/.test(t3) && o2("The string to be encoded contains characters outside of the Latin1 range.");
        for (var e4, n3, r3, i3, s3 = t3.length % 3, h3 = "", l3 = -1, u2 = t3.length - s3; ++l3 < u2; ) e4 = t3.charCodeAt(l3) << 16, n3 = t3.charCodeAt(++l3) << 8, r3 = t3.charCodeAt(++l3), h3 += a2.charAt((i3 = e4 + n3 + r3) >> 18 & 63) + a2.charAt(i3 >> 12 & 63) + a2.charAt(i3 >> 6 & 63) + a2.charAt(63 & i3);
        return 2 == s3 ? (e4 = t3.charCodeAt(l3) << 8, n3 = t3.charCodeAt(++l3), h3 += a2.charAt((i3 = e4 + n3) >> 10) + a2.charAt(i3 >> 4 & 63) + a2.charAt(i3 << 2 & 63) + "=") : 1 == s3 && (i3 = t3.charCodeAt(l3), h3 += a2.charAt(i3 >> 2) + a2.charAt(i3 << 4 & 63) + "=="), h3;
      }, decode: function(t3) {
        var e4 = (t3 = String(t3).replace(h2, "")).length;
        e4 % 4 == 0 && (e4 = (t3 = t3.replace(/==?$/, "")).length), (e4 % 4 == 1 || /[^+a-zA-Z0-9/]/.test(t3)) && o2("Invalid character: the string to be decoded is not correctly encoded.");
        for (var n3, r3, i3 = 0, s3 = "", l3 = -1; ++l3 < e4; ) r3 = a2.indexOf(t3.charAt(l3)), n3 = i3 % 4 ? 64 * n3 + r3 : r3, i3++ % 4 && (s3 += String.fromCharCode(255 & n3 >> (-2 * i3 & 6)));
        return s3;
      }, version: "1.0.0" };
      void 0 === (r2 = function() {
        return l2;
      }.call(e3, n2, e3, t2)) || (t2.exports = r2);
    })();
  }, 172(t2, e3) {
    e3.d = function(t3) {
      if (!t3) return 0;
      for (var e4 = (t3 = t3.toString()).length, n2 = t3.length; n2--; ) {
        var r2 = t3.charCodeAt(n2);
        56320 <= r2 && r2 <= 57343 && n2--, 127 < r2 && r2 <= 2047 ? e4++ : 2047 < r2 && r2 <= 65535 && (e4 += 2);
      }
      return e4;
    };
  }, 526(t2) {
    var e3 = { utf8: { stringToBytes: function(t3) {
      return e3.bin.stringToBytes(unescape(encodeURIComponent(t3)));
    }, bytesToString: function(t3) {
      return decodeURIComponent(escape(e3.bin.bytesToString(t3)));
    } }, bin: { stringToBytes: function(t3) {
      for (var e4 = [], n2 = 0; n2 < t3.length; n2++) e4.push(255 & t3.charCodeAt(n2));
      return e4;
    }, bytesToString: function(t3) {
      for (var e4 = [], n2 = 0; n2 < t3.length; n2++) e4.push(String.fromCharCode(t3[n2]));
      return e4.join("");
    } } };
    t2.exports = e3;
  }, 298(t2) {
    var e3, n2;
    e3 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", n2 = { rotl: function(t3, e4) {
      return t3 << e4 | t3 >>> 32 - e4;
    }, rotr: function(t3, e4) {
      return t3 << 32 - e4 | t3 >>> e4;
    }, endian: function(t3) {
      if (t3.constructor == Number) return 16711935 & n2.rotl(t3, 8) | 4278255360 & n2.rotl(t3, 24);
      for (var e4 = 0; e4 < t3.length; e4++) t3[e4] = n2.endian(t3[e4]);
      return t3;
    }, randomBytes: function(t3) {
      for (var e4 = []; t3 > 0; t3--) e4.push(Math.floor(256 * Math.random()));
      return e4;
    }, bytesToWords: function(t3) {
      for (var e4 = [], n3 = 0, r2 = 0; n3 < t3.length; n3++, r2 += 8) e4[r2 >>> 5] |= t3[n3] << 24 - r2 % 32;
      return e4;
    }, wordsToBytes: function(t3) {
      for (var e4 = [], n3 = 0; n3 < 32 * t3.length; n3 += 8) e4.push(t3[n3 >>> 5] >>> 24 - n3 % 32 & 255);
      return e4;
    }, bytesToHex: function(t3) {
      for (var e4 = [], n3 = 0; n3 < t3.length; n3++) e4.push((t3[n3] >>> 4).toString(16)), e4.push((15 & t3[n3]).toString(16));
      return e4.join("");
    }, hexToBytes: function(t3) {
      for (var e4 = [], n3 = 0; n3 < t3.length; n3 += 2) e4.push(parseInt(t3.substr(n3, 2), 16));
      return e4;
    }, bytesToBase64: function(t3) {
      for (var n3 = [], r2 = 0; r2 < t3.length; r2 += 3) for (var i2 = t3[r2] << 16 | t3[r2 + 1] << 8 | t3[r2 + 2], s2 = 0; s2 < 4; s2++) 8 * r2 + 6 * s2 <= 8 * t3.length ? n3.push(e3.charAt(i2 >>> 6 * (3 - s2) & 63)) : n3.push("=");
      return n3.join("");
    }, base64ToBytes: function(t3) {
      t3 = t3.replace(/[^A-Z0-9+\/]/gi, "");
      for (var n3 = [], r2 = 0, i2 = 0; r2 < t3.length; i2 = ++r2 % 4) 0 != i2 && n3.push((e3.indexOf(t3.charAt(r2 - 1)) & Math.pow(2, -2 * i2 + 8) - 1) << 2 * i2 | e3.indexOf(t3.charAt(r2)) >>> 6 - 2 * i2);
      return n3;
    } }, t2.exports = n2;
  }, 135(t2) {
    function e3(t3) {
      return !!t3.constructor && "function" == typeof t3.constructor.isBuffer && t3.constructor.isBuffer(t3);
    }
    t2.exports = function(t3) {
      return null != t3 && (e3(t3) || (function(t4) {
        return "function" == typeof t4.readFloatLE && "function" == typeof t4.slice && e3(t4.slice(0, 0));
      })(t3) || !!t3._isBuffer);
    };
  }, 542(t2, e3, n2) {
    !(function() {
      var e4 = n2(298), r2 = n2(526).utf8, i2 = n2(135), s2 = n2(526).bin, o2 = function(t3, n3) {
        t3.constructor == String ? t3 = n3 && "binary" === n3.encoding ? s2.stringToBytes(t3) : r2.stringToBytes(t3) : i2(t3) ? t3 = Array.prototype.slice.call(t3, 0) : Array.isArray(t3) || t3.constructor === Uint8Array || (t3 = t3.toString());
        for (var a2 = e4.bytesToWords(t3), h2 = 8 * t3.length, l2 = 1732584193, u2 = -271733879, c2 = -1732584194, p2 = 271733878, f = 0; f < a2.length; f++) a2[f] = 16711935 & (a2[f] << 8 | a2[f] >>> 24) | 4278255360 & (a2[f] << 24 | a2[f] >>> 8);
        a2[h2 >>> 5] |= 128 << h2 % 32, a2[14 + (h2 + 64 >>> 9 << 4)] = h2;
        var d2 = o2._ff, g = o2._gg, m2 = o2._hh, y2 = o2._ii;
        for (f = 0; f < a2.length; f += 16) {
          var b2 = l2, v2 = u2, w2 = c2, x2 = p2;
          l2 = d2(l2, u2, c2, p2, a2[f + 0], 7, -680876936), p2 = d2(p2, l2, u2, c2, a2[f + 1], 12, -389564586), c2 = d2(c2, p2, l2, u2, a2[f + 2], 17, 606105819), u2 = d2(u2, c2, p2, l2, a2[f + 3], 22, -1044525330), l2 = d2(l2, u2, c2, p2, a2[f + 4], 7, -176418897), p2 = d2(p2, l2, u2, c2, a2[f + 5], 12, 1200080426), c2 = d2(c2, p2, l2, u2, a2[f + 6], 17, -1473231341), u2 = d2(u2, c2, p2, l2, a2[f + 7], 22, -45705983), l2 = d2(l2, u2, c2, p2, a2[f + 8], 7, 1770035416), p2 = d2(p2, l2, u2, c2, a2[f + 9], 12, -1958414417), c2 = d2(c2, p2, l2, u2, a2[f + 10], 17, -42063), u2 = d2(u2, c2, p2, l2, a2[f + 11], 22, -1990404162), l2 = d2(l2, u2, c2, p2, a2[f + 12], 7, 1804603682), p2 = d2(p2, l2, u2, c2, a2[f + 13], 12, -40341101), c2 = d2(c2, p2, l2, u2, a2[f + 14], 17, -1502002290), l2 = g(l2, u2 = d2(u2, c2, p2, l2, a2[f + 15], 22, 1236535329), c2, p2, a2[f + 1], 5, -165796510), p2 = g(p2, l2, u2, c2, a2[f + 6], 9, -1069501632), c2 = g(c2, p2, l2, u2, a2[f + 11], 14, 643717713), u2 = g(u2, c2, p2, l2, a2[f + 0], 20, -373897302), l2 = g(l2, u2, c2, p2, a2[f + 5], 5, -701558691), p2 = g(p2, l2, u2, c2, a2[f + 10], 9, 38016083), c2 = g(c2, p2, l2, u2, a2[f + 15], 14, -660478335), u2 = g(u2, c2, p2, l2, a2[f + 4], 20, -405537848), l2 = g(l2, u2, c2, p2, a2[f + 9], 5, 568446438), p2 = g(p2, l2, u2, c2, a2[f + 14], 9, -1019803690), c2 = g(c2, p2, l2, u2, a2[f + 3], 14, -187363961), u2 = g(u2, c2, p2, l2, a2[f + 8], 20, 1163531501), l2 = g(l2, u2, c2, p2, a2[f + 13], 5, -1444681467), p2 = g(p2, l2, u2, c2, a2[f + 2], 9, -51403784), c2 = g(c2, p2, l2, u2, a2[f + 7], 14, 1735328473), l2 = m2(l2, u2 = g(u2, c2, p2, l2, a2[f + 12], 20, -1926607734), c2, p2, a2[f + 5], 4, -378558), p2 = m2(p2, l2, u2, c2, a2[f + 8], 11, -2022574463), c2 = m2(c2, p2, l2, u2, a2[f + 11], 16, 1839030562), u2 = m2(u2, c2, p2, l2, a2[f + 14], 23, -35309556), l2 = m2(l2, u2, c2, p2, a2[f + 1], 4, -1530992060), p2 = m2(p2, l2, u2, c2, a2[f + 4], 11, 1272893353), c2 = m2(c2, p2, l2, u2, a2[f + 7], 16, -155497632), u2 = m2(u2, c2, p2, l2, a2[f + 10], 23, -1094730640), l2 = m2(l2, u2, c2, p2, a2[f + 13], 4, 681279174), p2 = m2(p2, l2, u2, c2, a2[f + 0], 11, -358537222), c2 = m2(c2, p2, l2, u2, a2[f + 3], 16, -722521979), u2 = m2(u2, c2, p2, l2, a2[f + 6], 23, 76029189), l2 = m2(l2, u2, c2, p2, a2[f + 9], 4, -640364487), p2 = m2(p2, l2, u2, c2, a2[f + 12], 11, -421815835), c2 = m2(c2, p2, l2, u2, a2[f + 15], 16, 530742520), l2 = y2(l2, u2 = m2(u2, c2, p2, l2, a2[f + 2], 23, -995338651), c2, p2, a2[f + 0], 6, -198630844), p2 = y2(p2, l2, u2, c2, a2[f + 7], 10, 1126891415), c2 = y2(c2, p2, l2, u2, a2[f + 14], 15, -1416354905), u2 = y2(u2, c2, p2, l2, a2[f + 5], 21, -57434055), l2 = y2(l2, u2, c2, p2, a2[f + 12], 6, 1700485571), p2 = y2(p2, l2, u2, c2, a2[f + 3], 10, -1894986606), c2 = y2(c2, p2, l2, u2, a2[f + 10], 15, -1051523), u2 = y2(u2, c2, p2, l2, a2[f + 1], 21, -2054922799), l2 = y2(l2, u2, c2, p2, a2[f + 8], 6, 1873313359), p2 = y2(p2, l2, u2, c2, a2[f + 15], 10, -30611744), c2 = y2(c2, p2, l2, u2, a2[f + 6], 15, -1560198380), u2 = y2(u2, c2, p2, l2, a2[f + 13], 21, 1309151649), l2 = y2(l2, u2, c2, p2, a2[f + 4], 6, -145523070), p2 = y2(p2, l2, u2, c2, a2[f + 11], 10, -1120210379), c2 = y2(c2, p2, l2, u2, a2[f + 2], 15, 718787259), u2 = y2(u2, c2, p2, l2, a2[f + 9], 21, -343485551), l2 = l2 + b2 >>> 0, u2 = u2 + v2 >>> 0, c2 = c2 + w2 >>> 0, p2 = p2 + x2 >>> 0;
        }
        return e4.endian([l2, u2, c2, p2]);
      };
      o2._ff = function(t3, e5, n3, r3, i3, s3, o3) {
        var a2 = t3 + (e5 & n3 | ~e5 & r3) + (i3 >>> 0) + o3;
        return (a2 << s3 | a2 >>> 32 - s3) + e5;
      }, o2._gg = function(t3, e5, n3, r3, i3, s3, o3) {
        var a2 = t3 + (e5 & r3 | n3 & ~r3) + (i3 >>> 0) + o3;
        return (a2 << s3 | a2 >>> 32 - s3) + e5;
      }, o2._hh = function(t3, e5, n3, r3, i3, s3, o3) {
        var a2 = t3 + (e5 ^ n3 ^ r3) + (i3 >>> 0) + o3;
        return (a2 << s3 | a2 >>> 32 - s3) + e5;
      }, o2._ii = function(t3, e5, n3, r3, i3, s3, o3) {
        var a2 = t3 + (n3 ^ (e5 | ~r3)) + (i3 >>> 0) + o3;
        return (a2 << s3 | a2 >>> 32 - s3) + e5;
      }, o2._blocksize = 16, o2._digestsize = 16, t2.exports = function(t3, n3) {
        if (null == t3) throw new Error("Illegal argument " + t3);
        var r3 = e4.wordsToBytes(o2(t3, n3));
        return n3 && n3.asBytes ? r3 : n3 && n3.asString ? s2.bytesToString(r3) : e4.bytesToHex(r3);
      };
    })();
  }, 285(t2, e3, n2) {
    var r2 = n2(2);
    t2.exports = function(t3, e4) {
      if (!t3) return [];
      var n3 = null == (e4 = e4 || {}).max ? 1 / 0 : e4.max;
      return "{}" === t3.substr(0, 2) && (t3 = "\\{\\}" + t3.substr(2)), m2((function(t4) {
        return t4.split("\\\\").join(i2).split("\\{").join(s2).split("\\}").join(o2).split("\\,").join(a2).split("\\.").join(h2);
      })(t3), n3, true).map(u2);
    };
    var i2 = "\0SLASH" + Math.random() + "\0", s2 = "\0OPEN" + Math.random() + "\0", o2 = "\0CLOSE" + Math.random() + "\0", a2 = "\0COMMA" + Math.random() + "\0", h2 = "\0PERIOD" + Math.random() + "\0";
    function l2(t3) {
      return parseInt(t3, 10) == t3 ? parseInt(t3, 10) : t3.charCodeAt(0);
    }
    function u2(t3) {
      return t3.split(i2).join("\\").split(s2).join("{").split(o2).join("}").split(a2).join(",").split(h2).join(".");
    }
    function c2(t3) {
      if (!t3) return [""];
      var e4 = [], n3 = r2("{", "}", t3);
      if (!n3) return t3.split(",");
      var i3 = n3.pre, s3 = n3.body, o3 = n3.post, a3 = i3.split(",");
      a3[a3.length - 1] += "{" + s3 + "}";
      var h3 = c2(o3);
      return o3.length && (a3[a3.length - 1] += h3.shift(), a3.push.apply(a3, h3)), e4.push.apply(e4, a3), e4;
    }
    function p2(t3) {
      return "{" + t3 + "}";
    }
    function f(t3) {
      return /^-?0\d/.test(t3);
    }
    function d2(t3, e4) {
      return t3 <= e4;
    }
    function g(t3, e4) {
      return t3 >= e4;
    }
    function m2(t3, e4, n3) {
      var i3 = [], s3 = r2("{", "}", t3);
      if (!s3) return [t3];
      var a3 = s3.pre, h3 = s3.post.length ? m2(s3.post, e4, false) : [""];
      if (/\$$/.test(s3.pre)) for (var u3 = 0; u3 < h3.length && u3 < e4; u3++) {
        var y2 = a3 + "{" + s3.body + "}" + h3[u3];
        i3.push(y2);
      }
      else {
        var b2, v2, w2 = /^-?\d+\.\.-?\d+(?:\.\.-?\d+)?$/.test(s3.body), x2 = /^[a-zA-Z]\.\.[a-zA-Z](?:\.\.-?\d+)?$/.test(s3.body), N2 = w2 || x2, E = s3.body.indexOf(",") >= 0;
        if (!N2 && !E) return s3.post.match(/,(?!,).*\}/) ? m2(t3 = s3.pre + "{" + s3.body + o2 + s3.post, e4, true) : [t3];
        if (N2) b2 = s3.body.split(/\.\./);
        else if (1 === (b2 = c2(s3.body)).length && 1 === (b2 = m2(b2[0], e4, false).map(p2)).length) return h3.map((function(t4) {
          return s3.pre + b2[0] + t4;
        }));
        if (N2) {
          var A2 = l2(b2[0]), S2 = l2(b2[1]), P2 = Math.max(b2[0].length, b2[1].length), T2 = 3 == b2.length ? Math.max(Math.abs(l2(b2[2])), 1) : 1, O2 = d2;
          S2 < A2 && (T2 *= -1, O2 = g);
          var C2 = b2.some(f);
          v2 = [];
          for (var _2 = A2; O2(_2, S2); _2 += T2) {
            var $2;
            if (x2) "\\" === ($2 = String.fromCharCode(_2)) && ($2 = "");
            else if ($2 = String(_2), C2) {
              var j2 = P2 - $2.length;
              if (j2 > 0) {
                var I2 = new Array(j2 + 1).join("0");
                $2 = _2 < 0 ? "-" + I2 + $2.slice(1) : I2 + $2;
              }
            }
            v2.push($2);
          }
        } else {
          v2 = [];
          for (var M2 = 0; M2 < b2.length; M2++) v2.push.apply(v2, m2(b2[M2], e4, false));
        }
        for (M2 = 0; M2 < v2.length; M2++) for (u3 = 0; u3 < h3.length && i3.length < e4; u3++) y2 = a3 + v2[M2] + h3[u3], (!n3 || N2 || y2) && i3.push(y2);
      }
      return i3;
    }
  }, 829(t2) {
    function e3(t3) {
      return e3 = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(t4) {
        return typeof t4;
      } : function(t4) {
        return t4 && "function" == typeof Symbol && t4.constructor === Symbol && t4 !== Symbol.prototype ? "symbol" : typeof t4;
      }, e3(t3);
    }
    function n2(t3) {
      var e4 = "function" == typeof Map ? /* @__PURE__ */ new Map() : void 0;
      return n2 = function(t4) {
        if (null === t4 || (n3 = t4, -1 === Function.toString.call(n3).indexOf("[native code]"))) return t4;
        var n3;
        if ("function" != typeof t4) throw new TypeError("Super expression must either be null or a function");
        if (void 0 !== e4) {
          if (e4.has(t4)) return e4.get(t4);
          e4.set(t4, o3);
        }
        function o3() {
          return r2(t4, arguments, s2(this).constructor);
        }
        return o3.prototype = Object.create(t4.prototype, { constructor: { value: o3, enumerable: false, writable: true, configurable: true } }), i2(o3, t4);
      }, n2(t3);
    }
    function r2(t3, e4, n3) {
      return r2 = (function() {
        if ("undefined" == typeof Reflect || !Reflect.construct) return false;
        if (Reflect.construct.sham) return false;
        if ("function" == typeof Proxy) return true;
        try {
          return Date.prototype.toString.call(Reflect.construct(Date, [], (function() {
          }))), true;
        } catch (t4) {
          return false;
        }
      })() ? Reflect.construct : function(t4, e5, n4) {
        var r3 = [null];
        r3.push.apply(r3, e5);
        var s3 = new (Function.bind.apply(t4, r3))();
        return n4 && i2(s3, n4.prototype), s3;
      }, r2.apply(null, arguments);
    }
    function i2(t3, e4) {
      return i2 = Object.setPrototypeOf || function(t4, e5) {
        return t4.__proto__ = e5, t4;
      }, i2(t3, e4);
    }
    function s2(t3) {
      return s2 = Object.setPrototypeOf ? Object.getPrototypeOf : function(t4) {
        return t4.__proto__ || Object.getPrototypeOf(t4);
      }, s2(t3);
    }
    var o2 = (function(t3) {
      function n3(t4) {
        var r3;
        return (function(t5, e4) {
          if (!(t5 instanceof e4)) throw new TypeError("Cannot call a class as a function");
        })(this, n3), (r3 = (function(t5, n4) {
          return !n4 || "object" !== e3(n4) && "function" != typeof n4 ? (function(t6) {
            if (void 0 === t6) throw new ReferenceError("this hasn't been initialised - super() hasn't been called");
            return t6;
          })(t5) : n4;
        })(this, s2(n3).call(this, t4))).name = "ObjectPrototypeMutationError", r3;
      }
      return (function(t4, e4) {
        if ("function" != typeof e4 && null !== e4) throw new TypeError("Super expression must either be null or a function");
        t4.prototype = Object.create(e4 && e4.prototype, { constructor: { value: t4, writable: true, configurable: true } }), e4 && i2(t4, e4);
      })(n3, t3), n3;
    })(n2(Error));
    function a2(t3, n3) {
      for (var r3 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : function() {
      }, i3 = n3.split("."), s3 = i3.length, o3 = function(e4) {
        var n4 = i3[e4];
        if (!t3) return { v: void 0 };
        if ("+" === n4) {
          if (Array.isArray(t3)) return { v: t3.map((function(n5, s5) {
            var o4 = i3.slice(e4 + 1);
            return o4.length > 0 ? a2(n5, o4.join("."), r3) : r3(t3, s5, i3, e4);
          })) };
          var s4 = i3.slice(0, e4).join(".");
          throw new Error("Object at wildcard (".concat(s4, ") is not an array"));
        }
        t3 = r3(t3, n4, i3, e4);
      }, h3 = 0; h3 < s3; h3++) {
        var l2 = o3(h3);
        if ("object" === e3(l2)) return l2.v;
      }
      return t3;
    }
    function h2(t3, e4) {
      return t3.length === e4 + 1;
    }
    t2.exports = { set: function(t3, n3, r3) {
      if ("object" != e3(t3) || null === t3) return t3;
      if (void 0 === n3) return t3;
      if ("number" == typeof n3) return t3[n3] = r3, t3[n3];
      try {
        return a2(t3, n3, (function(t4, e4, n4, i3) {
          if (t4 === Reflect.getPrototypeOf({})) throw new o2("Attempting to mutate Object.prototype");
          if (!t4[e4]) {
            var s3 = Number.isInteger(Number(n4[i3 + 1])), a3 = "+" === n4[i3 + 1];
            t4[e4] = s3 || a3 ? [] : {};
          }
          return h2(n4, i3) && (t4[e4] = r3), t4[e4];
        }));
      } catch (e4) {
        if (e4 instanceof o2) throw e4;
        return t3;
      }
    }, get: function(t3, n3) {
      if ("object" != e3(t3) || null === t3) return t3;
      if (void 0 === n3) return t3;
      if ("number" == typeof n3) return t3[n3];
      try {
        return a2(t3, n3, (function(t4, e4) {
          return t4[e4];
        }));
      } catch (e4) {
        return t3;
      }
    }, has: function(t3, n3) {
      var r3 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
      if ("object" != e3(t3) || null === t3) return false;
      if (void 0 === n3) return false;
      if ("number" == typeof n3) return n3 in t3;
      try {
        var i3 = false;
        return a2(t3, n3, (function(t4, e4, n4, s3) {
          if (!h2(n4, s3)) return t4 && t4[e4];
          i3 = r3.own ? t4.hasOwnProperty(e4) : e4 in t4;
        })), i3;
      } catch (t4) {
        return false;
      }
    }, hasOwn: function(t3, e4, n3) {
      return this.has(t3, e4, n3 || { own: true });
    }, isIn: function(t3, n3, r3) {
      var i3 = arguments.length > 3 && void 0 !== arguments[3] ? arguments[3] : {};
      if ("object" != e3(t3) || null === t3) return false;
      if (void 0 === n3) return false;
      try {
        var s3 = false, o3 = false;
        return a2(t3, n3, (function(t4, n4, i4, a3) {
          return s3 = s3 || t4 === r3 || !!t4 && t4[n4] === r3, o3 = h2(i4, a3) && "object" === e3(t4) && n4 in t4, t4 && t4[n4];
        })), i3.validPath ? s3 && o3 : s3;
      } catch (t4) {
        return false;
      }
    }, ObjectPrototypeMutationError: o2 };
  }, 47(t2, e3, n2) {
    var r2 = n2(410), i2 = function(t3) {
      return "string" == typeof t3;
    };
    function s2(t3, e4) {
      for (var n3 = [], r3 = 0; r3 < t3.length; r3++) {
        var i3 = t3[r3];
        i3 && "." !== i3 && (".." === i3 ? n3.length && ".." !== n3[n3.length - 1] ? n3.pop() : e4 && n3.push("..") : n3.push(i3));
      }
      return n3;
    }
    var o2 = /^(\/?|)([\s\S]*?)((?:\.{1,2}|[^\/]+?|)(\.[^.\/]*|))(?:[\/]*)$/, a2 = {};
    function h2(t3) {
      return o2.exec(t3).slice(1);
    }
    a2.resolve = function() {
      for (var t3 = "", e4 = false, n3 = arguments.length - 1; n3 >= -1 && !e4; n3--) {
        var r3 = n3 >= 0 ? arguments[n3] : process.cwd();
        if (!i2(r3)) throw new TypeError("Arguments to path.resolve must be strings");
        r3 && (t3 = r3 + "/" + t3, e4 = "/" === r3.charAt(0));
      }
      return (e4 ? "/" : "") + (t3 = s2(t3.split("/"), !e4).join("/")) || ".";
    }, a2.normalize = function(t3) {
      var e4 = a2.isAbsolute(t3), n3 = "/" === t3.substr(-1);
      return (t3 = s2(t3.split("/"), !e4).join("/")) || e4 || (t3 = "."), t3 && n3 && (t3 += "/"), (e4 ? "/" : "") + t3;
    }, a2.isAbsolute = function(t3) {
      return "/" === t3.charAt(0);
    }, a2.join = function() {
      for (var t3 = "", e4 = 0; e4 < arguments.length; e4++) {
        var n3 = arguments[e4];
        if (!i2(n3)) throw new TypeError("Arguments to path.join must be strings");
        n3 && (t3 += t3 ? "/" + n3 : n3);
      }
      return a2.normalize(t3);
    }, a2.relative = function(t3, e4) {
      function n3(t4) {
        for (var e5 = 0; e5 < t4.length && "" === t4[e5]; e5++) ;
        for (var n4 = t4.length - 1; n4 >= 0 && "" === t4[n4]; n4--) ;
        return e5 > n4 ? [] : t4.slice(e5, n4 + 1);
      }
      t3 = a2.resolve(t3).substr(1), e4 = a2.resolve(e4).substr(1);
      for (var r3 = n3(t3.split("/")), i3 = n3(e4.split("/")), s3 = Math.min(r3.length, i3.length), o3 = s3, h3 = 0; h3 < s3; h3++) if (r3[h3] !== i3[h3]) {
        o3 = h3;
        break;
      }
      var l2 = [];
      for (h3 = o3; h3 < r3.length; h3++) l2.push("..");
      return (l2 = l2.concat(i3.slice(o3))).join("/");
    }, a2._makeLong = function(t3) {
      return t3;
    }, a2.dirname = function(t3) {
      var e4 = h2(t3), n3 = e4[0], r3 = e4[1];
      return n3 || r3 ? (r3 && (r3 = r3.substr(0, r3.length - 1)), n3 + r3) : ".";
    }, a2.basename = function(t3, e4) {
      var n3 = h2(t3)[2];
      return e4 && n3.substr(-1 * e4.length) === e4 && (n3 = n3.substr(0, n3.length - e4.length)), n3;
    }, a2.extname = function(t3) {
      return h2(t3)[3];
    }, a2.format = function(t3) {
      if (!r2.isObject(t3)) throw new TypeError("Parameter 'pathObject' must be an object, not " + typeof t3);
      var e4 = t3.root || "";
      if (!i2(e4)) throw new TypeError("'pathObject.root' must be a string or undefined, not " + typeof t3.root);
      return (t3.dir ? t3.dir + a2.sep : "") + (t3.base || "");
    }, a2.parse = function(t3) {
      if (!i2(t3)) throw new TypeError("Parameter 'pathString' must be a string, not " + typeof t3);
      var e4 = h2(t3);
      if (!e4 || 4 !== e4.length) throw new TypeError("Invalid path '" + t3 + "'");
      return e4[1] = e4[1] || "", e4[2] = e4[2] || "", e4[3] = e4[3] || "", { root: e4[0], dir: e4[0] + e4[1].slice(0, e4[1].length - 1), base: e4[2], ext: e4[3], name: e4[2].slice(0, e4[2].length - e4[3].length) };
    }, a2.sep = "/", a2.delimiter = ":", t2.exports = a2;
  }, 647(t2, e3) {
    var n2 = Object.prototype.hasOwnProperty;
    function r2(t3) {
      try {
        return decodeURIComponent(t3.replace(/\+/g, " "));
      } catch (t4) {
        return null;
      }
    }
    function i2(t3) {
      try {
        return encodeURIComponent(t3);
      } catch (t4) {
        return null;
      }
    }
    e3.stringify = function(t3, e4) {
      e4 = e4 || "";
      var r3, s2, o2 = [];
      for (s2 in "string" != typeof e4 && (e4 = "?"), t3) if (n2.call(t3, s2)) {
        if ((r3 = t3[s2]) || null != r3 && !isNaN(r3) || (r3 = ""), s2 = i2(s2), r3 = i2(r3), null === s2 || null === r3) continue;
        o2.push(s2 + "=" + r3);
      }
      return o2.length ? e4 + o2.join("&") : "";
    }, e3.parse = function(t3) {
      for (var e4, n3 = /([^=?#&]+)=?([^&]*)/g, i3 = {}; e4 = n3.exec(t3); ) {
        var s2 = r2(e4[1]), o2 = r2(e4[2]);
        null === s2 || null === o2 || s2 in i3 || (i3[s2] = o2);
      }
      return i3;
    };
  }, 670(t2) {
    t2.exports = function(t3, e3) {
      if (e3 = e3.split(":")[0], !(t3 = +t3)) return false;
      switch (e3) {
        case "http":
        case "ws":
          return 80 !== t3;
        case "https":
        case "wss":
          return 443 !== t3;
        case "ftp":
          return 21 !== t3;
        case "gopher":
          return 70 !== t3;
        case "file":
          return false;
      }
      return 0 !== t3;
    };
  }, 737(t2, e3, n2) {
    var r2 = n2(670), i2 = n2(647), s2 = /^[\x00-\x20\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/, o2 = /[\n\r\t]/g, a2 = /^[A-Za-z][A-Za-z0-9+-.]*:\/\//, h2 = /:\d+$/, l2 = /^([a-z][a-z0-9.+-]*:)?(\/\/)?([\\/]+)?([\S\s]*)/i, u2 = /^[a-zA-Z]:/;
    function c2(t3) {
      return (t3 || "").toString().replace(s2, "");
    }
    var p2 = [["#", "hash"], ["?", "query"], function(t3, e4) {
      return g(e4.protocol) ? t3.replace(/\\/g, "/") : t3;
    }, ["/", "pathname"], ["@", "auth", 1], [NaN, "host", void 0, 1, 1], [/:(\d*)$/, "port", void 0, 1], [NaN, "hostname", void 0, 1, 1]], f = { hash: 1, query: 1 };
    function d2(t3) {
      var e4, n3 = ("undefined" != typeof window ? window : "undefined" != typeof global ? global : "undefined" != typeof self ? self : {}).location || {}, r3 = {}, i3 = typeof (t3 = t3 || n3);
      if ("blob:" === t3.protocol) r3 = new y2(unescape(t3.pathname), {});
      else if ("string" === i3) for (e4 in r3 = new y2(t3, {}), f) delete r3[e4];
      else if ("object" === i3) {
        for (e4 in t3) e4 in f || (r3[e4] = t3[e4]);
        void 0 === r3.slashes && (r3.slashes = a2.test(t3.href));
      }
      return r3;
    }
    function g(t3) {
      return "file:" === t3 || "ftp:" === t3 || "http:" === t3 || "https:" === t3 || "ws:" === t3 || "wss:" === t3;
    }
    function m2(t3, e4) {
      t3 = (t3 = c2(t3)).replace(o2, ""), e4 = e4 || {};
      var n3, r3 = l2.exec(t3), i3 = r3[1] ? r3[1].toLowerCase() : "", s3 = !!r3[2], a3 = !!r3[3], h3 = 0;
      return s3 ? a3 ? (n3 = r3[2] + r3[3] + r3[4], h3 = r3[2].length + r3[3].length) : (n3 = r3[2] + r3[4], h3 = r3[2].length) : a3 ? (n3 = r3[3] + r3[4], h3 = r3[3].length) : n3 = r3[4], "file:" === i3 ? h3 >= 2 && (n3 = n3.slice(2)) : g(i3) ? n3 = r3[4] : i3 ? s3 && (n3 = n3.slice(2)) : h3 >= 2 && g(e4.protocol) && (n3 = r3[4]), { protocol: i3, slashes: s3 || g(i3), slashesCount: h3, rest: n3 };
    }
    function y2(t3, e4, n3) {
      if (t3 = (t3 = c2(t3)).replace(o2, ""), !(this instanceof y2)) return new y2(t3, e4, n3);
      var s3, a3, h3, l3, f2, b2, v2 = p2.slice(), w2 = typeof e4, x2 = this, N2 = 0;
      for ("object" !== w2 && "string" !== w2 && (n3 = e4, e4 = null), n3 && "function" != typeof n3 && (n3 = i2.parse), s3 = !(a3 = m2(t3 || "", e4 = d2(e4))).protocol && !a3.slashes, x2.slashes = a3.slashes || s3 && e4.slashes, x2.protocol = a3.protocol || e4.protocol || "", t3 = a3.rest, ("file:" === a3.protocol && (2 !== a3.slashesCount || u2.test(t3)) || !a3.slashes && (a3.protocol || a3.slashesCount < 2 || !g(x2.protocol))) && (v2[3] = [/(.*)/, "pathname"]); N2 < v2.length; N2++) "function" != typeof (l3 = v2[N2]) ? (h3 = l3[0], b2 = l3[1], h3 != h3 ? x2[b2] = t3 : "string" == typeof h3 ? ~(f2 = "@" === h3 ? t3.lastIndexOf(h3) : t3.indexOf(h3)) && ("number" == typeof l3[2] ? (x2[b2] = t3.slice(0, f2), t3 = t3.slice(f2 + l3[2])) : (x2[b2] = t3.slice(f2), t3 = t3.slice(0, f2))) : (f2 = h3.exec(t3)) && (x2[b2] = f2[1], t3 = t3.slice(0, f2.index)), x2[b2] = x2[b2] || s3 && l3[3] && e4[b2] || "", l3[4] && (x2[b2] = x2[b2].toLowerCase())) : t3 = l3(t3, x2);
      n3 && (x2.query = n3(x2.query)), s3 && e4.slashes && "/" !== x2.pathname.charAt(0) && ("" !== x2.pathname || "" !== e4.pathname) && (x2.pathname = (function(t4, e5) {
        if ("" === t4) return e5;
        for (var n4 = (e5 || "/").split("/").slice(0, -1).concat(t4.split("/")), r3 = n4.length, i3 = n4[r3 - 1], s4 = false, o3 = 0; r3--; ) "." === n4[r3] ? n4.splice(r3, 1) : ".." === n4[r3] ? (n4.splice(r3, 1), o3++) : o3 && (0 === r3 && (s4 = true), n4.splice(r3, 1), o3--);
        return s4 && n4.unshift(""), "." !== i3 && ".." !== i3 || n4.push(""), n4.join("/");
      })(x2.pathname, e4.pathname)), "/" !== x2.pathname.charAt(0) && g(x2.protocol) && (x2.pathname = "/" + x2.pathname), r2(x2.port, x2.protocol) || (x2.host = x2.hostname, x2.port = ""), x2.username = x2.password = "", x2.auth && (~(f2 = x2.auth.indexOf(":")) ? (x2.username = x2.auth.slice(0, f2), x2.username = encodeURIComponent(decodeURIComponent(x2.username)), x2.password = x2.auth.slice(f2 + 1), x2.password = encodeURIComponent(decodeURIComponent(x2.password))) : x2.username = encodeURIComponent(decodeURIComponent(x2.auth)), x2.auth = x2.password ? x2.username + ":" + x2.password : x2.username), x2.origin = "file:" !== x2.protocol && g(x2.protocol) && x2.host ? x2.protocol + "//" + x2.host : "null", x2.href = x2.toString();
    }
    y2.prototype = { set: function(t3, e4, n3) {
      var s3 = this;
      switch (t3) {
        case "query":
          "string" == typeof e4 && e4.length && (e4 = (n3 || i2.parse)(e4)), s3[t3] = e4;
          break;
        case "port":
          s3[t3] = e4, r2(e4, s3.protocol) ? e4 && (s3.host = s3.hostname + ":" + e4) : (s3.host = s3.hostname, s3[t3] = "");
          break;
        case "hostname":
          s3[t3] = e4, s3.port && (e4 += ":" + s3.port), s3.host = e4;
          break;
        case "host":
          s3[t3] = e4, h2.test(e4) ? (e4 = e4.split(":"), s3.port = e4.pop(), s3.hostname = e4.join(":")) : (s3.hostname = e4, s3.port = "");
          break;
        case "protocol":
          s3.protocol = e4.toLowerCase(), s3.slashes = !n3;
          break;
        case "pathname":
        case "hash":
          if (e4) {
            var o3 = "pathname" === t3 ? "/" : "#";
            s3[t3] = e4.charAt(0) !== o3 ? o3 + e4 : e4;
          } else s3[t3] = e4;
          break;
        case "username":
        case "password":
          s3[t3] = encodeURIComponent(e4);
          break;
        case "auth":
          var a3 = e4.indexOf(":");
          ~a3 ? (s3.username = e4.slice(0, a3), s3.username = encodeURIComponent(decodeURIComponent(s3.username)), s3.password = e4.slice(a3 + 1), s3.password = encodeURIComponent(decodeURIComponent(s3.password))) : s3.username = encodeURIComponent(decodeURIComponent(e4));
      }
      for (var l3 = 0; l3 < p2.length; l3++) {
        var u3 = p2[l3];
        u3[4] && (s3[u3[1]] = s3[u3[1]].toLowerCase());
      }
      return s3.auth = s3.password ? s3.username + ":" + s3.password : s3.username, s3.origin = "file:" !== s3.protocol && g(s3.protocol) && s3.host ? s3.protocol + "//" + s3.host : "null", s3.href = s3.toString(), s3;
    }, toString: function(t3) {
      t3 && "function" == typeof t3 || (t3 = i2.stringify);
      var e4, n3 = this, r3 = n3.host, s3 = n3.protocol;
      s3 && ":" !== s3.charAt(s3.length - 1) && (s3 += ":");
      var o3 = s3 + (n3.protocol && n3.slashes || g(n3.protocol) ? "//" : "");
      return n3.username ? (o3 += n3.username, n3.password && (o3 += ":" + n3.password), o3 += "@") : n3.password ? (o3 += ":" + n3.password, o3 += "@") : "file:" !== n3.protocol && g(n3.protocol) && !r3 && "/" !== n3.pathname && (o3 += "@"), (":" === r3[r3.length - 1] || h2.test(n3.hostname) && !n3.port) && (r3 += ":"), o3 += r3 + n3.pathname, (e4 = "object" == typeof n3.query ? t3(n3.query) : n3.query) && (o3 += "?" !== e4.charAt(0) ? "?" + e4 : e4), n3.hash && (o3 += n3.hash), o3;
    } }, y2.extractProtocol = m2, y2.location = d2, y2.trimLeft = c2, y2.qs = i2, t2.exports = y2;
  }, 410() {
  }, 388() {
  }, 805() {
  }, 345() {
  }, 800() {
  } };
  var e = {};
  function n(r2) {
    var i2 = e[r2];
    if (void 0 !== i2) return i2.exports;
    var s2 = e[r2] = { id: r2, loaded: false, exports: {} };
    return t[r2].call(s2.exports, s2, s2.exports, n), s2.loaded = true, s2.exports;
  }
  n.n = (t2) => {
    var e3 = t2 && t2.__esModule ? () => t2.default : () => t2;
    return n.d(e3, { a: e3 }), e3;
  }, n.d = (t2, e3) => {
    for (var r2 in e3) n.o(e3, r2) && !n.o(t2, r2) && Object.defineProperty(t2, r2, { enumerable: true, get: e3[r2] });
  }, n.o = (t2, e3) => Object.prototype.hasOwnProperty.call(t2, e3), n.nmd = (t2) => (t2.paths = [], t2.children || (t2.children = []), t2);
  var r = n(737);
  var i = n.n(r);
  function s(t2) {
    if (!o(t2)) throw new Error("Parameter was not an error");
  }
  function o(t2) {
    return !!t2 && "object" == typeof t2 && "[object Error]" === (e3 = t2, Object.prototype.toString.call(e3)) || t2 instanceof Error;
    var e3;
  }
  var a = class _a2 extends Error {
    constructor(t2, e3) {
      const n2 = [...arguments], { options: r2, shortMessage: i2 } = (function(t3) {
        let e4, n3 = "";
        if (0 === t3.length) e4 = {};
        else if (o(t3[0])) e4 = { cause: t3[0] }, n3 = t3.slice(1).join(" ") || "";
        else if (t3[0] && "object" == typeof t3[0]) e4 = Object.assign({}, t3[0]), n3 = t3.slice(1).join(" ") || "";
        else {
          if ("string" != typeof t3[0]) throw new Error("Invalid arguments passed to Layerr");
          e4 = {}, n3 = n3 = t3.join(" ") || "";
        }
        return { options: e4, shortMessage: n3 };
      })(n2);
      let s2 = i2;
      if (r2.cause && (s2 = `${s2}: ${r2.cause.message}`), super(s2), this.message = s2, r2.name && "string" == typeof r2.name ? this.name = r2.name : this.name = "Layerr", r2.cause && Object.defineProperty(this, "_cause", { value: r2.cause }), Object.defineProperty(this, "_info", { value: {} }), r2.info && "object" == typeof r2.info && Object.assign(this._info, r2.info), Error.captureStackTrace) {
        const t3 = r2.constructorOpt || this.constructor;
        Error.captureStackTrace(this, t3);
      }
    }
    static cause(t2) {
      return s(t2), t2._cause && o(t2._cause) ? t2._cause : null;
    }
    static fullStack(t2) {
      s(t2);
      const e3 = _a2.cause(t2);
      return e3 ? `${t2.stack}
caused by: ${_a2.fullStack(e3)}` : t2.stack ?? "";
    }
    static info(t2) {
      s(t2);
      const e3 = {}, n2 = _a2.cause(t2);
      return n2 && Object.assign(e3, _a2.info(n2)), t2._info && Object.assign(e3, t2._info), e3;
    }
    toString() {
      let t2 = this.name || this.constructor.name || this.constructor.prototype.name;
      return this.message && (t2 = `${t2}: ${this.message}`), t2;
    }
  };
  var h = n(47);
  var l = n.n(h);
  var u = "__PATH_SEPARATOR_POSIX__";
  var c = "__PATH_SEPARATOR_WINDOWS__";
  function p(t2) {
    try {
      const e3 = t2.replace(/\//g, u).replace(/\\\\/g, c);
      return encodeURIComponent(e3).split(c).join("\\\\").split(u).join("/");
    } catch (t3) {
      throw new a(t3, "Failed encoding path");
    }
  }
  function d(t2) {
    let e3 = t2;
    return "/" !== e3[0] && (e3 = "/" + e3), /^.+\/$/.test(e3) && (e3 = e3.substr(0, e3.length - 1)), e3;
  }
  function m() {
    for (var t2 = arguments.length, e3 = new Array(t2), n2 = 0; n2 < t2; n2++) e3[n2] = arguments[n2];
    return (function() {
      return (function(t3) {
        var e4 = [];
        if (0 === t3.length) return "";
        if ("string" != typeof t3[0]) throw new TypeError("Url must be a string. Received " + t3[0]);
        if (t3[0].match(/^[^/:]+:\/*$/) && t3.length > 1) {
          var n3 = t3.shift();
          t3[0] = n3 + t3[0];
        }
        t3[0].match(/^file:\/\/\//) ? t3[0] = t3[0].replace(/^([^/:]+):\/*/, "$1:///") : t3[0] = t3[0].replace(/^([^/:]+):\/*/, "$1://");
        for (var r2 = 0; r2 < t3.length; r2++) {
          var i2 = t3[r2];
          if ("string" != typeof i2) throw new TypeError("Url must be a string. Received " + i2);
          "" !== i2 && (r2 > 0 && (i2 = i2.replace(/^[\/]+/, "")), i2 = r2 < t3.length - 1 ? i2.replace(/[\/]+$/, "") : i2.replace(/[\/]+$/, "/"), e4.push(i2));
        }
        var s2 = e4.join("/"), o2 = (s2 = s2.replace(/\/(\?|&|#[^!])/g, "$1")).split("?");
        return o2.shift() + (o2.length > 0 ? "?" : "") + o2.join("&");
      })("object" == typeof arguments[0] ? arguments[0] : [].slice.call(arguments));
    })(e3.reduce(((t3, e4, n3) => ((0 === n3 || "/" !== e4 || "/" === e4 && "/" !== t3[t3.length - 1]) && t3.push(e4), t3)), []));
  }
  var y = n(542);
  var b = n.n(y);
  function v(t2, e3) {
    const n2 = t2.url.replace("//", ""), r2 = -1 == n2.indexOf("/") ? "/" : n2.slice(n2.indexOf("/")), i2 = t2.method ? t2.method.toUpperCase() : "GET", s2 = !!/(^|,)\s*auth\s*($|,)/.test(e3.qop) && "auth", o2 = `00000000${e3.nc}`.slice(-8), a2 = (function(t3, e4, n3, r3, i3, s3, o3) {
      const a3 = o3 || b()(`${e4}:${n3}:${r3}`);
      return t3 && "md5-sess" === t3.toLowerCase() ? b()(`${a3}:${i3}:${s3}`) : a3;
    })(e3.algorithm, e3.username, e3.realm, e3.password, e3.nonce, e3.cnonce, e3.ha1), h2 = b()(`${i2}:${r2}`), l2 = s2 ? b()(`${a2}:${e3.nonce}:${o2}:${e3.cnonce}:${s2}:${h2}`) : b()(`${a2}:${e3.nonce}:${h2}`), u2 = { username: e3.username, realm: e3.realm, nonce: e3.nonce, uri: r2, qop: s2, response: l2, nc: o2, cnonce: e3.cnonce, algorithm: e3.algorithm, opaque: e3.opaque }, c2 = [];
    for (const t3 in u2) u2[t3] && ("qop" === t3 || "nc" === t3 || "algorithm" === t3 ? c2.push(`${t3}=${u2[t3]}`) : c2.push(`${t3}="${u2[t3]}"`));
    return `Digest ${c2.join(", ")}`;
  }
  function w(t2) {
    return "digest" === (t2.headers && t2.headers.get("www-authenticate") || "").split(/\s/)[0].toLowerCase();
  }
  var x = n(101);
  var N = n.n(x);
  function A(t2, e3) {
    var n2;
    return `Basic ${n2 = `${t2}:${e3}`, N().encode(n2)}`;
  }
  var S = "undefined" != typeof WorkerGlobalScope && self instanceof WorkerGlobalScope ? self : "undefined" != typeof window ? window : globalThis;
  var P = S.fetch.bind(S);
  var T = (S.Headers, S.Request);
  var O = S.Response;
  var C = (function(t2) {
    return t2.Auto = "auto", t2.Digest = "digest", t2.None = "none", t2.Password = "password", t2.Token = "token", t2;
  })({});
  var _ = (function(t2) {
    return t2.DataTypeNoLength = "data-type-no-length", t2.InvalidAuthType = "invalid-auth-type", t2.InvalidOutputFormat = "invalid-output-format", t2.LinkUnsupportedAuthType = "link-unsupported-auth", t2.InvalidUpdateRange = "invalid-update-range", t2.NotSupported = "not-supported", t2;
  })({});
  function $(t2, e3, n2, r2, i2) {
    switch (t2.authType) {
      case C.Auto:
        e3 && n2 && (t2.headers.Authorization = A(e3, n2));
        break;
      case C.Digest:
        t2.digest = /* @__PURE__ */ (function(t3, e4, n3) {
          return { username: t3, password: e4, ha1: n3, nc: 0, algorithm: "md5", hasDigestAuth: false };
        })(e3, n2, i2);
        break;
      case C.None:
        break;
      case C.Password:
        t2.headers.Authorization = A(e3, n2);
        break;
      case C.Token:
        t2.headers.Authorization = `${(s2 = r2).token_type} ${s2.access_token}`;
        break;
      default:
        throw new a({ info: { code: _.InvalidAuthType } }, `Invalid auth type: ${t2.authType}`);
    }
    var s2;
  }
  n(345), n(800);
  var j = "@@HOTPATCHER";
  var I = () => {
  };
  function M(t2) {
    return { original: t2, methods: [t2], final: false };
  }
  var R = class {
    constructor() {
      this._configuration = { registry: {}, getEmptyAction: "null" }, this.__type__ = j;
    }
    get configuration() {
      return this._configuration;
    }
    get getEmptyAction() {
      return this.configuration.getEmptyAction;
    }
    set getEmptyAction(t2) {
      this.configuration.getEmptyAction = t2;
    }
    control(t2) {
      let e3 = arguments.length > 1 && void 0 !== arguments[1] && arguments[1];
      if (!t2 || t2.__type__ !== j) throw new Error("Failed taking control of target HotPatcher instance: Invalid type or object");
      return Object.keys(t2.configuration.registry).forEach(((n2) => {
        this.configuration.registry.hasOwnProperty(n2) ? e3 && (this.configuration.registry[n2] = Object.assign({}, t2.configuration.registry[n2])) : this.configuration.registry[n2] = Object.assign({}, t2.configuration.registry[n2]);
      })), t2._configuration = this.configuration, this;
    }
    execute(t2) {
      const e3 = this.get(t2) || I;
      for (var n2 = arguments.length, r2 = new Array(n2 > 1 ? n2 - 1 : 0), i2 = 1; i2 < n2; i2++) r2[i2 - 1] = arguments[i2];
      return e3(...r2);
    }
    get(t2) {
      const e3 = this.configuration.registry[t2];
      if (!e3) switch (this.getEmptyAction) {
        case "null":
          return null;
        case "throw":
          throw new Error(`Failed handling method request: No method provided for override: ${t2}`);
        default:
          throw new Error(`Failed handling request which resulted in an empty method: Invalid empty-action specified: ${this.getEmptyAction}`);
      }
      return (function() {
        for (var t3 = arguments.length, e4 = new Array(t3), n2 = 0; n2 < t3; n2++) e4[n2] = arguments[n2];
        if (0 === e4.length) throw new Error("Failed creating sequence: No functions provided");
        return function() {
          for (var t4 = arguments.length, n3 = new Array(t4), r2 = 0; r2 < t4; r2++) n3[r2] = arguments[r2];
          let i2 = n3;
          const s2 = this;
          for (; e4.length > 0; ) i2 = [e4.shift().apply(s2, i2)];
          return i2[0];
        };
      })(...e3.methods);
    }
    isPatched(t2) {
      return !!this.configuration.registry[t2];
    }
    patch(t2, e3) {
      let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
      const { chain: r2 = false } = n2;
      if (this.configuration.registry[t2] && this.configuration.registry[t2].final) throw new Error(`Failed patching '${t2}': Method marked as being final`);
      if ("function" != typeof e3) throw new Error(`Failed patching '${t2}': Provided method is not a function`);
      if (r2) this.configuration.registry[t2] ? this.configuration.registry[t2].methods.push(e3) : this.configuration.registry[t2] = M(e3);
      else if (this.isPatched(t2)) {
        const { original: n3 } = this.configuration.registry[t2];
        this.configuration.registry[t2] = Object.assign(M(e3), { original: n3 });
      } else this.configuration.registry[t2] = M(e3);
      return this;
    }
    patchInline(t2, e3) {
      this.isPatched(t2) || this.patch(t2, e3);
      for (var n2 = arguments.length, r2 = new Array(n2 > 2 ? n2 - 2 : 0), i2 = 2; i2 < n2; i2++) r2[i2 - 2] = arguments[i2];
      return this.execute(t2, ...r2);
    }
    plugin(t2) {
      for (var e3 = arguments.length, n2 = new Array(e3 > 1 ? e3 - 1 : 0), r2 = 1; r2 < e3; r2++) n2[r2 - 1] = arguments[r2];
      return n2.forEach(((e4) => {
        this.patch(t2, e4, { chain: true });
      })), this;
    }
    restore(t2) {
      if (!this.isPatched(t2)) throw new Error(`Failed restoring method: No method present for key: ${t2}`);
      if ("function" != typeof this.configuration.registry[t2].original) throw new Error(`Failed restoring method: Original method not found or of invalid type for key: ${t2}`);
      return this.configuration.registry[t2].methods = [this.configuration.registry[t2].original], this;
    }
    setFinal(t2) {
      if (!this.configuration.registry.hasOwnProperty(t2)) throw new Error(`Failed marking '${t2}' as final: No method found for key`);
      return this.configuration.registry[t2].final = true, this;
    }
  };
  var k = null;
  function L() {
    return k || (k = new R()), k;
  }
  function D(t2) {
    return (function(t3) {
      if ("object" != typeof t3 || null === t3 || "[object Object]" != Object.prototype.toString.call(t3)) return false;
      if (null === Object.getPrototypeOf(t3)) return true;
      let e3 = t3;
      for (; null !== Object.getPrototypeOf(e3); ) e3 = Object.getPrototypeOf(e3);
      return Object.getPrototypeOf(t3) === e3;
    })(t2) ? Object.assign({}, t2) : Object.setPrototypeOf(Object.assign({}, t2), Object.getPrototypeOf(t2));
  }
  function U() {
    for (var t2 = arguments.length, e3 = new Array(t2), n2 = 0; n2 < t2; n2++) e3[n2] = arguments[n2];
    let r2 = null, i2 = [...e3];
    for (; i2.length > 0; ) {
      const t3 = i2.shift();
      r2 = r2 ? F(r2, t3) : D(t3);
    }
    return r2;
  }
  function F(t2, e3) {
    const n2 = D(t2);
    return Object.keys(e3).forEach(((t3) => {
      n2.hasOwnProperty(t3) ? Array.isArray(e3[t3]) ? n2[t3] = Array.isArray(n2[t3]) ? [...n2[t3], ...e3[t3]] : [...e3[t3]] : "object" == typeof e3[t3] && e3[t3] ? n2[t3] = "object" == typeof n2[t3] && n2[t3] ? F(n2[t3], e3[t3]) : D(e3[t3]) : n2[t3] = e3[t3] : n2[t3] = e3[t3];
    })), n2;
  }
  function V(t2) {
    const e3 = {};
    for (const n2 of t2.keys()) e3[n2] = t2.get(n2);
    return e3;
  }
  function W() {
    for (var t2 = arguments.length, e3 = new Array(t2), n2 = 0; n2 < t2; n2++) e3[n2] = arguments[n2];
    if (0 === e3.length) return {};
    const r2 = {};
    return e3.reduce(((t3, e4) => (Object.keys(e4).forEach(((n3) => {
      const i2 = n3.toLowerCase();
      r2.hasOwnProperty(i2) ? t3[r2[i2]] = e4[n3] : (r2[i2] = n3, t3[n3] = e4[n3]);
    })), t3)), {});
  }
  n(805);
  var B = "function" == typeof ArrayBuffer;
  var { toString: G } = Object.prototype;
  function z(t2) {
    return B && (t2 instanceof ArrayBuffer || "[object ArrayBuffer]" === G.call(t2));
  }
  function q(t2) {
    return null != t2 && null != t2.constructor && "function" == typeof t2.constructor.isBuffer && t2.constructor.isBuffer(t2);
  }
  function H(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  }
  function Y(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  var X = H((function(t2) {
    const e3 = t2._digest;
    return delete t2._digest, e3.hasDigestAuth && (t2 = U(t2, { headers: { Authorization: v(t2, e3) } })), Y(Q(t2), (function(n2) {
      let r2 = false;
      return i2 = function(t3) {
        return r2 ? t3 : n2;
      }, (s2 = (function() {
        if (401 == n2.status) return e3.hasDigestAuth = (function(t3, e4) {
          if (!w(t3)) return false;
          const n3 = /([a-z0-9_-]+)=(?:"([^"]+)"|([a-z0-9_-]+))/gi;
          for (; ; ) {
            const r3 = t3.headers && t3.headers.get("www-authenticate") || "", i3 = n3.exec(r3);
            if (!i3) break;
            e4[i3[1]] = i3[2] || i3[3];
          }
          return e4.nc += 1, e4.cnonce = (function() {
            let t4 = "";
            for (let e5 = 0; e5 < 32; ++e5) t4 = `${t4}${"abcdef0123456789"[Math.floor(16 * Math.random())]}`;
            return t4;
          })(), true;
        })(n2, e3), (function() {
          if (e3.hasDigestAuth) return Y(Q(t2 = U(t2, { headers: { Authorization: v(t2, e3) } })), (function(t3) {
            return 401 == t3.status ? e3.hasDigestAuth = false : e3.nc++, r2 = true, t3;
          }));
        })();
        e3.nc++;
      })()) && s2.then ? s2.then(i2) : i2(s2);
      var i2, s2;
    }));
  }));
  var Z = H((function(t2, e3) {
    return Y(Q(t2), (function(n2) {
      return n2.ok ? (e3.authType = C.Password, n2) : 401 == n2.status && w(n2) ? (e3.authType = C.Digest, $(e3, e3.username, e3.password, void 0, void 0), t2._digest = e3.digest, X(t2)) : n2;
    }));
  }));
  var J = H((function(t2, e3) {
    return e3.authType === C.Auto ? Z(t2, e3) : t2._digest ? X(t2) : Q(t2);
  }));
  function K(t2, e3, n2) {
    const r2 = D(t2);
    return r2.headers = W(e3.headers, r2.headers || {}, n2.headers || {}), void 0 !== n2.data && (r2.data = n2.data), n2.signal && (r2.signal = n2.signal), e3.httpAgent && (r2.httpAgent = e3.httpAgent), e3.httpsAgent && (r2.httpsAgent = e3.httpsAgent), e3.digest && (r2._digest = e3.digest), "boolean" == typeof e3.withCredentials && (r2.withCredentials = e3.withCredentials), r2;
  }
  function Q(t2) {
    const e3 = L();
    return e3.patchInline("request", ((t3) => e3.patchInline("fetch", P, t3.url, (function(t4) {
      let e4 = {};
      const n2 = { method: t4.method };
      if (t4.headers && (e4 = W(e4, t4.headers)), void 0 !== t4.data) {
        const [r2, i2] = (function(t5) {
          if ("string" == typeof t5) return [t5, {}];
          if (q(t5)) return [t5, {}];
          if (z(t5)) return [t5, {}];
          if (t5 && "object" == typeof t5) return [JSON.stringify(t5), { "content-type": "application/json" }];
          throw new Error("Unable to convert request body: Unexpected body type: " + typeof t5);
        })(t4.data);
        n2.body = r2, e4 = W(e4, i2);
      }
      return t4.signal && (n2.signal = t4.signal), t4.withCredentials && (n2.credentials = "include"), n2.headers = e4, n2;
    })(t3))), t2);
  }
  var tt = n(285);
  var et = (t2) => {
    if ("string" != typeof t2) throw new TypeError("invalid pattern");
    if (t2.length > 65536) throw new TypeError("pattern is too long");
  };
  var nt = { "[:alnum:]": ["\\p{L}\\p{Nl}\\p{Nd}", true], "[:alpha:]": ["\\p{L}\\p{Nl}", true], "[:ascii:]": ["\\x00-\\x7f", false], "[:blank:]": ["\\p{Zs}\\t", true], "[:cntrl:]": ["\\p{Cc}", true], "[:digit:]": ["\\p{Nd}", true], "[:graph:]": ["\\p{Z}\\p{C}", true, true], "[:lower:]": ["\\p{Ll}", true], "[:print:]": ["\\p{C}", true], "[:punct:]": ["\\p{P}", true], "[:space:]": ["\\p{Z}\\t\\r\\n\\v\\f", true], "[:upper:]": ["\\p{Lu}", true], "[:word:]": ["\\p{L}\\p{Nl}\\p{Nd}\\p{Pc}", true], "[:xdigit:]": ["A-Fa-f0-9", false] };
  var rt = (t2) => t2.replace(/[[\]\\-]/g, "\\$&");
  var it = (t2) => t2.join("");
  var st = (t2, e3) => {
    const n2 = e3;
    if ("[" !== t2.charAt(n2)) throw new Error("not in a brace expression");
    const r2 = [], i2 = [];
    let s2 = n2 + 1, o2 = false, a2 = false, h2 = false, l2 = false, u2 = n2, c2 = "";
    t: for (; s2 < t2.length; ) {
      const e4 = t2.charAt(s2);
      if ("!" !== e4 && "^" !== e4 || s2 !== n2 + 1) {
        if ("]" === e4 && o2 && !h2) {
          u2 = s2 + 1;
          break;
        }
        if (o2 = true, "\\" !== e4 || h2) {
          if ("[" === e4 && !h2) {
            for (const [e5, [o3, h3, l3]] of Object.entries(nt)) if (t2.startsWith(e5, s2)) {
              if (c2) return ["$.", false, t2.length - n2, true];
              s2 += e5.length, l3 ? i2.push(o3) : r2.push(o3), a2 = a2 || h3;
              continue t;
            }
          }
          h2 = false, c2 ? (e4 > c2 ? r2.push(rt(c2) + "-" + rt(e4)) : e4 === c2 && r2.push(rt(e4)), c2 = "", s2++) : t2.startsWith("-]", s2 + 1) ? (r2.push(rt(e4 + "-")), s2 += 2) : t2.startsWith("-", s2 + 1) ? (c2 = e4, s2 += 2) : (r2.push(rt(e4)), s2++);
        } else h2 = true, s2++;
      } else l2 = true, s2++;
    }
    if (u2 < s2) return ["", false, 0, false];
    if (!r2.length && !i2.length) return ["$.", false, t2.length - n2, true];
    if (0 === i2.length && 1 === r2.length && /^\\?.$/.test(r2[0]) && !l2) {
      return [(p2 = 2 === r2[0].length ? r2[0].slice(-1) : r2[0], p2.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&")), false, u2 - n2, false];
    }
    var p2;
    const f = "[" + (l2 ? "^" : "") + it(r2) + "]", d2 = "[" + (l2 ? "" : "^") + it(i2) + "]";
    return [r2.length && i2.length ? "(" + f + "|" + d2 + ")" : r2.length ? f : d2, a2, u2 - n2, true];
  };
  var ot = function(t2) {
    let { windowsPathsNoEscape: e3 = false } = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
    return e3 ? t2.replace(/\[([^\/\\])\]/g, "$1") : t2.replace(/((?!\\).|^)\[([^\/\\])\]/g, "$1$2").replace(/\\([^\/])/g, "$1");
  };
  var at;
  var ht = /* @__PURE__ */ new Set(["!", "?", "+", "*", "@"]);
  var lt = (t2) => ht.has(t2);
  var ut = (t2) => lt(t2.type);
  var ct = /* @__PURE__ */ new Map([["!", ["@"]], ["?", ["?", "@"]], ["@", ["@"]], ["*", ["*", "+", "?", "@"]], ["+", ["+", "@"]]]);
  var pt = /* @__PURE__ */ new Map([["!", ["?"]], ["@", ["?"]], ["+", ["?", "*"]]]);
  var ft = /* @__PURE__ */ new Map([["!", ["?", "@"]], ["?", ["?", "@"]], ["@", ["?", "@"]], ["*", ["*", "+", "?", "@"]], ["+", ["+", "@", "?", "*"]]]);
  var dt = /* @__PURE__ */ new Map([["!", /* @__PURE__ */ new Map([["!", "@"]])], ["?", /* @__PURE__ */ new Map([["*", "*"], ["+", "*"]])], ["@", /* @__PURE__ */ new Map([["!", "!"], ["?", "?"], ["@", "@"], ["*", "*"], ["+", "+"]])], ["+", /* @__PURE__ */ new Map([["?", "*"], ["*", "*"]])]]);
  var gt = "(?!\\.)";
  var mt = /* @__PURE__ */ new Set(["[", "."]);
  var yt = /* @__PURE__ */ new Set(["..", "."]);
  var bt = new Set("().*{}+?[]^$\\!");
  var vt = "[^/]";
  var wt = vt + "*?";
  var xt = vt + "+?";
  var _t, _e, _n, _r, _i, _s, _o, _a, _h, _l, _u, _Nt_instances, c_fn, _Nt_static, p_fn, d_fn, g_fn, f_fn, m_fn, y_fn, b_fn, v_fn, w_fn, x_fn, E_fn, N_fn;
  var Nt = class {
    constructor(t2, e3) {
      __privateAdd(this, _Nt_instances);
      __publicField(this, "type");
      __privateAdd(this, _t);
      __privateAdd(this, _e);
      __privateAdd(this, _n, false);
      __privateAdd(this, _r, []);
      __privateAdd(this, _i);
      __privateAdd(this, _s);
      __privateAdd(this, _o);
      __privateAdd(this, _a, false);
      __privateAdd(this, _h);
      __privateAdd(this, _l);
      __privateAdd(this, _u, false);
      let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
      this.type = t2, t2 && __privateSet(this, _e, true), __privateSet(this, _i, e3), __privateSet(this, _t, __privateGet(this, _i) ? __privateGet(__privateGet(this, _i), _t) : this), __privateSet(this, _h, __privateGet(this, _t) === this ? n2 : __privateGet(__privateGet(this, _t), _h)), __privateSet(this, _o, __privateGet(this, _t) === this ? [] : __privateGet(__privateGet(this, _t), _o)), "!" !== t2 || __privateGet(__privateGet(this, _t), _a) || __privateGet(this, _o).push(this), __privateSet(this, _s, __privateGet(this, _i) ? __privateGet(__privateGet(this, _i), _r).length : 0);
    }
    get hasMagic() {
      if (void 0 !== __privateGet(this, _e)) return __privateGet(this, _e);
      for (const t2 of __privateGet(this, _r)) if ("string" != typeof t2 && (t2.type || t2.hasMagic)) return __privateSet(this, _e, true);
      return __privateGet(this, _e);
    }
    toString() {
      return void 0 !== __privateGet(this, _l) ? __privateGet(this, _l) : this.type ? __privateSet(this, _l, this.type + "(" + __privateGet(this, _r).map(((t2) => String(t2))).join("|") + ")") : __privateSet(this, _l, __privateGet(this, _r).map(((t2) => String(t2))).join(""));
    }
    push() {
      for (var t2 = arguments.length, e3 = new Array(t2), n2 = 0; n2 < t2; n2++) e3[n2] = arguments[n2];
      for (const t3 of e3) if ("" !== t3) {
        if ("string" != typeof t3 && !(t3 instanceof at && __privateGet(t3, _i) === this)) throw new Error("invalid part: " + t3);
        __privateGet(this, _r).push(t3);
      }
    }
    toJSON() {
      const t2 = null === this.type ? __privateGet(this, _r).slice().map(((t3) => "string" == typeof t3 ? t3 : t3.toJSON())) : [this.type, ...__privateGet(this, _r).map(((t3) => t3.toJSON()))];
      return this.isStart() && !this.type && t2.unshift([]), this.isEnd() && (this === __privateGet(this, _t) || __privateGet(__privateGet(this, _t), _a) && "!" === __privateGet(this, _i)?.type) && t2.push({}), t2;
    }
    isStart() {
      if (__privateGet(this, _t) === this) return true;
      if (!__privateGet(this, _i)?.isStart()) return false;
      if (0 === __privateGet(this, _s)) return true;
      const t2 = __privateGet(this, _i);
      for (let e3 = 0; e3 < __privateGet(this, _s); e3++) {
        const n2 = __privateGet(t2, _r)[e3];
        if (!(n2 instanceof at && "!" === n2.type)) return false;
      }
      return true;
    }
    isEnd() {
      if (__privateGet(this, _t) === this) return true;
      if ("!" === __privateGet(this, _i)?.type) return true;
      if (!__privateGet(this, _i)?.isEnd()) return false;
      if (!this.type) return __privateGet(this, _i)?.isEnd();
      const t2 = __privateGet(this, _i) ? __privateGet(__privateGet(this, _i), _r).length : 0;
      return __privateGet(this, _s) === t2 - 1;
    }
    copyIn(t2) {
      "string" == typeof t2 ? this.push(t2) : this.push(t2.clone(this));
    }
    clone(t2) {
      const e3 = new at(this.type, t2);
      for (const t3 of __privateGet(this, _r)) e3.copyIn(t3);
      return e3;
    }
    static fromGlob(t2) {
      var _a2;
      let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      const n2 = new at(null, void 0, e3);
      return __privateMethod(_a2 = at, _Nt_static, p_fn).call(_a2, t2, n2, 0, e3, 0), n2;
    }
    toMMPattern() {
      if (this !== __privateGet(this, _t)) return __privateGet(this, _t).toMMPattern();
      const t2 = this.toString(), [e3, n2, r2, i2] = this.toRegExpSource();
      if (!(r2 || __privateGet(this, _e) || __privateGet(this, _h).nocase && !__privateGet(this, _h).nocaseMagicOnly && t2.toUpperCase() !== t2.toLowerCase())) return n2;
      const s2 = (__privateGet(this, _h).nocase ? "i" : "") + (i2 ? "u" : "");
      return Object.assign(new RegExp(`^${e3}$`, s2), { _src: e3, _glob: t2 });
    }
    get options() {
      return __privateGet(this, _h);
    }
    toRegExpSource(t2) {
      const e3 = t2 ?? !!__privateGet(this, _h).dot;
      if (__privateGet(this, _t) === this && (__privateMethod(this, _Nt_instances, x_fn).call(this), __privateMethod(this, _Nt_instances, c_fn).call(this)), !ut(this)) {
        const n3 = this.isStart() && this.isEnd(), r3 = __privateGet(this, _r).map(((e4) => {
          var _a2;
          const [r4, i4, s4, o3] = "string" == typeof e4 ? __privateMethod(_a2 = at, _Nt_static, N_fn).call(_a2, e4, __privateGet(this, _e), n3) : e4.toRegExpSource(t2);
          return __privateSet(this, _e, __privateGet(this, _e) || s4), __privateSet(this, _n, __privateGet(this, _n) || o3), r4;
        })).join("");
        let i3 = "";
        if (this.isStart() && "string" == typeof __privateGet(this, _r)[0] && (1 !== __privateGet(this, _r).length || !yt.has(__privateGet(this, _r)[0]))) {
          const n4 = mt, s4 = e3 && n4.has(r3.charAt(0)) || r3.startsWith("\\.") && n4.has(r3.charAt(2)) || r3.startsWith("\\.\\.") && n4.has(r3.charAt(4)), o3 = !e3 && !t2 && n4.has(r3.charAt(0));
          i3 = s4 ? "(?!(?:^|/)\\.\\.?(?:$|/))" : o3 ? gt : "";
        }
        let s3 = "";
        return this.isEnd() && __privateGet(__privateGet(this, _t), _a) && "!" === __privateGet(this, _i)?.type && (s3 = "(?:$|\\/)"), [i3 + r3 + s3, ot(r3), __privateSet(this, _e, !!__privateGet(this, _e)), __privateGet(this, _n)];
      }
      const n2 = "*" === this.type || "+" === this.type, r2 = "!" === this.type ? "(?:(?!(?:" : "(?:";
      let i2 = __privateMethod(this, _Nt_instances, E_fn).call(this, e3);
      if (this.isStart() && this.isEnd() && !i2 && "!" !== this.type) {
        const t3 = this.toString(), e4 = this;
        return __privateSet(e4, _r, [t3]), e4.type = null, __privateSet(e4, _e, void 0), [t3, ot(this.toString()), false, false];
      }
      let s2 = !n2 || t2 || e3 ? "" : __privateMethod(this, _Nt_instances, E_fn).call(this, true);
      s2 === i2 && (s2 = ""), s2 && (i2 = `(?:${i2})(?:${s2})*?`);
      let o2 = "";
      return o2 = "!" === this.type && __privateGet(this, _u) ? (this.isStart() && !e3 ? gt : "") + xt : r2 + i2 + ("!" === this.type ? "))" + (!this.isStart() || e3 || t2 ? "" : gt) + wt + ")" : "@" === this.type ? ")" : "?" === this.type ? ")?" : "+" === this.type && s2 ? ")" : "*" === this.type && s2 ? ")?" : `)${this.type}`), [o2, ot(i2), __privateSet(this, _e, !!__privateGet(this, _e)), __privateGet(this, _n)];
    }
  };
  _t = new WeakMap();
  _e = new WeakMap();
  _n = new WeakMap();
  _r = new WeakMap();
  _i = new WeakMap();
  _s = new WeakMap();
  _o = new WeakMap();
  _a = new WeakMap();
  _h = new WeakMap();
  _l = new WeakMap();
  _u = new WeakMap();
  _Nt_instances = new WeakSet();
  c_fn = function() {
    if (this !== __privateGet(this, _t)) throw new Error("should only call on root");
    if (__privateGet(this, _a)) return this;
    let t2;
    for (this.toString(), __privateSet(this, _a, true); t2 = __privateGet(this, _o).pop(); ) {
      if ("!" !== t2.type) continue;
      let e3 = t2, n2 = __privateGet(e3, _i);
      for (; n2; ) {
        for (let r2 = __privateGet(e3, _s) + 1; !n2.type && r2 < __privateGet(n2, _r).length; r2++) for (const e4 of __privateGet(t2, _r)) {
          if ("string" == typeof e4) throw new Error("string part in extglob AST??");
          e4.copyIn(__privateGet(n2, _r)[r2]);
        }
        e3 = n2, n2 = __privateGet(e3, _i);
      }
    }
    return this;
  };
  _Nt_static = new WeakSet();
  p_fn = function(t2, e3, n2, r2, i2) {
    var _a2, _b, _c, _d;
    const s2 = r2.maxExtglobRecursion ?? 2;
    let o2 = false, a2 = false, h2 = -1, l2 = false;
    if (null === e3.type) {
      let u3 = n2, c3 = "";
      for (; u3 < t2.length; ) {
        const n3 = t2.charAt(u3++);
        if (o2 || "\\" === n3) o2 = !o2, c3 += n3;
        else if (a2) u3 === h2 + 1 ? "^" !== n3 && "!" !== n3 || (l2 = true) : "]" !== n3 || u3 === h2 + 2 && l2 || (a2 = false), c3 += n3;
        else if ("[" !== n3) if (!r2.noext && lt(n3) && "(" === t2.charAt(u3) && i2 <= s2) {
          e3.push(c3), c3 = "";
          const s3 = new at(n3, e3);
          u3 = __privateMethod(_a2 = at, _Nt_static, p_fn).call(_a2, t2, s3, u3, r2, i2 + 1), e3.push(s3);
        } else c3 += n3;
        else a2 = true, h2 = u3, l2 = false, c3 += n3;
      }
      return e3.push(c3), u3;
    }
    let u2 = n2 + 1, c2 = new at(null, e3);
    const p2 = [];
    let f = "";
    for (; u2 < t2.length; ) {
      const n3 = t2.charAt(u2++);
      if (o2 || "\\" === n3) o2 = !o2, f += n3;
      else if (a2) u2 === h2 + 1 ? "^" !== n3 && "!" !== n3 || (l2 = true) : "]" !== n3 || u2 === h2 + 2 && l2 || (a2 = false), f += n3;
      else if ("[" !== n3) if (lt(n3) && "(" === t2.charAt(u2) && (i2 <= s2 || e3 && __privateMethod(_b = e3, _Nt_instances, f_fn).call(_b, n3))) {
        const s3 = e3 && __privateMethod(_c = e3, _Nt_instances, f_fn).call(_c, n3) ? 0 : 1;
        c2.push(f), f = "";
        const o3 = new at(n3, c2);
        c2.push(o3), u2 = __privateMethod(_d = at, _Nt_static, p_fn).call(_d, t2, o3, u2, r2, i2 + s3);
      } else if ("|" !== n3) {
        if (")" === n3) return "" === f && 0 === __privateGet(e3, _r).length && __privateSet(e3, _u, true), c2.push(f), f = "", e3.push(...p2, c2), u2;
        f += n3;
      } else c2.push(f), f = "", p2.push(c2), c2 = new at(null, e3);
      else a2 = true, h2 = u2, l2 = false, f += n3;
    }
    return e3.type = null, __privateSet(e3, _e, void 0), __privateSet(e3, _r, [t2.substring(n2 - 1)]), u2;
  };
  d_fn = function(t2) {
    return __privateMethod(this, _Nt_instances, g_fn).call(this, t2, pt);
  };
  g_fn = function(t2) {
    let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : ct;
    if (!t2 || "object" != typeof t2 || null !== t2.type || 1 !== __privateGet(t2, _r).length || null === this.type) return false;
    const n2 = __privateGet(t2, _r)[0];
    return !(!n2 || "object" != typeof n2 || null === n2.type) && __privateMethod(this, _Nt_instances, f_fn).call(this, n2.type, e3);
  };
  f_fn = function(t2) {
    let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : ft;
    return !!e3.get(this.type)?.includes(t2);
  };
  m_fn = function(t2, e3) {
    const n2 = __privateGet(t2, _r)[0], r2 = new at(null, n2, this.options);
    __privateGet(r2, _r).push(""), n2.push(r2), __privateMethod(this, _Nt_instances, y_fn).call(this, t2, e3);
  };
  y_fn = function(t2, e3) {
    const n2 = __privateGet(t2, _r)[0];
    __privateGet(this, _r).splice(e3, 1, ...__privateGet(n2, _r));
    for (const t3 of __privateGet(n2, _r)) "object" == typeof t3 && __privateSet(t3, _i, this);
    __privateSet(this, _l, void 0);
  };
  b_fn = function(t2) {
    const e3 = dt.get(this.type);
    return !!e3?.has(t2);
  };
  v_fn = function(t2) {
    if (!t2 || "object" != typeof t2 || null !== t2.type || 1 !== __privateGet(t2, _r).length || null === this.type || 1 !== __privateGet(this, _r).length) return false;
    const e3 = __privateGet(t2, _r)[0];
    return !(!e3 || "object" != typeof e3 || null === e3.type) && __privateMethod(this, _Nt_instances, b_fn).call(this, e3.type);
  };
  w_fn = function(t2) {
    const e3 = dt.get(this.type), n2 = __privateGet(t2, _r)[0], r2 = e3?.get(n2.type);
    if (!r2) return false;
    __privateSet(this, _r, __privateGet(n2, _r));
    for (const t3 of __privateGet(this, _r)) "object" == typeof t3 && __privateSet(t3, _i, this);
    this.type = r2, __privateSet(this, _l, void 0), __privateSet(this, _u, false);
  };
  x_fn = function() {
    var _a2, _b;
    if (ut(this)) {
      let t2 = 0, e3 = false;
      do {
        e3 = true;
        for (let t3 = 0; t3 < __privateGet(this, _r).length; t3++) {
          const n2 = __privateGet(this, _r)[t3];
          "object" == typeof n2 && (__privateMethod(_a2 = n2, _Nt_instances, x_fn).call(_a2), __privateMethod(this, _Nt_instances, g_fn).call(this, n2) ? (e3 = false, __privateMethod(this, _Nt_instances, y_fn).call(this, n2, t3)) : __privateMethod(this, _Nt_instances, d_fn).call(this, n2) ? (e3 = false, __privateMethod(this, _Nt_instances, m_fn).call(this, n2, t3)) : __privateMethod(this, _Nt_instances, v_fn).call(this, n2) && (e3 = false, __privateMethod(this, _Nt_instances, w_fn).call(this, n2)));
        }
      } while (!e3 && ++t2 < 10);
    } else for (const t2 of __privateGet(this, _r)) "object" == typeof t2 && __privateMethod(_b = t2, _Nt_instances, x_fn).call(_b);
    __privateSet(this, _l, void 0);
  };
  E_fn = function(t2) {
    return __privateGet(this, _r).map(((e3) => {
      if ("string" == typeof e3) throw new Error("string type in extglob ast??");
      const [n2, r2, i2, s2] = e3.toRegExpSource(t2);
      return __privateSet(this, _n, __privateGet(this, _n) || s2), n2;
    })).filter(((t3) => !(this.isStart() && this.isEnd() && !t3))).join("|");
  };
  N_fn = function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] && arguments[2], r2 = false, i2 = "", s2 = false, o2 = false;
    for (let a2 = 0; a2 < t2.length; a2++) {
      const h2 = t2.charAt(a2);
      if (r2) r2 = false, i2 += (bt.has(h2) ? "\\" : "") + h2, o2 = false;
      else if ("\\" !== h2) {
        if ("[" === h2) {
          const [n3, r3, h3, l2] = st(t2, a2);
          if (h3) {
            i2 += n3, s2 = s2 || r3, a2 += h3 - 1, e3 = e3 || l2, o2 = false;
            continue;
          }
        }
        if ("*" !== h2) o2 = false, "?" !== h2 ? i2 += h2.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&") : (i2 += vt, e3 = true);
        else {
          if (o2) continue;
          o2 = true, i2 += n2 && /^[*]+$/.test(t2) ? xt : wt, e3 = true;
        }
      } else a2 === t2.length - 1 ? i2 += "\\\\" : r2 = true;
    }
    return [i2, ot(t2), !!e3, s2];
  };
  __privateAdd(Nt, _Nt_static);
  at = Nt;
  var Et = function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    return et(e3), !(!n2.nocomment && "#" === e3.charAt(0)) && new Xt(e3, n2).match(t2);
  };
  var At = /^\*+([^+@!?\*\[\(]*)$/;
  var St = (t2) => (e3) => !e3.startsWith(".") && e3.endsWith(t2);
  var Pt = (t2) => (e3) => e3.endsWith(t2);
  var Tt = (t2) => (t2 = t2.toLowerCase(), (e3) => !e3.startsWith(".") && e3.toLowerCase().endsWith(t2));
  var Ot = (t2) => (t2 = t2.toLowerCase(), (e3) => e3.toLowerCase().endsWith(t2));
  var Ct = /^\*+\.\*+$/;
  var _t2 = (t2) => !t2.startsWith(".") && t2.includes(".");
  var $t = (t2) => "." !== t2 && ".." !== t2 && t2.includes(".");
  var jt = /^\.\*+$/;
  var It = (t2) => "." !== t2 && ".." !== t2 && t2.startsWith(".");
  var Mt = /^\*+$/;
  var Rt = (t2) => 0 !== t2.length && !t2.startsWith(".");
  var kt = (t2) => 0 !== t2.length && "." !== t2 && ".." !== t2;
  var Lt = /^\?+([^+@!?\*\[\(]*)?$/;
  var Dt = (t2) => {
    let [e3, n2 = ""] = t2;
    const r2 = Wt([e3]);
    return n2 ? (n2 = n2.toLowerCase(), (t3) => r2(t3) && t3.toLowerCase().endsWith(n2)) : r2;
  };
  var Ut = (t2) => {
    let [e3, n2 = ""] = t2;
    const r2 = Bt([e3]);
    return n2 ? (n2 = n2.toLowerCase(), (t3) => r2(t3) && t3.toLowerCase().endsWith(n2)) : r2;
  };
  var Ft = (t2) => {
    let [e3, n2 = ""] = t2;
    const r2 = Bt([e3]);
    return n2 ? (t3) => r2(t3) && t3.endsWith(n2) : r2;
  };
  var Vt = (t2) => {
    let [e3, n2 = ""] = t2;
    const r2 = Wt([e3]);
    return n2 ? (t3) => r2(t3) && t3.endsWith(n2) : r2;
  };
  var Wt = (t2) => {
    let [e3] = t2;
    const n2 = e3.length;
    return (t3) => t3.length === n2 && !t3.startsWith(".");
  };
  var Bt = (t2) => {
    let [e3] = t2;
    const n2 = e3.length;
    return (t3) => t3.length === n2 && "." !== t3 && ".." !== t3;
  };
  var Gt = "object" == typeof process && process ? "object" == typeof process.env && process.env && process.env.__MINIMATCH_TESTING_PLATFORM__ || process.platform : "posix";
  Et.sep = "win32" === Gt ? "\\" : "/";
  var zt = Symbol("globstar **");
  Et.GLOBSTAR = zt, Et.filter = function(t2) {
    let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
    return (n2) => Et(n2, t2, e3);
  };
  var qt = function(t2) {
    let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
    return Object.assign({}, t2, e3);
  };
  Et.defaults = (t2) => {
    if (!t2 || "object" != typeof t2 || !Object.keys(t2).length) return Et;
    const e3 = Et;
    return Object.assign((function(n2, r2) {
      return e3(n2, r2, qt(t2, arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {}));
    }), { Minimatch: class extends e3.Minimatch {
      constructor(e4) {
        super(e4, qt(t2, arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {}));
      }
      static defaults(n2) {
        return e3.defaults(qt(t2, n2)).Minimatch;
      }
    }, AST: class extends e3.AST {
      constructor(e4, n2) {
        super(e4, n2, qt(t2, arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {}));
      }
      static fromGlob(n2) {
        let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
        return e3.AST.fromGlob(n2, qt(t2, r2));
      }
    }, unescape: function(n2) {
      let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      return e3.unescape(n2, qt(t2, r2));
    }, escape: function(n2) {
      let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      return e3.escape(n2, qt(t2, r2));
    }, filter: function(n2) {
      let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      return e3.filter(n2, qt(t2, r2));
    }, defaults: (n2) => e3.defaults(qt(t2, n2)), makeRe: function(n2) {
      let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      return e3.makeRe(n2, qt(t2, r2));
    }, braceExpand: function(n2) {
      let r2 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      return e3.braceExpand(n2, qt(t2, r2));
    }, match: function(n2, r2) {
      let i2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
      return e3.match(n2, r2, qt(t2, i2));
    }, sep: e3.sep, GLOBSTAR: zt });
  };
  var Ht = function(t2) {
    let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
    return et(t2), e3.nobrace || !/\{(?:(?!\{).)*\}/.test(t2) ? [t2] : tt(t2);
  };
  Et.braceExpand = Ht, Et.makeRe = function(t2) {
    return new Xt(t2, arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {}).makeRe();
  }, Et.match = function(t2, e3) {
    const n2 = new Xt(e3, arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {});
    return t2 = t2.filter(((t3) => n2.match(t3))), n2.options.nonull && !t2.length && t2.push(e3), t2;
  };
  var Yt = /[?*]|[+@!]\(.*?\)|\[|\]/;
  var _Xt_instances, A_fn, P_fn, S_fn;
  var Xt = class {
    constructor(t2) {
      __privateAdd(this, _Xt_instances);
      __publicField(this, "options");
      __publicField(this, "set");
      __publicField(this, "pattern");
      __publicField(this, "windowsPathsNoEscape");
      __publicField(this, "nonegate");
      __publicField(this, "negate");
      __publicField(this, "comment");
      __publicField(this, "empty");
      __publicField(this, "preserveMultipleSlashes");
      __publicField(this, "partial");
      __publicField(this, "globSet");
      __publicField(this, "globParts");
      __publicField(this, "nocase");
      __publicField(this, "isWindows");
      __publicField(this, "platform");
      __publicField(this, "windowsNoMagicRoot");
      __publicField(this, "maxGlobstarRecursion");
      __publicField(this, "regexp");
      let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
      et(t2), e3 = e3 || {}, this.options = e3, this.maxGlobstarRecursion = e3.maxGlobstarRecursion ?? 200, this.pattern = t2, this.platform = e3.platform || Gt, this.isWindows = "win32" === this.platform, this.windowsPathsNoEscape = !!e3.windowsPathsNoEscape || false === e3.allowWindowsEscape, this.windowsPathsNoEscape && (this.pattern = this.pattern.replace(/\\/g, "/")), this.preserveMultipleSlashes = !!e3.preserveMultipleSlashes, this.regexp = null, this.negate = false, this.nonegate = !!e3.nonegate, this.comment = false, this.empty = false, this.partial = !!e3.partial, this.nocase = !!this.options.nocase, this.windowsNoMagicRoot = void 0 !== e3.windowsNoMagicRoot ? e3.windowsNoMagicRoot : !(!this.isWindows || !this.nocase), this.globSet = [], this.globParts = [], this.set = [], this.make();
    }
    hasMagic() {
      if (this.options.magicalBraces && this.set.length > 1) return true;
      for (const t2 of this.set) for (const e3 of t2) if ("string" != typeof e3) return true;
      return false;
    }
    debug() {
    }
    make() {
      const t2 = this.pattern, e3 = this.options;
      if (!e3.nocomment && "#" === t2.charAt(0)) return void (this.comment = true);
      if (!t2) return void (this.empty = true);
      this.parseNegate(), this.globSet = [...new Set(this.braceExpand())], e3.debug && (this.debug = function() {
        return console.error(...arguments);
      }), this.debug(this.pattern, this.globSet);
      const n2 = this.globSet.map(((t3) => this.slashSplit(t3)));
      this.globParts = this.preprocess(n2), this.debug(this.pattern, this.globParts);
      let r2 = this.globParts.map(((t3, e4, n3) => {
        if (this.isWindows && this.windowsNoMagicRoot) {
          const e5 = !("" !== t3[0] || "" !== t3[1] || "?" !== t3[2] && Yt.test(t3[2]) || Yt.test(t3[3])), n4 = /^[a-z]:/i.test(t3[0]);
          if (e5) return [...t3.slice(0, 4), ...t3.slice(4).map(((t4) => this.parse(t4)))];
          if (n4) return [t3[0], ...t3.slice(1).map(((t4) => this.parse(t4)))];
        }
        return t3.map(((t4) => this.parse(t4)));
      }));
      if (this.debug(this.pattern, r2), this.set = r2.filter(((t3) => -1 === t3.indexOf(false))), this.isWindows) for (let t3 = 0; t3 < this.set.length; t3++) {
        const e4 = this.set[t3];
        "" === e4[0] && "" === e4[1] && "?" === this.globParts[t3][2] && "string" == typeof e4[3] && /^[a-z]:$/i.test(e4[3]) && (e4[2] = "?");
      }
      this.debug(this.pattern, this.set);
    }
    preprocess(t2) {
      if (this.options.noglobstar) for (let e4 = 0; e4 < t2.length; e4++) for (let n2 = 0; n2 < t2[e4].length; n2++) "**" === t2[e4][n2] && (t2[e4][n2] = "*");
      const { optimizationLevel: e3 = 1 } = this.options;
      return e3 >= 2 ? (t2 = this.firstPhasePreProcess(t2), t2 = this.secondPhasePreProcess(t2)) : t2 = e3 >= 1 ? this.levelOneOptimize(t2) : this.adjascentGlobstarOptimize(t2), t2;
    }
    adjascentGlobstarOptimize(t2) {
      return t2.map(((t3) => {
        let e3 = -1;
        for (; -1 !== (e3 = t3.indexOf("**", e3 + 1)); ) {
          let n2 = e3;
          for (; "**" === t3[n2 + 1]; ) n2++;
          n2 !== e3 && t3.splice(e3, n2 - e3);
        }
        return t3;
      }));
    }
    levelOneOptimize(t2) {
      return t2.map(((t3) => 0 === (t3 = t3.reduce(((t4, e3) => {
        const n2 = t4[t4.length - 1];
        return "**" === e3 && "**" === n2 ? t4 : ".." === e3 && n2 && ".." !== n2 && "." !== n2 && "**" !== n2 ? (t4.pop(), t4) : (t4.push(e3), t4);
      }), [])).length ? [""] : t3));
    }
    levelTwoFileOptimize(t2) {
      Array.isArray(t2) || (t2 = this.slashSplit(t2));
      let e3 = false;
      do {
        if (e3 = false, !this.preserveMultipleSlashes) {
          for (let n3 = 1; n3 < t2.length - 1; n3++) {
            const r2 = t2[n3];
            1 === n3 && "" === r2 && "" === t2[0] || "." !== r2 && "" !== r2 || (e3 = true, t2.splice(n3, 1), n3--);
          }
          "." !== t2[0] || 2 !== t2.length || "." !== t2[1] && "" !== t2[1] || (e3 = true, t2.pop());
        }
        let n2 = 0;
        for (; -1 !== (n2 = t2.indexOf("..", n2 + 1)); ) {
          const r2 = t2[n2 - 1];
          r2 && "." !== r2 && ".." !== r2 && "**" !== r2 && (e3 = true, t2.splice(n2 - 1, 2), n2 -= 2);
        }
      } while (e3);
      return 0 === t2.length ? [""] : t2;
    }
    firstPhasePreProcess(t2) {
      let e3 = false;
      do {
        e3 = false;
        for (let n2 of t2) {
          let r2 = -1;
          for (; -1 !== (r2 = n2.indexOf("**", r2 + 1)); ) {
            let i3 = r2;
            for (; "**" === n2[i3 + 1]; ) i3++;
            i3 > r2 && n2.splice(r2 + 1, i3 - r2);
            let s2 = n2[r2 + 1];
            const o2 = n2[r2 + 2], a2 = n2[r2 + 3];
            if (".." !== s2) continue;
            if (!o2 || "." === o2 || ".." === o2 || !a2 || "." === a2 || ".." === a2) continue;
            e3 = true, n2.splice(r2, 1);
            const h2 = n2.slice(0);
            h2[r2] = "**", t2.push(h2), r2--;
          }
          if (!this.preserveMultipleSlashes) {
            for (let t3 = 1; t3 < n2.length - 1; t3++) {
              const r3 = n2[t3];
              1 === t3 && "" === r3 && "" === n2[0] || "." !== r3 && "" !== r3 || (e3 = true, n2.splice(t3, 1), t3--);
            }
            "." !== n2[0] || 2 !== n2.length || "." !== n2[1] && "" !== n2[1] || (e3 = true, n2.pop());
          }
          let i2 = 0;
          for (; -1 !== (i2 = n2.indexOf("..", i2 + 1)); ) {
            const t3 = n2[i2 - 1];
            if (t3 && "." !== t3 && ".." !== t3 && "**" !== t3) {
              e3 = true;
              const t4 = 1 === i2 && "**" === n2[i2 + 1] ? ["."] : [];
              n2.splice(i2 - 1, 2, ...t4), 0 === n2.length && n2.push(""), i2 -= 2;
            }
          }
        }
      } while (e3);
      return t2;
    }
    secondPhasePreProcess(t2) {
      for (let e3 = 0; e3 < t2.length - 1; e3++) for (let n2 = e3 + 1; n2 < t2.length; n2++) {
        const r2 = this.partsMatch(t2[e3], t2[n2], !this.preserveMultipleSlashes);
        if (r2) {
          t2[e3] = [], t2[n2] = r2;
          break;
        }
      }
      return t2.filter(((t3) => t3.length));
    }
    partsMatch(t2, e3) {
      let n2 = arguments.length > 2 && void 0 !== arguments[2] && arguments[2], r2 = 0, i2 = 0, s2 = [], o2 = "";
      for (; r2 < t2.length && i2 < e3.length; ) if (t2[r2] === e3[i2]) s2.push("b" === o2 ? e3[i2] : t2[r2]), r2++, i2++;
      else if (n2 && "**" === t2[r2] && e3[i2] === t2[r2 + 1]) s2.push(t2[r2]), r2++;
      else if (n2 && "**" === e3[i2] && t2[r2] === e3[i2 + 1]) s2.push(e3[i2]), i2++;
      else if ("*" !== t2[r2] || !e3[i2] || !this.options.dot && e3[i2].startsWith(".") || "**" === e3[i2]) {
        if ("*" !== e3[i2] || !t2[r2] || !this.options.dot && t2[r2].startsWith(".") || "**" === t2[r2]) return false;
        if ("a" === o2) return false;
        o2 = "b", s2.push(e3[i2]), r2++, i2++;
      } else {
        if ("b" === o2) return false;
        o2 = "a", s2.push(t2[r2]), r2++, i2++;
      }
      return t2.length === e3.length && s2;
    }
    parseNegate() {
      if (this.nonegate) return;
      const t2 = this.pattern;
      let e3 = false, n2 = 0;
      for (let r2 = 0; r2 < t2.length && "!" === t2.charAt(r2); r2++) e3 = !e3, n2++;
      n2 && (this.pattern = t2.slice(n2)), this.negate = e3;
    }
    matchOne(t2, e3) {
      let n2 = arguments.length > 2 && void 0 !== arguments[2] && arguments[2], r2 = 0, i2 = 0;
      if (this.isWindows) {
        const n3 = "string" == typeof t2[0] && /^[a-z]:$/i.test(t2[0]), s3 = !n3 && "" === t2[0] && "" === t2[1] && "?" === t2[2] && /^[a-z]:$/i.test(t2[3]), o2 = "string" == typeof e3[0] && /^[a-z]:$/i.test(e3[0]), a2 = s3 ? 3 : n3 ? 0 : void 0, h2 = !o2 && "" === e3[0] && "" === e3[1] && "?" === e3[2] && "string" == typeof e3[3] && /^[a-z]:$/i.test(e3[3]) ? 3 : o2 ? 0 : void 0;
        if ("number" == typeof a2 && "number" == typeof h2) {
          const [n4, s4] = [t2[a2], e3[h2]];
          n4.toLowerCase() === s4.toLowerCase() && (e3[h2] = n4, i2 = h2, r2 = a2);
        }
      }
      const { optimizationLevel: s2 = 1 } = this.options;
      return s2 >= 2 && (t2 = this.levelTwoFileOptimize(t2)), e3.includes(zt) ? __privateMethod(this, _Xt_instances, A_fn).call(this, t2, e3, n2, r2, i2) : __privateMethod(this, _Xt_instances, S_fn).call(this, t2, e3, n2, r2, i2);
    }
    braceExpand() {
      return Ht(this.pattern, this.options);
    }
    parse(t2) {
      et(t2);
      const e3 = this.options;
      if ("**" === t2) return zt;
      if ("" === t2) return "";
      let n2, r2 = null;
      (n2 = t2.match(Mt)) ? r2 = e3.dot ? kt : Rt : (n2 = t2.match(At)) ? r2 = (e3.nocase ? e3.dot ? Ot : Tt : e3.dot ? Pt : St)(n2[1]) : (n2 = t2.match(Lt)) ? r2 = (e3.nocase ? e3.dot ? Ut : Dt : e3.dot ? Ft : Vt)(n2) : (n2 = t2.match(Ct)) ? r2 = e3.dot ? $t : _t2 : (n2 = t2.match(jt)) && (r2 = It);
      const i2 = Nt.fromGlob(t2, this.options).toMMPattern();
      return r2 && "object" == typeof i2 && Reflect.defineProperty(i2, "test", { value: r2 }), i2;
    }
    makeRe() {
      if (this.regexp || false === this.regexp) return this.regexp;
      const t2 = this.set;
      if (!t2.length) return this.regexp = false, this.regexp;
      const e3 = this.options, n2 = e3.noglobstar ? "[^/]*?" : e3.dot ? "(?:(?!(?:\\/|^)(?:\\.{1,2})($|\\/)).)*?" : "(?:(?!(?:\\/|^)\\.).)*?", r2 = new Set(e3.nocase ? ["i"] : []);
      let i2 = t2.map(((t3) => {
        const e4 = t3.map(((t4) => {
          if (t4 instanceof RegExp) for (const e5 of t4.flags.split("")) r2.add(e5);
          return "string" == typeof t4 ? t4.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&") : t4 === zt ? zt : t4._src;
        }));
        return e4.forEach(((t4, r3) => {
          const i3 = e4[r3 + 1], s3 = e4[r3 - 1];
          t4 === zt && s3 !== zt && (void 0 === s3 ? void 0 !== i3 && i3 !== zt ? e4[r3 + 1] = "(?:\\/|" + n2 + "\\/)?" + i3 : e4[r3] = n2 : void 0 === i3 ? e4[r3 - 1] = s3 + "(?:\\/|" + n2 + ")?" : i3 !== zt && (e4[r3 - 1] = s3 + "(?:\\/|\\/" + n2 + "\\/)" + i3, e4[r3 + 1] = zt));
        })), e4.filter(((t4) => t4 !== zt)).join("/");
      })).join("|");
      const [s2, o2] = t2.length > 1 ? ["(?:", ")"] : ["", ""];
      i2 = "^" + s2 + i2 + o2 + "$", this.negate && (i2 = "^(?!" + i2 + ").+$");
      try {
        this.regexp = new RegExp(i2, [...r2].join(""));
      } catch (t3) {
        this.regexp = false;
      }
      return this.regexp;
    }
    slashSplit(t2) {
      return this.preserveMultipleSlashes ? t2.split("/") : this.isWindows && /^\/\/[^\/]+/.test(t2) ? ["", ...t2.split(/\/+/)] : t2.split(/\/+/);
    }
    match(t2) {
      let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : this.partial;
      if (this.debug("match", t2, this.pattern), this.comment) return false;
      if (this.empty) return "" === t2;
      if ("/" === t2 && e3) return true;
      const n2 = this.options;
      this.isWindows && (t2 = t2.split("\\").join("/"));
      const r2 = this.slashSplit(t2);
      this.debug(this.pattern, "split", r2);
      const i2 = this.set;
      this.debug(this.pattern, "set", i2);
      let s2 = r2[r2.length - 1];
      if (!s2) for (let t3 = r2.length - 2; !s2 && t3 >= 0; t3--) s2 = r2[t3];
      for (let t3 = 0; t3 < i2.length; t3++) {
        const o2 = i2[t3];
        let a2 = r2;
        if (n2.matchBase && 1 === o2.length && (a2 = [s2]), this.matchOne(a2, o2, e3)) return !!n2.flipNegate || !this.negate;
      }
      return !n2.flipNegate && this.negate;
    }
    static defaults(t2) {
      return Et.defaults(t2).Minimatch;
    }
  };
  _Xt_instances = new WeakSet();
  A_fn = function(t2, e3, n2, r2, i2) {
    const s2 = e3.indexOf(zt, i2), o2 = e3.lastIndexOf(zt), [a2, h2, l2] = n2 ? [e3.slice(i2, s2), e3.slice(s2 + 1), []] : [e3.slice(i2, s2), e3.slice(s2 + 1, o2), e3.slice(o2 + 1)];
    if (a2.length) {
      const e4 = t2.slice(r2, r2 + a2.length);
      if (!__privateMethod(this, _Xt_instances, S_fn).call(this, e4, a2, n2, 0, 0)) return false;
      r2 += a2.length;
    }
    let u2 = 0;
    if (l2.length) {
      if (l2.length + r2 > t2.length) return false;
      let e4 = t2.length - l2.length;
      if (__privateMethod(this, _Xt_instances, S_fn).call(this, t2, l2, n2, e4, 0)) u2 = l2.length;
      else {
        if ("" !== t2[t2.length - 1] || r2 + l2.length === t2.length) return false;
        if (e4--, !__privateMethod(this, _Xt_instances, S_fn).call(this, t2, l2, n2, e4, 0)) return false;
        u2 = l2.length + 1;
      }
    }
    if (!h2.length) {
      let e4 = !!u2;
      for (let n3 = r2; n3 < t2.length - u2; n3++) {
        const r3 = String(t2[n3]);
        if (e4 = true, "." === r3 || ".." === r3 || !this.options.dot && r3.startsWith(".")) return false;
      }
      return n2 || e4;
    }
    const c2 = [[[], 0]];
    let p2 = c2[0], f = 0;
    const d2 = [0];
    for (const t3 of h2) t3 === zt ? (d2.push(f), p2 = [[], 0], c2.push(p2)) : (p2[0].push(t3), f++);
    let g = c2.length - 1;
    const m2 = t2.length - u2;
    for (const t3 of c2) t3[1] = m2 - (d2[g--] + t3[0].length);
    return !!__privateMethod(this, _Xt_instances, P_fn).call(this, t2, c2, r2, 0, n2, 0, !!u2);
  };
  P_fn = function(t2, e3, n2, r2, i2, s2, o2) {
    const a2 = e3[r2];
    if (!a2) {
      for (let e4 = n2; e4 < t2.length; e4++) {
        o2 = true;
        const n3 = t2[e4];
        if ("." === n3 || ".." === n3 || !this.options.dot && n3.startsWith(".")) return false;
      }
      return o2;
    }
    const [h2, l2] = a2;
    for (; n2 <= l2; ) {
      if (__privateMethod(this, _Xt_instances, S_fn).call(this, t2.slice(0, n2 + h2.length), h2, i2, n2, 0) && s2 < this.maxGlobstarRecursion) {
        const a4 = __privateMethod(this, _Xt_instances, P_fn).call(this, t2, e3, n2 + h2.length, r2 + 1, i2, s2 + 1, o2);
        if (false !== a4) return a4;
      }
      const a3 = t2[n2];
      if ("." === a3 || ".." === a3 || !this.options.dot && a3.startsWith(".")) return false;
      n2++;
    }
    return i2 || null;
  };
  S_fn = function(t2, e3, n2, r2, i2) {
    let s2, o2, a2, h2;
    for (s2 = r2, o2 = i2, h2 = t2.length, a2 = e3.length; s2 < h2 && o2 < a2; s2++, o2++) {
      this.debug("matchOne loop");
      let n3, r3 = e3[o2], i3 = t2[s2];
      if (this.debug(e3, r3, i3), false === r3 || r3 === zt) return false;
      if ("string" == typeof r3 ? (n3 = i3 === r3, this.debug("string match", r3, i3, n3)) : (n3 = r3.test(i3), this.debug("pattern match", r3, i3, n3)), !n3) return false;
    }
    if (s2 === h2 && o2 === a2) return true;
    if (s2 === h2) return n2;
    if (o2 === a2) return s2 === h2 - 1 && "" === t2[s2];
    throw new Error("wtf?");
  };
  function Zt(t2) {
    const e3 = new Error(`${arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : ""}Invalid response: ${t2.status} ${t2.statusText}`);
    return e3.status = t2.status, e3.response = t2, e3;
  }
  function Jt(t2, e3) {
    const { status: n2 } = e3;
    if (401 === n2 && t2.digest) return e3;
    if (n2 >= 400) throw Zt(e3);
    return e3;
  }
  function Kt(t2, e3) {
    return arguments.length > 2 && void 0 !== arguments[2] && arguments[2] ? { data: e3, headers: t2.headers ? V(t2.headers) : {}, status: t2.status, statusText: t2.statusText } : e3;
  }
  Et.AST = Nt, Et.Minimatch = Xt, Et.escape = function(t2) {
    let { windowsPathsNoEscape: e3 = false } = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
    return e3 ? t2.replace(/[?*()[\]]/g, "[$&]") : t2.replace(/[?*()[\]\\]/g, "\\$&");
  }, Et.unescape = ot;
  var Qt = (te = function(t2, e3, n2) {
    let r2 = arguments.length > 3 && void 0 !== arguments[3] ? arguments[3] : {};
    const i2 = K({ url: m(t2.remoteURL, p(e3)), method: "COPY", headers: { Destination: m(t2.remoteURL, p(n2)), Overwrite: false === r2.overwrite ? "F" : "T", Depth: r2.shallow ? "0" : "infinity" } }, t2, r2);
    return o2 = function(e4) {
      Jt(t2, e4);
    }, (s2 = J(i2, t2)) && s2.then || (s2 = Promise.resolve(s2)), o2 ? s2.then(o2) : s2;
    var s2, o2;
  }, function() {
    for (var t2 = [], e3 = 0; e3 < arguments.length; e3++) t2[e3] = arguments[e3];
    try {
      return Promise.resolve(te.apply(this, t2));
    } catch (t3) {
      return Promise.reject(t3);
    }
  });
  var te;
  var ee = ":A-Za-z_\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD";
  var ne = new RegExp("^[" + ee + "][" + ee + "\\-.\\d\\u00B7\\u0300-\\u036F\\u203F-\\u2040]*$");
  function re(t2, e3) {
    const n2 = [];
    let r2 = e3.exec(t2);
    for (; r2; ) {
      const i2 = [];
      i2.startIndex = e3.lastIndex - r2[0].length;
      const s2 = r2.length;
      for (let t3 = 0; t3 < s2; t3++) i2.push(r2[t3]);
      n2.push(i2), r2 = e3.exec(t2);
    }
    return n2;
  }
  var ie = function(t2) {
    return !(null == ne.exec(t2));
  };
  var se = ["hasOwnProperty", "toString", "valueOf", "__defineGetter__", "__defineSetter__", "__lookupGetter__", "__lookupSetter__"];
  var oe = ["__proto__", "constructor", "prototype"];
  var ae = (t2) => se.includes(t2) ? "__" + t2 : t2;
  var he = { preserveOrder: false, attributeNamePrefix: "@_", attributesGroupName: false, textNodeName: "#text", ignoreAttributes: true, removeNSPrefix: false, allowBooleanAttributes: false, parseTagValue: true, parseAttributeValue: false, trimValues: true, cdataPropName: false, numberParseOptions: { hex: true, leadingZeros: true, eNotation: true }, tagValueProcessor: function(t2, e3) {
    return e3;
  }, attributeValueProcessor: function(t2, e3) {
    return e3;
  }, stopNodes: [], alwaysCreateTextNode: false, isArray: () => false, commentPropName: false, unpairedTags: [], processEntities: true, htmlEntities: false, entityDecoder: null, ignoreDeclaration: false, ignorePiTags: false, transformTagName: false, transformAttributeName: false, updateTag: function(t2, e3, n2) {
    return t2;
  }, captureMetaData: false, maxNestedTags: 100, strictReservedNames: true, jPath: true, onDangerousProperty: ae };
  function le(t2, e3) {
    if ("string" != typeof t2) return;
    const n2 = t2.toLowerCase();
    if (se.some(((t3) => n2 === t3.toLowerCase()))) throw new Error(`[SECURITY] Invalid ${e3}: "${t2}" is a reserved JavaScript keyword that could cause prototype pollution`);
    if (oe.some(((t3) => n2 === t3.toLowerCase()))) throw new Error(`[SECURITY] Invalid ${e3}: "${t2}" is a reserved JavaScript keyword that could cause prototype pollution`);
  }
  function ue(t2, e3) {
    return "boolean" == typeof t2 ? { enabled: t2, maxEntitySize: 1e4, maxExpansionDepth: 1e4, maxTotalExpansions: 1 / 0, maxExpandedLength: 1e5, maxEntityCount: 1e3, allowedTags: null, tagFilter: null, appliesTo: "all" } : "object" == typeof t2 && null !== t2 ? { enabled: false !== t2.enabled, maxEntitySize: Math.max(1, t2.maxEntitySize ?? 1e4), maxExpansionDepth: Math.max(1, t2.maxExpansionDepth ?? 1e4), maxTotalExpansions: Math.max(1, t2.maxTotalExpansions ?? 1 / 0), maxExpandedLength: Math.max(1, t2.maxExpandedLength ?? 1e5), maxEntityCount: Math.max(1, t2.maxEntityCount ?? 1e3), allowedTags: t2.allowedTags ?? null, tagFilter: t2.tagFilter ?? null, appliesTo: t2.appliesTo ?? "all" } : ue(true);
  }
  var ce = function(t2) {
    const e3 = Object.assign({}, he, t2), n2 = [{ value: e3.attributeNamePrefix, name: "attributeNamePrefix" }, { value: e3.attributesGroupName, name: "attributesGroupName" }, { value: e3.textNodeName, name: "textNodeName" }, { value: e3.cdataPropName, name: "cdataPropName" }, { value: e3.commentPropName, name: "commentPropName" }];
    for (const { value: t3, name: e4 } of n2) t3 && le(t3, e4);
    return null === e3.onDangerousProperty && (e3.onDangerousProperty = ae), e3.processEntities = ue(e3.processEntities, e3.htmlEntities), e3.unpairedTagsSet = new Set(e3.unpairedTags), e3.stopNodes && Array.isArray(e3.stopNodes) && (e3.stopNodes = e3.stopNodes.map(((t3) => "string" == typeof t3 && t3.startsWith("*.") ? ".." + t3.substring(2) : t3))), e3;
  };
  var pe;
  pe = "function" != typeof Symbol ? "@@xmlMetadata" : Symbol("XML Node Metadata");
  var fe = class {
    constructor(t2) {
      this.tagname = t2, this.child = [], this[":@"] = /* @__PURE__ */ Object.create(null);
    }
    add(t2, e3) {
      "__proto__" === t2 && (t2 = "#__proto__"), this.child.push({ [t2]: e3 });
    }
    addChild(t2, e3) {
      "__proto__" === t2.tagname && (t2.tagname = "#__proto__"), t2[":@"] && Object.keys(t2[":@"]).length > 0 ? this.child.push({ [t2.tagname]: t2.child, ":@": t2[":@"] }) : this.child.push({ [t2.tagname]: t2.child }), void 0 !== e3 && (this.child[this.child.length - 1][pe] = { startIndex: e3 });
    }
    static getMetaDataSymbol() {
      return pe;
    }
  };
  var de = class {
    constructor(t2) {
      this.suppressValidationErr = !t2, this.options = t2;
    }
    readDocType(t2, e3) {
      const n2 = /* @__PURE__ */ Object.create(null);
      let r2 = 0;
      if ("O" !== t2[e3 + 3] || "C" !== t2[e3 + 4] || "T" !== t2[e3 + 5] || "Y" !== t2[e3 + 6] || "P" !== t2[e3 + 7] || "E" !== t2[e3 + 8]) throw new Error("Invalid Tag instead of DOCTYPE");
      {
        e3 += 9;
        let i2 = 1, s2 = false, o2 = false, a2 = "";
        for (; e3 < t2.length; e3++) if ("<" !== t2[e3] || o2) if (">" === t2[e3]) {
          if (o2 ? "-" === t2[e3 - 1] && "-" === t2[e3 - 2] && (o2 = false, i2--) : i2--, 0 === i2) break;
        } else "[" === t2[e3] ? s2 = true : a2 += t2[e3];
        else {
          if (s2 && me(t2, "!ENTITY", e3)) {
            let i3, s3;
            if (e3 += 7, [i3, s3, e3] = this.readEntityExp(t2, e3 + 1, this.suppressValidationErr), -1 === s3.indexOf("&")) {
              if (false !== this.options.enabled && null != this.options.maxEntityCount && r2 >= this.options.maxEntityCount) throw new Error(`Entity count (${r2 + 1}) exceeds maximum allowed (${this.options.maxEntityCount})`);
              n2[i3] = s3, r2++;
            }
          } else if (s2 && me(t2, "!ELEMENT", e3)) {
            e3 += 8;
            const { index: n3 } = this.readElementExp(t2, e3 + 1);
            e3 = n3;
          } else if (s2 && me(t2, "!ATTLIST", e3)) e3 += 8;
          else if (s2 && me(t2, "!NOTATION", e3)) {
            e3 += 9;
            const { index: n3 } = this.readNotationExp(t2, e3 + 1, this.suppressValidationErr);
            e3 = n3;
          } else {
            if (!me(t2, "!--", e3)) throw new Error("Invalid DOCTYPE");
            o2 = true;
          }
          i2++, a2 = "";
        }
        if (0 !== i2) throw new Error("Unclosed DOCTYPE");
      }
      return { entities: n2, i: e3 };
    }
    readEntityExp(t2, e3) {
      const n2 = e3 = ge(t2, e3);
      for (; e3 < t2.length && !/\s/.test(t2[e3]) && '"' !== t2[e3] && "'" !== t2[e3]; ) e3++;
      let r2 = t2.substring(n2, e3);
      if (ye(r2), e3 = ge(t2, e3), !this.suppressValidationErr) {
        if ("SYSTEM" === t2.substring(e3, e3 + 6).toUpperCase()) throw new Error("External entities are not supported");
        if ("%" === t2[e3]) throw new Error("Parameter entities are not supported");
      }
      let i2 = "";
      if ([e3, i2] = this.readIdentifierVal(t2, e3, "entity"), false !== this.options.enabled && null != this.options.maxEntitySize && i2.length > this.options.maxEntitySize) throw new Error(`Entity "${r2}" size (${i2.length}) exceeds maximum allowed size (${this.options.maxEntitySize})`);
      return [r2, i2, --e3];
    }
    readNotationExp(t2, e3) {
      const n2 = e3 = ge(t2, e3);
      for (; e3 < t2.length && !/\s/.test(t2[e3]); ) e3++;
      let r2 = t2.substring(n2, e3);
      !this.suppressValidationErr && ye(r2), e3 = ge(t2, e3);
      const i2 = t2.substring(e3, e3 + 6).toUpperCase();
      if (!this.suppressValidationErr && "SYSTEM" !== i2 && "PUBLIC" !== i2) throw new Error(`Expected SYSTEM or PUBLIC, found "${i2}"`);
      e3 += i2.length, e3 = ge(t2, e3);
      let s2 = null, o2 = null;
      if ("PUBLIC" === i2) [e3, s2] = this.readIdentifierVal(t2, e3, "publicIdentifier"), '"' !== t2[e3 = ge(t2, e3)] && "'" !== t2[e3] || ([e3, o2] = this.readIdentifierVal(t2, e3, "systemIdentifier"));
      else if ("SYSTEM" === i2 && ([e3, o2] = this.readIdentifierVal(t2, e3, "systemIdentifier"), !this.suppressValidationErr && !o2)) throw new Error("Missing mandatory system identifier for SYSTEM notation");
      return { notationName: r2, publicIdentifier: s2, systemIdentifier: o2, index: --e3 };
    }
    readIdentifierVal(t2, e3, n2) {
      let r2 = "";
      const i2 = t2[e3];
      if ('"' !== i2 && "'" !== i2) throw new Error(`Expected quoted string, found "${i2}"`);
      const s2 = ++e3;
      for (; e3 < t2.length && t2[e3] !== i2; ) e3++;
      if (r2 = t2.substring(s2, e3), t2[e3] !== i2) throw new Error(`Unterminated ${n2} value`);
      return [++e3, r2];
    }
    readElementExp(t2, e3) {
      const n2 = e3 = ge(t2, e3);
      for (; e3 < t2.length && !/\s/.test(t2[e3]); ) e3++;
      let r2 = t2.substring(n2, e3);
      if (!this.suppressValidationErr && !ie(r2)) throw new Error(`Invalid element name: "${r2}"`);
      let i2 = "";
      if ("E" === t2[e3 = ge(t2, e3)] && me(t2, "MPTY", e3)) e3 += 4;
      else if ("A" === t2[e3] && me(t2, "NY", e3)) e3 += 2;
      else if ("(" === t2[e3]) {
        const n3 = ++e3;
        for (; e3 < t2.length && ")" !== t2[e3]; ) e3++;
        if (i2 = t2.substring(n3, e3), ")" !== t2[e3]) throw new Error("Unterminated content model");
      } else if (!this.suppressValidationErr) throw new Error(`Invalid Element Expression, found "${t2[e3]}"`);
      return { elementName: r2, contentModel: i2.trim(), index: e3 };
    }
    readAttlistExp(t2, e3) {
      let n2 = e3 = ge(t2, e3);
      for (; e3 < t2.length && !/\s/.test(t2[e3]); ) e3++;
      let r2 = t2.substring(n2, e3);
      for (ye(r2), n2 = e3 = ge(t2, e3); e3 < t2.length && !/\s/.test(t2[e3]); ) e3++;
      let i2 = t2.substring(n2, e3);
      if (!ye(i2)) throw new Error(`Invalid attribute name: "${i2}"`);
      e3 = ge(t2, e3);
      let s2 = "";
      if ("NOTATION" === t2.substring(e3, e3 + 8).toUpperCase()) {
        if (s2 = "NOTATION", "(" !== t2[e3 = ge(t2, e3 += 8)]) throw new Error(`Expected '(', found "${t2[e3]}"`);
        e3++;
        let n3 = [];
        for (; e3 < t2.length && ")" !== t2[e3]; ) {
          const r3 = e3;
          for (; e3 < t2.length && "|" !== t2[e3] && ")" !== t2[e3]; ) e3++;
          let i3 = t2.substring(r3, e3);
          if (i3 = i3.trim(), !ye(i3)) throw new Error(`Invalid notation name: "${i3}"`);
          n3.push(i3), "|" === t2[e3] && (e3++, e3 = ge(t2, e3));
        }
        if (")" !== t2[e3]) throw new Error("Unterminated list of notations");
        e3++, s2 += " (" + n3.join("|") + ")";
      } else {
        const n3 = e3;
        for (; e3 < t2.length && !/\s/.test(t2[e3]); ) e3++;
        s2 += t2.substring(n3, e3);
        const r3 = ["CDATA", "ID", "IDREF", "IDREFS", "ENTITY", "ENTITIES", "NMTOKEN", "NMTOKENS"];
        if (!this.suppressValidationErr && !r3.includes(s2.toUpperCase())) throw new Error(`Invalid attribute type: "${s2}"`);
      }
      e3 = ge(t2, e3);
      let o2 = "";
      return "#REQUIRED" === t2.substring(e3, e3 + 8).toUpperCase() ? (o2 = "#REQUIRED", e3 += 8) : "#IMPLIED" === t2.substring(e3, e3 + 7).toUpperCase() ? (o2 = "#IMPLIED", e3 += 7) : [e3, o2] = this.readIdentifierVal(t2, e3, "ATTLIST"), { elementName: r2, attributeName: i2, attributeType: s2, defaultValue: o2, index: e3 };
    }
  };
  var ge = (t2, e3) => {
    for (; e3 < t2.length && /\s/.test(t2[e3]); ) e3++;
    return e3;
  };
  function me(t2, e3, n2) {
    for (let r2 = 0; r2 < e3.length; r2++) if (e3[r2] !== t2[n2 + r2 + 1]) return false;
    return true;
  }
  function ye(t2) {
    if (ie(t2)) return t2;
    throw new Error(`Invalid entity name ${t2}`);
  }
  var be = /^[-+]?0x[a-fA-F0-9]+$/;
  var ve = /^([\-\+])?(0*)([0-9]*(\.[0-9]*)?)$/;
  var we = { hex: true, leadingZeros: true, decimalPoint: ".", eNotation: true, infinity: "original" };
  var xe = /^([-+])?(0*)(\d*(\.\d*)?[eE][-\+]?\d+)$/;
  var Ne = class {
    constructor(t2) {
      this._matcher = t2;
    }
    get separator() {
      return this._matcher.separator;
    }
    getCurrentTag() {
      const t2 = this._matcher.path;
      return t2.length > 0 ? t2[t2.length - 1].tag : void 0;
    }
    getCurrentNamespace() {
      const t2 = this._matcher.path;
      return t2.length > 0 ? t2[t2.length - 1].namespace : void 0;
    }
    getAttrValue(t2) {
      const e3 = this._matcher.path;
      if (0 !== e3.length) return e3[e3.length - 1].values?.[t2];
    }
    hasAttr(t2) {
      const e3 = this._matcher.path;
      if (0 === e3.length) return false;
      const n2 = e3[e3.length - 1];
      return void 0 !== n2.values && t2 in n2.values;
    }
    getPosition() {
      const t2 = this._matcher.path;
      return 0 === t2.length ? -1 : t2[t2.length - 1].position ?? 0;
    }
    getCounter() {
      const t2 = this._matcher.path;
      return 0 === t2.length ? -1 : t2[t2.length - 1].counter ?? 0;
    }
    getIndex() {
      return this.getPosition();
    }
    getDepth() {
      return this._matcher.path.length;
    }
    toString(t2) {
      let e3 = !(arguments.length > 1 && void 0 !== arguments[1]) || arguments[1];
      return this._matcher.toString(t2, e3);
    }
    toArray() {
      return this._matcher.path.map(((t2) => t2.tag));
    }
    matches(t2) {
      return this._matcher.matches(t2);
    }
    matchesAny(t2) {
      return t2.matchesAny(this._matcher);
    }
  };
  var Ee = class {
    constructor() {
      let t2 = arguments.length > 0 && void 0 !== arguments[0] ? arguments[0] : {};
      this.separator = t2.separator || ".", this.path = [], this.siblingStacks = [], this._pathStringCache = null, this._view = new Ne(this);
    }
    push(t2) {
      let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : null, n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : null;
      this._pathStringCache = null, this.path.length > 0 && (this.path[this.path.length - 1].values = void 0);
      const r2 = this.path.length;
      this.siblingStacks[r2] || (this.siblingStacks[r2] = /* @__PURE__ */ new Map());
      const i2 = this.siblingStacks[r2], s2 = n2 ? `${n2}:${t2}` : t2, o2 = i2.get(s2) || 0;
      let a2 = 0;
      for (const t3 of i2.values()) a2 += t3;
      i2.set(s2, o2 + 1);
      const h2 = { tag: t2, position: a2, counter: o2 };
      null != n2 && (h2.namespace = n2), null != e3 && (h2.values = e3), this.path.push(h2);
    }
    pop() {
      if (0 === this.path.length) return;
      this._pathStringCache = null;
      const t2 = this.path.pop();
      return this.siblingStacks.length > this.path.length + 1 && (this.siblingStacks.length = this.path.length + 1), t2;
    }
    updateCurrent(t2) {
      if (this.path.length > 0) {
        const e3 = this.path[this.path.length - 1];
        null != t2 && (e3.values = t2);
      }
    }
    getCurrentTag() {
      return this.path.length > 0 ? this.path[this.path.length - 1].tag : void 0;
    }
    getCurrentNamespace() {
      return this.path.length > 0 ? this.path[this.path.length - 1].namespace : void 0;
    }
    getAttrValue(t2) {
      if (0 !== this.path.length) return this.path[this.path.length - 1].values?.[t2];
    }
    hasAttr(t2) {
      if (0 === this.path.length) return false;
      const e3 = this.path[this.path.length - 1];
      return void 0 !== e3.values && t2 in e3.values;
    }
    getPosition() {
      return 0 === this.path.length ? -1 : this.path[this.path.length - 1].position ?? 0;
    }
    getCounter() {
      return 0 === this.path.length ? -1 : this.path[this.path.length - 1].counter ?? 0;
    }
    getIndex() {
      return this.getPosition();
    }
    getDepth() {
      return this.path.length;
    }
    toString(t2) {
      let e3 = !(arguments.length > 1 && void 0 !== arguments[1]) || arguments[1];
      const n2 = t2 || this.separator;
      if (n2 === this.separator && true === e3) {
        if (null !== this._pathStringCache) return this._pathStringCache;
        const t3 = this.path.map(((t4) => t4.namespace ? `${t4.namespace}:${t4.tag}` : t4.tag)).join(n2);
        return this._pathStringCache = t3, t3;
      }
      return this.path.map(((t3) => e3 && t3.namespace ? `${t3.namespace}:${t3.tag}` : t3.tag)).join(n2);
    }
    toArray() {
      return this.path.map(((t2) => t2.tag));
    }
    reset() {
      this._pathStringCache = null, this.path = [], this.siblingStacks = [];
    }
    matches(t2) {
      const e3 = t2.segments;
      return 0 !== e3.length && (t2.hasDeepWildcard() ? this._matchWithDeepWildcard(e3) : this._matchSimple(e3));
    }
    _matchSimple(t2) {
      if (this.path.length !== t2.length) return false;
      for (let e3 = 0; e3 < t2.length; e3++) if (!this._matchSegment(t2[e3], this.path[e3], e3 === this.path.length - 1)) return false;
      return true;
    }
    _matchWithDeepWildcard(t2) {
      let e3 = this.path.length - 1, n2 = t2.length - 1;
      for (; n2 >= 0 && e3 >= 0; ) {
        const r2 = t2[n2];
        if ("deep-wildcard" === r2.type) {
          if (n2--, n2 < 0) return true;
          const r3 = t2[n2];
          let i2 = false;
          for (let t3 = e3; t3 >= 0; t3--) if (this._matchSegment(r3, this.path[t3], t3 === this.path.length - 1)) {
            e3 = t3 - 1, n2--, i2 = true;
            break;
          }
          if (!i2) return false;
        } else {
          if (!this._matchSegment(r2, this.path[e3], e3 === this.path.length - 1)) return false;
          e3--, n2--;
        }
      }
      return n2 < 0;
    }
    _matchSegment(t2, e3, n2) {
      if ("*" !== t2.tag && t2.tag !== e3.tag) return false;
      if (void 0 !== t2.namespace && "*" !== t2.namespace && t2.namespace !== e3.namespace) return false;
      if (void 0 !== t2.attrName) {
        if (!n2) return false;
        if (!e3.values || !(t2.attrName in e3.values)) return false;
        if (void 0 !== t2.attrValue && String(e3.values[t2.attrName]) !== String(t2.attrValue)) return false;
      }
      if (void 0 !== t2.position) {
        if (!n2) return false;
        const r2 = e3.counter ?? 0;
        if ("first" === t2.position && 0 !== r2) return false;
        if ("odd" === t2.position && r2 % 2 != 1) return false;
        if ("even" === t2.position && r2 % 2 != 0) return false;
        if ("nth" === t2.position && r2 !== t2.positionValue) return false;
      }
      return true;
    }
    matchesAny(t2) {
      return t2.matchesAny(this);
    }
    snapshot() {
      return { path: this.path.map(((t2) => ({ ...t2 }))), siblingStacks: this.siblingStacks.map(((t2) => new Map(t2))) };
    }
    restore(t2) {
      this._pathStringCache = null, this.path = t2.path.map(((t3) => ({ ...t3 }))), this.siblingStacks = t2.siblingStacks.map(((t3) => new Map(t3)));
    }
    readOnly() {
      return this._view;
    }
  };
  var Ae = class {
    constructor(t2) {
      let e3 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {}, n2 = arguments.length > 2 ? arguments[2] : void 0;
      this.pattern = t2, this.separator = e3.separator || ".", this.segments = this._parse(t2), this.data = n2, this._hasDeepWildcard = this.segments.some(((t3) => "deep-wildcard" === t3.type)), this._hasAttributeCondition = this.segments.some(((t3) => void 0 !== t3.attrName)), this._hasPositionSelector = this.segments.some(((t3) => void 0 !== t3.position));
    }
    _parse(t2) {
      const e3 = [];
      let n2 = 0, r2 = "";
      for (; n2 < t2.length; ) t2[n2] === this.separator ? n2 + 1 < t2.length && t2[n2 + 1] === this.separator ? (r2.trim() && (e3.push(this._parseSegment(r2.trim())), r2 = ""), e3.push({ type: "deep-wildcard" }), n2 += 2) : (r2.trim() && e3.push(this._parseSegment(r2.trim())), r2 = "", n2++) : (r2 += t2[n2], n2++);
      return r2.trim() && e3.push(this._parseSegment(r2.trim())), e3;
    }
    _parseSegment(t2) {
      const e3 = { type: "tag" };
      let n2 = null, r2 = t2;
      const i2 = t2.match(/^([^\[]+)(\[[^\]]*\])(.*)$/);
      if (i2 && (r2 = i2[1] + i2[3], i2[2])) {
        const t3 = i2[2].slice(1, -1);
        t3 && (n2 = t3);
      }
      let s2, o2, a2 = r2;
      if (r2.includes("::")) {
        const e4 = r2.indexOf("::");
        if (s2 = r2.substring(0, e4).trim(), a2 = r2.substring(e4 + 2).trim(), !s2) throw new Error(`Invalid namespace in pattern: ${t2}`);
      }
      let h2 = null;
      if (a2.includes(":")) {
        const t3 = a2.lastIndexOf(":"), e4 = a2.substring(0, t3).trim(), n3 = a2.substring(t3 + 1).trim();
        ["first", "last", "odd", "even"].includes(n3) || /^nth\(\d+\)$/.test(n3) ? (o2 = e4, h2 = n3) : o2 = a2;
      } else o2 = a2;
      if (!o2) throw new Error(`Invalid segment pattern: ${t2}`);
      if (e3.tag = o2, s2 && (e3.namespace = s2), n2) if (n2.includes("=")) {
        const t3 = n2.indexOf("=");
        e3.attrName = n2.substring(0, t3).trim(), e3.attrValue = n2.substring(t3 + 1).trim();
      } else e3.attrName = n2.trim();
      if (h2) {
        const t3 = h2.match(/^nth\((\d+)\)$/);
        t3 ? (e3.position = "nth", e3.positionValue = parseInt(t3[1], 10)) : e3.position = h2;
      }
      return e3;
    }
    get length() {
      return this.segments.length;
    }
    hasDeepWildcard() {
      return this._hasDeepWildcard;
    }
    hasAttributeCondition() {
      return this._hasAttributeCondition;
    }
    hasPositionSelector() {
      return this._hasPositionSelector;
    }
    toString() {
      return this.pattern;
    }
  };
  var Se = class {
    constructor() {
      this._byDepthAndTag = /* @__PURE__ */ new Map(), this._wildcardByDepth = /* @__PURE__ */ new Map(), this._deepWildcards = [], this._patterns = /* @__PURE__ */ new Set(), this._sealed = false;
    }
    add(t2) {
      if (this._sealed) throw new TypeError("ExpressionSet is sealed. Create a new ExpressionSet to add more expressions.");
      if (this._patterns.has(t2.pattern)) return this;
      if (this._patterns.add(t2.pattern), t2.hasDeepWildcard()) return this._deepWildcards.push(t2), this;
      const e3 = t2.length, n2 = t2.segments[t2.segments.length - 1], r2 = n2?.tag;
      if (r2 && "*" !== r2) {
        const n3 = `${e3}:${r2}`;
        this._byDepthAndTag.has(n3) || this._byDepthAndTag.set(n3, []), this._byDepthAndTag.get(n3).push(t2);
      } else this._wildcardByDepth.has(e3) || this._wildcardByDepth.set(e3, []), this._wildcardByDepth.get(e3).push(t2);
      return this;
    }
    addAll(t2) {
      for (const e3 of t2) this.add(e3);
      return this;
    }
    has(t2) {
      return this._patterns.has(t2.pattern);
    }
    get size() {
      return this._patterns.size;
    }
    seal() {
      return this._sealed = true, this;
    }
    get isSealed() {
      return this._sealed;
    }
    matchesAny(t2) {
      return null !== this.findMatch(t2);
    }
    findMatch(t2) {
      const e3 = t2.getDepth(), n2 = `${e3}:${t2.getCurrentTag()}`, r2 = this._byDepthAndTag.get(n2);
      if (r2) {
        for (let e4 = 0; e4 < r2.length; e4++) if (t2.matches(r2[e4])) return r2[e4];
      }
      const i2 = this._wildcardByDepth.get(e3);
      if (i2) {
        for (let e4 = 0; e4 < i2.length; e4++) if (t2.matches(i2[e4])) return i2[e4];
      }
      for (let e4 = 0; e4 < this._deepWildcards.length; e4++) if (t2.matches(this._deepWildcards[e4])) return this._deepWildcards[e4];
      return null;
    }
  };
  var Pe = { cent: "\xA2", pound: "\xA3", curren: "\xA4", yen: "\xA5", euro: "\u20AC", dollar: "$", euro: "\u20AC", fnof: "\u0192", inr: "\u20B9", af: "\u060B", birr: "\u1265\u122D", peso: "\u20B1", rub: "\u20BD", won: "\u20A9", yuan: "\xA5", cedil: "\xB8" };
  var Te = { amp: "&", apos: "'", gt: ">", lt: "<", quot: '"' };
  var Oe = { nbsp: "\xA0", copy: "\xA9", reg: "\xAE", trade: "\u2122", mdash: "\u2014", ndash: "\u2013", hellip: "\u2026", laquo: "\xAB", raquo: "\xBB", lsquo: "\u2018", rsquo: "\u2019", ldquo: "\u201C", rdquo: "\u201D", bull: "\u2022", para: "\xB6", sect: "\xA7", deg: "\xB0", frac12: "\xBD", frac14: "\xBC", frac34: "\xBE" };
  var Ce = new Set("!?\\\\/[]$%{}^&*()<>|+");
  function _e2(t2) {
    if ("#" === t2[0]) throw new Error(`[EntityReplacer] Invalid character '#' in entity name: "${t2}"`);
    for (const e3 of t2) if (Ce.has(e3)) throw new Error(`[EntityReplacer] Invalid character '${e3}' in entity name: "${t2}"`);
    return t2;
  }
  function $e() {
    const t2 = /* @__PURE__ */ Object.create(null);
    for (var e3 = arguments.length, n2 = new Array(e3), r2 = 0; r2 < e3; r2++) n2[r2] = arguments[r2];
    for (const e4 of n2) if (e4) for (const n3 of Object.keys(e4)) {
      const r3 = e4[n3];
      if ("string" == typeof r3) t2[n3] = r3;
      else if (r3 && "object" == typeof r3 && void 0 !== r3.val) {
        const e5 = r3.val;
        "string" == typeof e5 && (t2[n3] = e5);
      }
    }
    return t2;
  }
  var je = "external";
  var Ie = "base";
  var Me = "all";
  var Re = Object.freeze({ allow: 0, leave: 1, remove: 2, throw: 3 });
  var ke = /* @__PURE__ */ new Set([9, 10, 13]);
  var Le = class {
    constructor() {
      let t2 = arguments.length > 0 && void 0 !== arguments[0] ? arguments[0] : {};
      var e3;
      this._limit = t2.limit || {}, this._maxTotalExpansions = this._limit.maxTotalExpansions || 0, this._maxExpandedLength = this._limit.maxExpandedLength || 0, this._postCheck = "function" == typeof t2.postCheck ? t2.postCheck : (t3) => t3, this._limitTiers = (e3 = this._limit.applyLimitsTo ?? je) && e3 !== je ? e3 === Me ? /* @__PURE__ */ new Set([Me]) : e3 === Ie ? /* @__PURE__ */ new Set([Ie]) : Array.isArray(e3) ? new Set(e3) : /* @__PURE__ */ new Set([je]) : /* @__PURE__ */ new Set([je]), this._numericAllowed = t2.numericAllowed ?? true, this._baseMap = $e(Te, t2.namedEntities || null), this._externalMap = /* @__PURE__ */ Object.create(null), this._inputMap = /* @__PURE__ */ Object.create(null), this._totalExpansions = 0, this._expandedLength = 0, this._removeSet = new Set(t2.remove && Array.isArray(t2.remove) ? t2.remove : []), this._leaveSet = new Set(t2.leave && Array.isArray(t2.leave) ? t2.leave : []);
      const n2 = (function(t3) {
        if (!t3) return { xmlVersion: 1, onLevel: Re.allow, nullLevel: Re.remove };
        const e4 = 1.1 === t3.xmlVersion ? 1.1 : 1, n3 = Re[t3.onNCR] ?? Re.allow, r2 = Re[t3.nullNCR] ?? Re.remove;
        return { xmlVersion: e4, onLevel: n3, nullLevel: Math.max(r2, Re.remove) };
      })(t2.ncr);
      this._ncrXmlVersion = n2.xmlVersion, this._ncrOnLevel = n2.onLevel, this._ncrNullLevel = n2.nullLevel;
    }
    setExternalEntities(t2) {
      if (t2) for (const e3 of Object.keys(t2)) _e2(e3);
      this._externalMap = $e(t2);
    }
    addExternalEntity(t2, e3) {
      _e2(t2), "string" == typeof e3 && -1 === e3.indexOf("&") && (this._externalMap[t2] = e3);
    }
    addInputEntities(t2) {
      this._totalExpansions = 0, this._expandedLength = 0, this._inputMap = $e(t2);
    }
    reset() {
      return this._inputMap = /* @__PURE__ */ Object.create(null), this._totalExpansions = 0, this._expandedLength = 0, this;
    }
    setXmlVersion(t2) {
      this._ncrXmlVersion = 1.1 === t2 ? 1.1 : 1;
    }
    decode(t2) {
      if ("string" != typeof t2 || 0 === t2.length) return t2;
      const e3 = t2, n2 = [], r2 = t2.length;
      let i2 = 0, s2 = 0;
      const o2 = this._maxTotalExpansions > 0, a2 = this._maxExpandedLength > 0, h2 = o2 || a2;
      for (; s2 < r2; ) {
        if (38 !== t2.charCodeAt(s2)) {
          s2++;
          continue;
        }
        let e4 = s2 + 1;
        for (; e4 < r2 && 59 !== t2.charCodeAt(e4) && e4 - s2 <= 32; ) e4++;
        if (e4 >= r2 || 59 !== t2.charCodeAt(e4)) {
          s2++;
          continue;
        }
        const l3 = t2.slice(s2 + 1, e4);
        if (0 === l3.length) {
          s2++;
          continue;
        }
        let u2, c2;
        if (this._removeSet.has(l3)) u2 = "", void 0 === c2 && (c2 = je);
        else {
          if (this._leaveSet.has(l3)) {
            s2++;
            continue;
          }
          if (35 === l3.charCodeAt(0)) {
            const t3 = this._resolveNCR(l3);
            if (void 0 === t3) {
              s2++;
              continue;
            }
            u2 = t3, c2 = Ie;
          } else {
            const t3 = this._resolveName(l3);
            u2 = t3?.value, c2 = t3?.tier;
          }
        }
        if (void 0 !== u2) {
          if (s2 > i2 && n2.push(t2.slice(i2, s2)), n2.push(u2), i2 = e4 + 1, s2 = i2, h2 && this._tierCounts(c2)) {
            if (o2 && (this._totalExpansions++, this._totalExpansions > this._maxTotalExpansions)) throw new Error(`[EntityReplacer] Entity expansion count limit exceeded: ${this._totalExpansions} > ${this._maxTotalExpansions}`);
            if (a2) {
              const t3 = u2.length - (l3.length + 2);
              if (t3 > 0 && (this._expandedLength += t3, this._expandedLength > this._maxExpandedLength)) throw new Error(`[EntityReplacer] Expanded content length limit exceeded: ${this._expandedLength} > ${this._maxExpandedLength}`);
            }
          }
        } else s2++;
      }
      i2 < r2 && n2.push(t2.slice(i2));
      const l2 = 0 === n2.length ? t2 : n2.join("");
      return this._postCheck(l2, e3);
    }
    _tierCounts(t2) {
      return !!this._limitTiers.has(Me) || this._limitTiers.has(t2);
    }
    _resolveName(t2) {
      return t2 in this._inputMap ? { value: this._inputMap[t2], tier: je } : t2 in this._externalMap ? { value: this._externalMap[t2], tier: je } : t2 in this._baseMap ? { value: this._baseMap[t2], tier: Ie } : void 0;
    }
    _classifyNCR(t2) {
      return 0 === t2 ? this._ncrNullLevel : t2 >= 55296 && t2 <= 57343 || 1 === this._ncrXmlVersion && t2 >= 1 && t2 <= 31 && !ke.has(t2) ? Re.remove : -1;
    }
    _applyNCRAction(t2, e3, n2) {
      switch (t2) {
        case Re.allow:
          return String.fromCodePoint(n2);
        case Re.remove:
          return "";
        case Re.leave:
          return;
        case Re.throw:
          throw new Error(`[EntityDecoder] Prohibited numeric character reference &${e3}; (U+${n2.toString(16).toUpperCase().padStart(4, "0")})`);
        default:
          return String.fromCodePoint(n2);
      }
    }
    _resolveNCR(t2) {
      const e3 = t2.charCodeAt(1);
      let n2;
      if (n2 = 120 === e3 || 88 === e3 ? parseInt(t2.slice(2), 16) : parseInt(t2.slice(1), 10), Number.isNaN(n2) || n2 < 0 || n2 > 1114111) return;
      const r2 = this._classifyNCR(n2);
      if (!this._numericAllowed && r2 < Re.remove) return;
      const i2 = -1 === r2 ? this._ncrOnLevel : Math.max(this._ncrOnLevel, r2);
      return this._applyNCRAction(i2, t2, n2);
    }
  };
  function De(t2, e3) {
    if (!t2) return {};
    const n2 = e3.attributesGroupName ? t2[e3.attributesGroupName] : t2;
    if (!n2) return {};
    const r2 = {};
    for (const t3 in n2) t3.startsWith(e3.attributeNamePrefix) ? r2[t3.substring(e3.attributeNamePrefix.length)] = n2[t3] : r2[t3] = n2[t3];
    return r2;
  }
  function Ue(t2) {
    if (!t2 || "string" != typeof t2) return;
    const e3 = t2.indexOf(":");
    if (-1 !== e3 && e3 > 0) {
      const n2 = t2.substring(0, e3);
      if ("xmlns" !== n2) return n2;
    }
  }
  var Fe = class {
    constructor(t2, e3) {
      var n2;
      this.options = t2, this.currentNode = null, this.tagsNodeStack = [], this.parseXml = ze, this.parseTextData = Ve, this.resolveNameSpace = We, this.buildAttributesMap = Ge, this.isItStopNode = Xe, this.replaceEntitiesValue = He, this.readStopNodeData = Qe, this.saveTextToParentTag = Ye, this.addChild = qe, this.ignoreAttributesFn = "function" == typeof (n2 = this.options.ignoreAttributes) ? n2 : Array.isArray(n2) ? (t3) => {
        for (const e4 of n2) {
          if ("string" == typeof e4 && t3 === e4) return true;
          if (e4 instanceof RegExp && e4.test(t3)) return true;
        }
      } : () => false, this.entityExpansionCount = 0, this.currentExpandedLength = 0;
      let r2 = { ...Te };
      this.options.entityDecoder ? this.entityDecoder = this.options.entityDecoder : ("object" == typeof this.options.htmlEntities ? r2 = this.options.htmlEntities : true === this.options.htmlEntities && (r2 = { ...Oe, ...Pe }), this.entityDecoder = new Le({ namedEntities: { ...r2, ...e3 }, numericAllowed: this.options.htmlEntities, limit: { maxTotalExpansions: this.options.processEntities.maxTotalExpansions, maxExpandedLength: this.options.processEntities.maxExpandedLength, applyLimitsTo: this.options.processEntities.appliesTo } })), this.matcher = new Ee(), this.readonlyMatcher = this.matcher.readOnly(), this.isCurrentNodeStopNode = false, this.stopNodeExpressionsSet = new Se();
      const i2 = this.options.stopNodes;
      if (i2 && i2.length > 0) {
        for (let t3 = 0; t3 < i2.length; t3++) {
          const e4 = i2[t3];
          "string" == typeof e4 ? this.stopNodeExpressionsSet.add(new Ae(e4)) : e4 instanceof Ae && this.stopNodeExpressionsSet.add(e4);
        }
        this.stopNodeExpressionsSet.seal();
      }
    }
  };
  function Ve(t2, e3, n2, r2, i2, s2, o2) {
    const a2 = this.options;
    if (void 0 !== t2 && (a2.trimValues && !r2 && (t2 = t2.trim()), t2.length > 0)) {
      o2 || (t2 = this.replaceEntitiesValue(t2, e3, n2));
      const r3 = a2.jPath ? n2.toString() : n2, h2 = a2.tagValueProcessor(e3, t2, r3, i2, s2);
      return null == h2 ? t2 : typeof h2 != typeof t2 || h2 !== t2 ? h2 : a2.trimValues || t2.trim() === t2 ? tn(t2, a2.parseTagValue, a2.numberParseOptions) : t2;
    }
  }
  function We(t2) {
    if (this.options.removeNSPrefix) {
      const e3 = t2.split(":"), n2 = "/" === t2.charAt(0) ? "/" : "";
      if ("xmlns" === e3[0]) return "";
      2 === e3.length && (t2 = n2 + e3[1]);
    }
    return t2;
  }
  var Be = new RegExp(`([^\\s=]+)\\s*(=\\s*(['"])([\\s\\S]*?)\\3)?`, "gm");
  function Ge(t2, e3, n2) {
    let r2 = arguments.length > 3 && void 0 !== arguments[3] && arguments[3];
    const i2 = this.options;
    if (true === r2 || true !== i2.ignoreAttributes && "string" == typeof t2) {
      const r3 = re(t2, Be), s2 = r3.length, o2 = {}, a2 = new Array(s2);
      let h2 = false;
      const l2 = {};
      for (let t3 = 0; t3 < s2; t3++) {
        const e4 = this.resolveNameSpace(r3[t3][1]), s3 = r3[t3][4];
        if (e4.length && void 0 !== s3) {
          let r4 = s3;
          i2.trimValues && (r4 = r4.trim()), r4 = this.replaceEntitiesValue(r4, n2, this.readonlyMatcher), a2[t3] = r4, l2[e4] = r4, h2 = true;
        }
      }
      h2 && "object" == typeof e3 && e3.updateCurrent && e3.updateCurrent(l2);
      const u2 = i2.jPath ? e3.toString() : this.readonlyMatcher;
      let c2 = false;
      for (let t3 = 0; t3 < s2; t3++) {
        const e4 = this.resolveNameSpace(r3[t3][1]);
        if (this.ignoreAttributesFn(e4, u2)) continue;
        let n3 = i2.attributeNamePrefix + e4;
        if (e4.length) if (i2.transformAttributeName && (n3 = i2.transformAttributeName(n3)), n3 = nn(n3, i2), void 0 !== r3[t3][4]) {
          const r4 = a2[t3], s3 = i2.attributeValueProcessor(e4, r4, u2);
          o2[n3] = null == s3 ? r4 : typeof s3 != typeof r4 || s3 !== r4 ? s3 : tn(r4, i2.parseAttributeValue, i2.numberParseOptions), c2 = true;
        } else i2.allowBooleanAttributes && (o2[n3] = true, c2 = true);
      }
      if (!c2) return;
      if (i2.attributesGroupName && !i2.preserveOrder) {
        const t3 = {};
        return t3[i2.attributesGroupName] = o2, t3;
      }
      return o2;
    }
  }
  var ze = function(t2) {
    t2 = t2.replace(/\r\n?/g, "\n");
    const e3 = new fe("!xml");
    let n2 = e3, r2 = "";
    this.matcher.reset(), this.entityDecoder.reset(), this.entityExpansionCount = 0, this.currentExpandedLength = 0;
    const i2 = this.options, s2 = new de(i2.processEntities), o2 = t2.length;
    for (let a2 = 0; a2 < o2; a2++) if ("<" === t2[a2]) {
      const h2 = t2.charCodeAt(a2 + 1);
      if (47 === h2) {
        const e4 = Ze(t2, ">", a2, "Closing Tag is not closed.");
        let s3 = t2.substring(a2 + 2, e4).trim();
        if (i2.removeNSPrefix) {
          const t3 = s3.indexOf(":");
          -1 !== t3 && (s3 = s3.substr(t3 + 1));
        }
        s3 = en(i2.transformTagName, s3, "", i2).tagName, n2 && (r2 = this.saveTextToParentTag(r2, n2, this.readonlyMatcher));
        const o3 = this.matcher.getCurrentTag();
        if (s3 && i2.unpairedTagsSet.has(s3)) throw new Error(`Unpaired tag can not be used as closing tag: </${s3}>`);
        o3 && i2.unpairedTagsSet.has(o3) && (this.matcher.pop(), this.tagsNodeStack.pop()), this.matcher.pop(), this.isCurrentNodeStopNode = false, n2 = this.tagsNodeStack.pop(), r2 = "", a2 = e4;
      } else if (63 === h2) {
        let e4 = Ke(t2, a2, false, "?>");
        if (!e4) throw new Error("Pi Tag is not closed.");
        r2 = this.saveTextToParentTag(r2, n2, this.readonlyMatcher);
        const s3 = this.buildAttributesMap(e4.tagExp, this.matcher, e4.tagName, true);
        if (s3) {
          const t3 = s3[this.options.attributeNamePrefix + "version"];
          this.entityDecoder.setXmlVersion(Number(t3) || 1);
        }
        if (i2.ignoreDeclaration && "?xml" === e4.tagName || i2.ignorePiTags) ;
        else {
          const t3 = new fe(e4.tagName);
          t3.add(i2.textNodeName, ""), e4.tagName !== e4.tagExp && e4.attrExpPresent && true !== i2.ignoreAttributes && (t3[":@"] = s3), this.addChild(n2, t3, this.readonlyMatcher, a2);
        }
        a2 = e4.closeIndex + 1;
      } else if (33 === h2 && 45 === t2.charCodeAt(a2 + 2) && 45 === t2.charCodeAt(a2 + 3)) {
        const e4 = Ze(t2, "-->", a2 + 4, "Comment is not closed.");
        if (i2.commentPropName) {
          const s3 = t2.substring(a2 + 4, e4 - 2);
          r2 = this.saveTextToParentTag(r2, n2, this.readonlyMatcher), n2.add(i2.commentPropName, [{ [i2.textNodeName]: s3 }]);
        }
        a2 = e4;
      } else if (33 === h2 && 68 === t2.charCodeAt(a2 + 2)) {
        const e4 = s2.readDocType(t2, a2);
        this.entityDecoder.addInputEntities(e4.entities), a2 = e4.i;
      } else if (33 === h2 && 91 === t2.charCodeAt(a2 + 2)) {
        const e4 = Ze(t2, "]]>", a2, "CDATA is not closed.") - 2, s3 = t2.substring(a2 + 9, e4);
        r2 = this.saveTextToParentTag(r2, n2, this.readonlyMatcher);
        let o3 = this.parseTextData(s3, n2.tagname, this.readonlyMatcher, true, false, true, true);
        null == o3 && (o3 = ""), i2.cdataPropName ? n2.add(i2.cdataPropName, [{ [i2.textNodeName]: s3 }]) : n2.add(i2.textNodeName, o3), a2 = e4 + 2;
      } else {
        let s3 = Ke(t2, a2, i2.removeNSPrefix);
        if (!s3) {
          const e4 = t2.substring(Math.max(0, a2 - 50), Math.min(o2, a2 + 50));
          throw new Error(`readTagExp returned undefined at position ${a2}. Context: "${e4}"`);
        }
        let h3 = s3.tagName;
        const l2 = s3.rawTagName;
        let u2 = s3.tagExp, c2 = s3.attrExpPresent, p2 = s3.closeIndex;
        if ({ tagName: h3, tagExp: u2 } = en(i2.transformTagName, h3, u2, i2), i2.strictReservedNames && (h3 === i2.commentPropName || h3 === i2.cdataPropName || h3 === i2.textNodeName || h3 === i2.attributesGroupName)) throw new Error(`Invalid tag name: ${h3}`);
        n2 && r2 && "!xml" !== n2.tagname && (r2 = this.saveTextToParentTag(r2, n2, this.readonlyMatcher, false));
        const f = n2;
        f && i2.unpairedTagsSet.has(f.tagname) && (n2 = this.tagsNodeStack.pop(), this.matcher.pop());
        let d2 = false;
        u2.length > 0 && u2.lastIndexOf("/") === u2.length - 1 && (d2 = true, "/" === h3[h3.length - 1] ? (h3 = h3.substr(0, h3.length - 1), u2 = h3) : u2 = u2.substr(0, u2.length - 1), c2 = h3 !== u2);
        let g, m2 = null, y2 = {};
        g = Ue(l2), h3 !== e3.tagname && this.matcher.push(h3, {}, g), h3 !== u2 && c2 && (m2 = this.buildAttributesMap(u2, this.matcher, h3), m2 && (y2 = De(m2, i2))), h3 !== e3.tagname && (this.isCurrentNodeStopNode = this.isItStopNode());
        const b2 = a2;
        if (this.isCurrentNodeStopNode) {
          let e4 = "";
          if (d2) a2 = s3.closeIndex;
          else if (i2.unpairedTagsSet.has(h3)) a2 = s3.closeIndex;
          else {
            const n3 = this.readStopNodeData(t2, l2, p2 + 1);
            if (!n3) throw new Error(`Unexpected end of ${l2}`);
            a2 = n3.i, e4 = n3.tagContent;
          }
          const r3 = new fe(h3);
          m2 && (r3[":@"] = m2), r3.add(i2.textNodeName, e4), this.matcher.pop(), this.isCurrentNodeStopNode = false, this.addChild(n2, r3, this.readonlyMatcher, b2);
        } else {
          if (d2) {
            ({ tagName: h3, tagExp: u2 } = en(i2.transformTagName, h3, u2, i2));
            const t3 = new fe(h3);
            m2 && (t3[":@"] = m2), this.addChild(n2, t3, this.readonlyMatcher, b2), this.matcher.pop(), this.isCurrentNodeStopNode = false;
          } else {
            if (i2.unpairedTagsSet.has(h3)) {
              const t3 = new fe(h3);
              m2 && (t3[":@"] = m2), this.addChild(n2, t3, this.readonlyMatcher, b2), this.matcher.pop(), this.isCurrentNodeStopNode = false, a2 = s3.closeIndex;
              continue;
            }
            {
              const t3 = new fe(h3);
              if (this.tagsNodeStack.length > i2.maxNestedTags) throw new Error("Maximum nested tags exceeded");
              this.tagsNodeStack.push(n2), m2 && (t3[":@"] = m2), this.addChild(n2, t3, this.readonlyMatcher, b2), n2 = t3;
            }
          }
          r2 = "", a2 = p2;
        }
      }
    } else r2 += t2[a2];
    return e3.child;
  };
  function qe(t2, e3, n2, r2) {
    this.options.captureMetaData || (r2 = void 0);
    const i2 = this.options.jPath ? n2.toString() : n2, s2 = this.options.updateTag(e3.tagname, i2, e3[":@"]);
    false === s2 || ("string" == typeof s2 ? (e3.tagname = s2, t2.addChild(e3, r2)) : t2.addChild(e3, r2));
  }
  function He(t2, e3, n2) {
    const r2 = this.options.processEntities;
    if (!r2 || !r2.enabled) return t2;
    if (r2.allowedTags) {
      const i2 = this.options.jPath ? n2.toString() : n2;
      if (!(Array.isArray(r2.allowedTags) ? r2.allowedTags.includes(e3) : r2.allowedTags(e3, i2))) return t2;
    }
    if (r2.tagFilter) {
      const i2 = this.options.jPath ? n2.toString() : n2;
      if (!r2.tagFilter(e3, i2)) return t2;
    }
    return this.entityDecoder.decode(t2);
  }
  function Ye(t2, e3, n2, r2) {
    return t2 && (void 0 === r2 && (r2 = 0 === e3.child.length), void 0 !== (t2 = this.parseTextData(t2, e3.tagname, n2, false, !!e3[":@"] && 0 !== Object.keys(e3[":@"]).length, r2)) && "" !== t2 && e3.add(this.options.textNodeName, t2), t2 = ""), t2;
  }
  function Xe() {
    return 0 !== this.stopNodeExpressionsSet.size && this.matcher.matchesAny(this.stopNodeExpressionsSet);
  }
  function Ze(t2, e3, n2, r2) {
    const i2 = t2.indexOf(e3, n2);
    if (-1 === i2) throw new Error(r2);
    return i2 + e3.length - 1;
  }
  function Je(t2, e3, n2, r2) {
    const i2 = t2.indexOf(e3, n2);
    if (-1 === i2) throw new Error(r2);
    return i2;
  }
  function Ke(t2, e3, n2) {
    const r2 = (function(t3, e4) {
      let n3 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : ">", r3 = 0;
      const i3 = t3.length, s3 = n3.charCodeAt(0), o3 = n3.length > 1 ? n3.charCodeAt(1) : -1;
      let a3 = "", h3 = e4;
      for (let n4 = e4; n4 < i3; n4++) {
        const e5 = t3.charCodeAt(n4);
        if (r3) e5 === r3 && (r3 = 0);
        else if (34 === e5 || 39 === e5) r3 = e5;
        else if (e5 === s3) {
          if (-1 === o3) return a3 += t3.substring(h3, n4), { data: a3, index: n4 };
          if (t3.charCodeAt(n4 + 1) === o3) return a3 += t3.substring(h3, n4), { data: a3, index: n4 };
        } else 9 !== e5 || r3 || (a3 += t3.substring(h3, n4) + " ", h3 = n4 + 1);
      }
    })(t2, e3 + 1, arguments.length > 3 && void 0 !== arguments[3] ? arguments[3] : ">");
    if (!r2) return;
    let i2 = r2.data;
    const s2 = r2.index, o2 = i2.search(/\s/);
    let a2 = i2, h2 = true;
    -1 !== o2 && (a2 = i2.substring(0, o2), i2 = i2.substring(o2 + 1).trimStart());
    const l2 = a2;
    if (n2) {
      const t3 = a2.indexOf(":");
      -1 !== t3 && (a2 = a2.substr(t3 + 1), h2 = a2 !== r2.data.substr(t3 + 1));
    }
    return { tagName: a2, tagExp: i2, closeIndex: s2, attrExpPresent: h2, rawTagName: l2 };
  }
  function Qe(t2, e3, n2) {
    const r2 = n2;
    let i2 = 1;
    const s2 = t2.length;
    for (; n2 < s2; n2++) if ("<" === t2[n2]) {
      const s3 = t2.charCodeAt(n2 + 1);
      if (47 === s3) {
        const s4 = Je(t2, ">", n2, `${e3} is not closed`);
        if (t2.substring(n2 + 2, s4).trim() === e3 && (i2--, 0 === i2)) return { tagContent: t2.substring(r2, n2), i: s4 };
        n2 = s4;
      } else if (63 === s3) n2 = Ze(t2, "?>", n2 + 1, "StopNode is not closed.");
      else if (33 === s3 && 45 === t2.charCodeAt(n2 + 2) && 45 === t2.charCodeAt(n2 + 3)) n2 = Ze(t2, "-->", n2 + 3, "StopNode is not closed.");
      else if (33 === s3 && 91 === t2.charCodeAt(n2 + 2)) n2 = Ze(t2, "]]>", n2, "StopNode is not closed.") - 2;
      else {
        const r3 = Ke(t2, n2, ">");
        r3 && ((r3 && r3.tagName) === e3 && "/" !== r3.tagExp[r3.tagExp.length - 1] && i2++, n2 = r3.closeIndex);
      }
    }
  }
  function tn(t2, e3, n2) {
    if (e3 && "string" == typeof t2) {
      const e4 = t2.trim();
      return "true" === e4 || "false" !== e4 && (function(t3) {
        let e5 = arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : {};
        if (e5 = Object.assign({}, we, e5), !t3 || "string" != typeof t3) return t3;
        let n3 = t3.trim();
        if (0 === n3.length) return t3;
        if (void 0 !== e5.skipLike && e5.skipLike.test(n3)) return t3;
        if ("0" === n3) return 0;
        if (e5.hex && be.test(n3)) return (function(t4) {
          if (parseInt) return parseInt(t4, 16);
          if (Number.parseInt) return Number.parseInt(t4, 16);
          if (window && window.parseInt) return window.parseInt(t4, 16);
          throw new Error("parseInt, Number.parseInt, window.parseInt are not supported");
        })(n3);
        if (isFinite(n3)) {
          if (n3.includes("e") || n3.includes("E")) return (function(t4, e6, n4) {
            if (!n4.eNotation) return t4;
            const r3 = e6.match(xe);
            if (r3) {
              let i2 = r3[1] || "";
              const s2 = -1 === r3[3].indexOf("e") ? "E" : "e", o2 = r3[2], a2 = i2 ? t4[o2.length + 1] === s2 : t4[o2.length] === s2;
              return o2.length > 1 && a2 ? t4 : (1 !== o2.length || !r3[3].startsWith(`.${s2}`) && r3[3][0] !== s2) && o2.length > 0 ? n4.leadingZeros && !a2 ? (e6 = (r3[1] || "") + r3[3], Number(e6)) : t4 : Number(e6);
            }
            return t4;
          })(t3, n3, e5);
          {
            const i2 = ve.exec(n3);
            if (i2) {
              const s2 = i2[1] || "", o2 = i2[2];
              let a2 = (r2 = i2[3]) && -1 !== r2.indexOf(".") ? ("." === (r2 = r2.replace(/0+$/, "")) ? r2 = "0" : "." === r2[0] ? r2 = "0" + r2 : "." === r2[r2.length - 1] && (r2 = r2.substring(0, r2.length - 1)), r2) : r2;
              const h2 = s2 ? "." === t3[o2.length + 1] : "." === t3[o2.length];
              if (!e5.leadingZeros && (o2.length > 1 || 1 === o2.length && !h2)) return t3;
              {
                const r3 = Number(n3), i3 = String(r3);
                if (0 === r3) return r3;
                if (-1 !== i3.search(/[eE]/)) return e5.eNotation ? r3 : t3;
                if (-1 !== n3.indexOf(".")) return "0" === i3 || i3 === a2 || i3 === `${s2}${a2}` ? r3 : t3;
                let h3 = o2 ? a2 : n3;
                return o2 ? h3 === i3 || s2 + h3 === i3 ? r3 : t3 : h3 === i3 || h3 === s2 + i3 ? r3 : t3;
              }
            }
            return t3;
          }
        }
        var r2;
        return (function(t4, e6, n4) {
          const r3 = e6 === 1 / 0;
          switch (n4.infinity.toLowerCase()) {
            case "null":
              return null;
            case "infinity":
              return e6;
            case "string":
              return r3 ? "Infinity" : "-Infinity";
            default:
              return t4;
          }
        })(t3, Number(n3), e5);
      })(t2, n2);
    }
    return void 0 !== t2 ? t2 : "";
  }
  function en(t2, e3, n2, r2) {
    if (t2) {
      const r3 = t2(e3);
      n2 === e3 && (n2 = r3), e3 = r3;
    }
    return { tagName: e3 = nn(e3, r2), tagExp: n2 };
  }
  function nn(t2, e3) {
    if (oe.includes(t2)) throw new Error(`[SECURITY] Invalid name: "${t2}" is a reserved JavaScript keyword that could cause prototype pollution`);
    return se.includes(t2) ? e3.onDangerousProperty(t2) : t2;
  }
  var rn = fe.getMetaDataSymbol();
  function sn(t2, e3) {
    if (!t2 || "object" != typeof t2) return {};
    if (!e3) return t2;
    const n2 = {};
    for (const r2 in t2) r2.startsWith(e3) ? n2[r2.substring(e3.length)] = t2[r2] : n2[r2] = t2[r2];
    return n2;
  }
  function on(t2, e3, n2, r2) {
    return an(t2, e3, n2, r2);
  }
  function an(t2, e3, n2, r2) {
    let i2;
    const s2 = {};
    for (let o2 = 0; o2 < t2.length; o2++) {
      const a2 = t2[o2], h2 = hn(a2);
      if (void 0 !== h2 && h2 !== e3.textNodeName) {
        const t3 = sn(a2[":@"] || {}, e3.attributeNamePrefix);
        n2.push(h2, t3);
      }
      if (h2 === e3.textNodeName) void 0 === i2 ? i2 = a2[h2] : i2 += "" + a2[h2];
      else {
        if (void 0 === h2) continue;
        if (a2[h2]) {
          let t3 = an(a2[h2], e3, n2, r2);
          const i3 = un(t3, e3);
          if (a2[":@"] ? ln(t3, a2[":@"], r2, e3) : 1 !== Object.keys(t3).length || void 0 === t3[e3.textNodeName] || e3.alwaysCreateTextNode ? 0 === Object.keys(t3).length && (e3.alwaysCreateTextNode ? t3[e3.textNodeName] = "" : t3 = "") : t3 = t3[e3.textNodeName], void 0 !== a2[rn] && "object" == typeof t3 && null !== t3 && (t3[rn] = a2[rn]), void 0 !== s2[h2] && Object.prototype.hasOwnProperty.call(s2, h2)) Array.isArray(s2[h2]) || (s2[h2] = [s2[h2]]), s2[h2].push(t3);
          else {
            const n3 = e3.jPath ? r2.toString() : r2;
            e3.isArray(h2, n3, i3) ? s2[h2] = [t3] : s2[h2] = t3;
          }
          void 0 !== h2 && h2 !== e3.textNodeName && n2.pop();
        }
      }
    }
    return "string" == typeof i2 ? i2.length > 0 && (s2[e3.textNodeName] = i2) : void 0 !== i2 && (s2[e3.textNodeName] = i2), s2;
  }
  function hn(t2) {
    const e3 = Object.keys(t2);
    for (let t3 = 0; t3 < e3.length; t3++) {
      const n2 = e3[t3];
      if (":@" !== n2) return n2;
    }
  }
  function ln(t2, e3, n2, r2) {
    if (e3) {
      const i2 = Object.keys(e3), s2 = i2.length;
      for (let o2 = 0; o2 < s2; o2++) {
        const s3 = i2[o2], a2 = s3.startsWith(r2.attributeNamePrefix) ? s3.substring(r2.attributeNamePrefix.length) : s3, h2 = r2.jPath ? n2.toString() + "." + a2 : n2;
        r2.isArray(s3, h2, true, true) ? t2[s3] = [e3[s3]] : t2[s3] = e3[s3];
      }
    }
  }
  function un(t2, e3) {
    const { textNodeName: n2 } = e3, r2 = Object.keys(t2).length;
    return 0 === r2 || !(1 !== r2 || !t2[n2] && "boolean" != typeof t2[n2] && 0 !== t2[n2]);
  }
  var cn = { allowBooleanAttributes: false, unpairedTags: [] };
  function pn(t2) {
    return " " === t2 || "	" === t2 || "\n" === t2 || "\r" === t2;
  }
  function fn(t2, e3) {
    const n2 = e3;
    for (; e3 < t2.length; e3++) if ("?" != t2[e3] && " " != t2[e3]) ;
    else {
      const r2 = t2.substr(n2, e3 - n2);
      if (e3 > 5 && "xml" === r2) return vn("InvalidXml", "XML declaration allowed only at the start of the document.", xn(t2, e3));
      if ("?" == t2[e3] && ">" == t2[e3 + 1]) {
        e3++;
        break;
      }
    }
    return e3;
  }
  function dn(t2, e3) {
    if (t2.length > e3 + 5 && "-" === t2[e3 + 1] && "-" === t2[e3 + 2]) {
      for (e3 += 3; e3 < t2.length; e3++) if ("-" === t2[e3] && "-" === t2[e3 + 1] && ">" === t2[e3 + 2]) {
        e3 += 2;
        break;
      }
    } else if (t2.length > e3 + 8 && "D" === t2[e3 + 1] && "O" === t2[e3 + 2] && "C" === t2[e3 + 3] && "T" === t2[e3 + 4] && "Y" === t2[e3 + 5] && "P" === t2[e3 + 6] && "E" === t2[e3 + 7]) {
      let n2 = 1;
      for (e3 += 8; e3 < t2.length; e3++) if ("<" === t2[e3]) n2++;
      else if (">" === t2[e3] && (n2--, 0 === n2)) break;
    } else if (t2.length > e3 + 9 && "[" === t2[e3 + 1] && "C" === t2[e3 + 2] && "D" === t2[e3 + 3] && "A" === t2[e3 + 4] && "T" === t2[e3 + 5] && "A" === t2[e3 + 6] && "[" === t2[e3 + 7]) {
      for (e3 += 8; e3 < t2.length; e3++) if ("]" === t2[e3] && "]" === t2[e3 + 1] && ">" === t2[e3 + 2]) {
        e3 += 2;
        break;
      }
    }
    return e3;
  }
  function gn(t2, e3) {
    let n2 = "", r2 = "", i2 = false;
    for (; e3 < t2.length; e3++) {
      if ('"' === t2[e3] || "'" === t2[e3]) "" === r2 ? r2 = t2[e3] : r2 !== t2[e3] || (r2 = "");
      else if (">" === t2[e3] && "" === r2) {
        i2 = true;
        break;
      }
      n2 += t2[e3];
    }
    return "" === r2 && { value: n2, index: e3, tagClosed: i2 };
  }
  var mn = new RegExp(`(\\s*)([^\\s=]+)(\\s*=)?(\\s*(['"])(([\\s\\S])*?)\\5)?`, "g");
  function yn(t2, e3) {
    const n2 = re(t2, mn), r2 = {};
    for (let t3 = 0; t3 < n2.length; t3++) {
      if (0 === n2[t3][1].length) return vn("InvalidAttr", "Attribute '" + n2[t3][2] + "' has no space in starting.", Nn(n2[t3]));
      if (void 0 !== n2[t3][3] && void 0 === n2[t3][4]) return vn("InvalidAttr", "Attribute '" + n2[t3][2] + "' is without value.", Nn(n2[t3]));
      if (void 0 === n2[t3][3] && !e3.allowBooleanAttributes) return vn("InvalidAttr", "boolean attribute '" + n2[t3][2] + "' is not allowed.", Nn(n2[t3]));
      const i2 = n2[t3][2];
      if (!wn(i2)) return vn("InvalidAttr", "Attribute '" + i2 + "' is an invalid name.", Nn(n2[t3]));
      if (Object.prototype.hasOwnProperty.call(r2, i2)) return vn("InvalidAttr", "Attribute '" + i2 + "' is repeated.", Nn(n2[t3]));
      r2[i2] = 1;
    }
    return true;
  }
  function bn(t2, e3) {
    if (";" === t2[++e3]) return -1;
    if ("#" === t2[e3]) return (function(t3, e4) {
      let n3 = /\d/;
      for ("x" === t3[e4] && (e4++, n3 = /[\da-fA-F]/); e4 < t3.length; e4++) {
        if (";" === t3[e4]) return e4;
        if (!t3[e4].match(n3)) break;
      }
      return -1;
    })(t2, ++e3);
    let n2 = 0;
    for (; e3 < t2.length; e3++, n2++) if (!(t2[e3].match(/\w/) && n2 < 20)) {
      if (";" === t2[e3]) break;
      return -1;
    }
    return e3;
  }
  function vn(t2, e3, n2) {
    return { err: { code: t2, msg: e3, line: n2.line || n2, col: n2.col } };
  }
  function wn(t2) {
    return ie(t2);
  }
  function xn(t2, e3) {
    const n2 = t2.substring(0, e3).split(/\r?\n/);
    return { line: n2.length, col: n2[n2.length - 1].length + 1 };
  }
  function Nn(t2) {
    return t2.startIndex + t2[1].length;
  }
  var En = class {
    constructor(t2) {
      this.externalEntities = {}, this.options = ce(t2);
    }
    parse(t2, e3) {
      if ("string" != typeof t2 && t2.toString) t2 = t2.toString();
      else if ("string" != typeof t2) throw new Error("XML data is accepted in String or Bytes[] form.");
      if (e3) {
        true === e3 && (e3 = {});
        const n3 = (function(t3, e4) {
          e4 = Object.assign({}, cn, e4);
          const n4 = [];
          let r3 = false, i2 = false;
          "\uFEFF" === t3[0] && (t3 = t3.substr(1));
          for (let s2 = 0; s2 < t3.length; s2++) if ("<" === t3[s2] && "?" === t3[s2 + 1]) {
            if (s2 += 2, s2 = fn(t3, s2), s2.err) return s2;
          } else {
            if ("<" !== t3[s2]) {
              if (pn(t3[s2])) continue;
              return vn("InvalidChar", "char '" + t3[s2] + "' is not expected.", xn(t3, s2));
            }
            {
              let o2 = s2;
              if (s2++, "!" === t3[s2]) {
                s2 = dn(t3, s2);
                continue;
              }
              {
                let a2 = false;
                "/" === t3[s2] && (a2 = true, s2++);
                let h2 = "";
                for (; s2 < t3.length && ">" !== t3[s2] && " " !== t3[s2] && "	" !== t3[s2] && "\n" !== t3[s2] && "\r" !== t3[s2]; s2++) h2 += t3[s2];
                if (h2 = h2.trim(), "/" === h2[h2.length - 1] && (h2 = h2.substring(0, h2.length - 1), s2--), !ie(h2)) {
                  let e5;
                  return e5 = 0 === h2.trim().length ? "Invalid space after '<'." : "Tag '" + h2 + "' is an invalid name.", vn("InvalidTag", e5, xn(t3, s2));
                }
                const l2 = gn(t3, s2);
                if (false === l2) return vn("InvalidAttr", "Attributes for '" + h2 + "' have open quote.", xn(t3, s2));
                let u2 = l2.value;
                if (s2 = l2.index, "/" === u2[u2.length - 1]) {
                  const n5 = s2 - u2.length;
                  u2 = u2.substring(0, u2.length - 1);
                  const i3 = yn(u2, e4);
                  if (true !== i3) return vn(i3.err.code, i3.err.msg, xn(t3, n5 + i3.err.line));
                  r3 = true;
                } else if (a2) {
                  if (!l2.tagClosed) return vn("InvalidTag", "Closing tag '" + h2 + "' doesn't have proper closing.", xn(t3, s2));
                  if (u2.trim().length > 0) return vn("InvalidTag", "Closing tag '" + h2 + "' can't have attributes or invalid starting.", xn(t3, o2));
                  if (0 === n4.length) return vn("InvalidTag", "Closing tag '" + h2 + "' has not been opened.", xn(t3, o2));
                  {
                    const e5 = n4.pop();
                    if (h2 !== e5.tagName) {
                      let n5 = xn(t3, e5.tagStartPos);
                      return vn("InvalidTag", "Expected closing tag '" + e5.tagName + "' (opened in line " + n5.line + ", col " + n5.col + ") instead of closing tag '" + h2 + "'.", xn(t3, o2));
                    }
                    0 == n4.length && (i2 = true);
                  }
                } else {
                  const a3 = yn(u2, e4);
                  if (true !== a3) return vn(a3.err.code, a3.err.msg, xn(t3, s2 - u2.length + a3.err.line));
                  if (true === i2) return vn("InvalidXml", "Multiple possible root nodes found.", xn(t3, s2));
                  -1 !== e4.unpairedTags.indexOf(h2) || n4.push({ tagName: h2, tagStartPos: o2 }), r3 = true;
                }
                for (s2++; s2 < t3.length; s2++) if ("<" === t3[s2]) {
                  if ("!" === t3[s2 + 1]) {
                    s2++, s2 = dn(t3, s2);
                    continue;
                  }
                  if ("?" !== t3[s2 + 1]) break;
                  if (s2 = fn(t3, ++s2), s2.err) return s2;
                } else if ("&" === t3[s2]) {
                  const e5 = bn(t3, s2);
                  if (-1 == e5) return vn("InvalidChar", "char '&' is not expected.", xn(t3, s2));
                  s2 = e5;
                } else if (true === i2 && !pn(t3[s2])) return vn("InvalidXml", "Extra text at the end", xn(t3, s2));
                "<" === t3[s2] && s2--;
              }
            }
          }
          return r3 ? 1 == n4.length ? vn("InvalidTag", "Unclosed tag '" + n4[0].tagName + "'.", xn(t3, n4[0].tagStartPos)) : !(n4.length > 0) || vn("InvalidXml", "Invalid '" + JSON.stringify(n4.map(((t4) => t4.tagName)), null, 4).replace(/\r?\n/g, "") + "' found.", { line: 1, col: 1 }) : vn("InvalidXml", "Start tag expected.", 1);
        })(t2, e3);
        if (true !== n3) throw Error(`${n3.err.msg}:${n3.err.line}:${n3.err.col}`);
      }
      const n2 = new Fe(this.options, this.externalEntities), r2 = n2.parseXml(t2);
      return this.options.preserveOrder || void 0 === r2 ? r2 : on(r2, this.options, n2.matcher, n2.readonlyMatcher);
    }
    addEntity(t2, e3) {
      if (-1 !== e3.indexOf("&")) throw new Error("Entity value can't have '&'");
      if (-1 !== t2.indexOf("&") || -1 !== t2.indexOf(";")) throw new Error("An entity must be set without '&' and ';'. Eg. use '#xD' for '&#xD;'");
      if ("&" === e3) throw new Error("An entity with value '&' is not permitted");
      this.externalEntities[t2] = e3;
    }
    static getMetaDataSymbol() {
      return fe.getMetaDataSymbol();
    }
  };
  var An = n(829);
  var Sn = n.n(An);
  var Pn = (function(t2) {
    return t2.Array = "array", t2.Object = "object", t2.Original = "original", t2;
  })(Pn || {});
  function Tn(t2) {
    return "string" == typeof t2 ? t2 : t2.toString(".", false);
  }
  function On(t2, e3) {
    if (!t2.endsWith("propstat.prop.displayname")) return e3;
  }
  function Cn(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : Pn.Original;
    const r2 = Sn().get(t2, e3);
    return "array" === n2 && false === Array.isArray(r2) ? [r2] : "object" === n2 && Array.isArray(r2) ? r2[0] : r2;
  }
  function _n2(t2, e3) {
    return e3 = e3 ?? { attributeNamePrefix: "@", attributeParsers: [], tagParsers: [On] }, new Promise(((n2) => {
      n2((function(t3) {
        const { multistatus: e4 } = t3;
        if ("" === e4) return { multistatus: { response: [] } };
        if (!e4) throw new Error("Invalid response: No root multistatus found");
        const n3 = { multistatus: Array.isArray(e4) ? e4[0] : e4 };
        return Sn().set(n3, "multistatus.response", Cn(n3, "multistatus.response", Pn.Array)), Sn().set(n3, "multistatus.response", Sn().get(n3, "multistatus.response").map(((t4) => (function(t5) {
          const e5 = Object.assign({}, t5);
          return e5.status ? Sn().set(e5, "status", Cn(e5, "status", Pn.Object)) : (Sn().set(e5, "propstat", Cn(e5, "propstat", Pn.Object)), Sn().set(e5, "propstat.prop", Cn(e5, "propstat.prop", Pn.Object))), e5;
        })(t4)))), n3;
      })((function(t3) {
        let { attributeNamePrefix: e4, attributeParsers: n3, entityDecoder: r2, tagParsers: i2 } = t3;
        const s2 = { allowBooleanAttributes: true, attributeNamePrefix: e4, textNodeName: "text", ignoreAttributes: false, removeNSPrefix: true, jPath: false, numberParseOptions: { hex: true, leadingZeros: false }, attributeValueProcessor(t4, e5, r3) {
          const i3 = Tn(r3);
          for (const t5 of n3) try {
            const n4 = t5(i3, e5);
            if (n4 !== e5) return n4;
          } catch (t6) {
          }
          return e5;
        }, tagValueProcessor(t4, e5, n4) {
          const r3 = Tn(n4);
          for (const t5 of i2) try {
            const n5 = t5(r3, e5);
            if (n5 !== e5) return n5;
          } catch (t6) {
          }
          return e5;
        } };
        return r2 && (s2.entityDecoder = new Le({ limit: { maxTotalExpansions: r2.limit?.maxTotalExpansions ?? 0, maxExpandedLength: r2.limit?.maxExpandedLength ?? 0 } })), new En(s2);
      })(e3).parse(t2)));
    }));
  }
  function $n(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] && arguments[2];
    const { getlastmodified: r2 = null, getcontentlength: i2 = "0", resourcetype: s2 = null, getcontenttype: o2 = null, getetag: a2 = null } = t2, h2 = s2 && "object" == typeof s2 && void 0 !== s2.collection ? "directory" : "file", u2 = { filename: e3, basename: l().basename(e3), lastmod: r2, size: parseInt(i2, 10), type: h2, etag: "string" == typeof a2 ? a2.replace(/"/g, "") : null };
    return "file" === h2 && (u2.mime = o2 && "string" == typeof o2 ? o2.split(";")[0] : ""), n2 && (void 0 !== t2.displayname && (t2.displayname = String(t2.displayname)), u2.props = t2), u2;
  }
  function jn(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] && arguments[2], r2 = null;
    try {
      t2.multistatus.response[0].propstat && (r2 = t2.multistatus.response[0]);
    } catch (t3) {
    }
    if (!r2) throw new Error("Failed getting item stat: bad response");
    const { propstat: { prop: i2, status: s2 } } = r2, [o2, a2, h2] = s2.split(" ", 3), l2 = parseInt(a2, 10);
    if (l2 >= 400) {
      const t3 = new Error(`Invalid response: ${l2} ${h2}`);
      throw t3.status = l2, t3;
    }
    return $n(i2, d(e3), n2);
  }
  function Mn(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  var Rn = /* @__PURE__ */ (function(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  })((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const { details: r2 = false } = n2, i2 = K({ url: m(t2.remoteURL, p(e3)), method: "PROPFIND", headers: { Accept: "text/plain,application/xml", Depth: "0" } }, t2, n2);
    return Mn(J(i2, t2), (function(n3) {
      return Jt(t2, n3), Mn(n3.text(), (function(i3) {
        return Mn(_n2(i3, t2.parsing), (function(t3) {
          const i4 = jn(t3, e3, r2);
          return Kt(n3, i4, r2);
        }));
      }));
    }));
  }));
  function kn(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  var Ln = Dn((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const r2 = (function(t3) {
      if (!t3 || "/" === t3) return [];
      let e4 = t3;
      const n3 = [];
      do {
        n3.push(e4), e4 = l().dirname(e4);
      } while (e4 && "/" !== e4);
      return n3;
    })(d(e3));
    r2.sort(((t3, e4) => t3.length > e4.length ? 1 : e4.length > t3.length ? -1 : 0));
    let i2 = false;
    return (function(t3, e4, n3) {
      if ("function" == typeof t3[Vn]) {
        let u2 = function(t4) {
          try {
            for (; !(r3 = o2.next()).done; ) if ((t4 = e4(r3.value)) && t4.then) {
              if (!Gn(t4)) return void t4.then(u2, s2 || (s2 = Wn.bind(null, i3 = new Bn(), 2)));
              t4 = t4.v;
            }
            i3 ? Wn(i3, 1, t4) : i3 = t4;
          } catch (t5) {
            Wn(i3 || (i3 = new Bn()), 2, t5);
          }
        };
        var r3, i3, s2, o2 = t3[Vn]();
        if (u2(), o2.return) {
          var a2 = function(t4) {
            try {
              r3.done || o2.return();
            } catch (t5) {
            }
            return t4;
          };
          if (i3 && i3.then) return i3.then(a2, (function(t4) {
            throw a2(t4);
          }));
          a2();
        }
        return i3;
      }
      if (!("length" in t3)) throw new TypeError("Object is not iterable");
      for (var h2 = [], l2 = 0; l2 < t3.length; l2++) h2.push(t3[l2]);
      return (function(t4, e5, n4) {
        var r4, i4, s3 = -1;
        return (function o3(a3) {
          try {
            for (; ++s3 < t4.length && (!n4 || !n4()); ) if ((a3 = e5(s3)) && a3.then) {
              if (!Gn(a3)) return void a3.then(o3, i4 || (i4 = Wn.bind(null, r4 = new Bn(), 2)));
              a3 = a3.v;
            }
            r4 ? Wn(r4, 1, a3) : r4 = a3;
          } catch (t5) {
            Wn(r4 || (r4 = new Bn()), 2, t5);
          }
        })(), r4;
      })(h2, (function(t4) {
        return e4(h2[t4]);
      }), n3);
    })(r2, (function(r3) {
      return s2 = function() {
        return (function(n3, i3) {
          try {
            var s3 = kn(Rn(t2, r3), (function(t3) {
              if ("directory" !== t3.type) throw new Error(`Path includes a file: ${e3}`);
            }));
          } catch (t3) {
            return i3(t3);
          }
          return s3 && s3.then ? s3.then(void 0, i3) : s3;
        })(0, (function(e4) {
          const s3 = e4;
          return (function() {
            if (404 === s3.status) return i2 = true, Fn(zn(t2, r3, { ...n2, recursive: false }));
            throw e4;
          })();
        }));
      }, (o2 = (function() {
        if (i2) return Fn(zn(t2, r3, { ...n2, recursive: false }));
      })()) && o2.then ? o2.then(s2) : s2();
      var s2, o2;
    }), (function() {
      return false;
    }));
  }));
  function Dn(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  }
  function Un() {
  }
  function Fn(t2, e3) {
    if (!e3) return t2 && t2.then ? t2.then(Un) : Promise.resolve();
  }
  var Vn = "undefined" != typeof Symbol ? Symbol.iterator || (Symbol.iterator = Symbol("Symbol.iterator")) : "@@iterator";
  function Wn(t2, e3, n2) {
    if (!t2.s) {
      if (n2 instanceof Bn) {
        if (!n2.s) return void (n2.o = Wn.bind(null, t2, e3));
        1 & e3 && (e3 = n2.s), n2 = n2.v;
      }
      if (n2 && n2.then) return void n2.then(Wn.bind(null, t2, e3), Wn.bind(null, t2, 2));
      t2.s = e3, t2.v = n2;
      const r2 = t2.o;
      r2 && r2(t2);
    }
  }
  var Bn = (function() {
    function t2() {
    }
    return t2.prototype.then = function(e3, n2) {
      const r2 = new t2(), i2 = this.s;
      if (i2) {
        const t3 = 1 & i2 ? e3 : n2;
        if (t3) {
          try {
            Wn(r2, 1, t3(this.v));
          } catch (t4) {
            Wn(r2, 2, t4);
          }
          return r2;
        }
        return this;
      }
      return this.o = function(t3) {
        try {
          const i3 = t3.v;
          1 & t3.s ? Wn(r2, 1, e3 ? e3(i3) : i3) : n2 ? Wn(r2, 1, n2(i3)) : Wn(r2, 2, i3);
        } catch (t4) {
          Wn(r2, 2, t4);
        }
      }, r2;
    }, t2;
  })();
  function Gn(t2) {
    return t2 instanceof Bn && 1 & t2.s;
  }
  var zn = Dn((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    if (true === n2.recursive) return Ln(t2, e3, n2);
    const r2 = K({ url: m(t2.remoteURL, (i2 = p(e3), i2.endsWith("/") ? i2 : i2 + "/")), method: "MKCOL" }, t2, n2);
    var i2;
    return kn(J(r2, t2), (function(e4) {
      Jt(t2, e4);
    }));
  }));
  var qn = n(388);
  var Hn = n.n(qn);
  function er(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  }
  var nr = er((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const r2 = K({ url: m(t2.remoteURL, p(e3)), method: "GET", headers: { Accept: "text/plain" }, transformResponse: [or] }, t2, n2);
    return rr(J(r2, t2), (function(e4) {
      return Jt(t2, e4), rr(e4.text(), (function(t3) {
        return Kt(e4, t3, n2.details);
      }));
    }));
  }));
  function rr(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  var ir = er((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const r2 = K({ url: m(t2.remoteURL, p(e3)), method: "GET" }, t2, n2);
    return rr(J(r2, t2), (function(e4) {
      let r3;
      return Jt(t2, e4), (function(t3, e5) {
        var n3 = t3();
        return n3 && n3.then ? n3.then(e5) : e5();
      })((function() {
        return rr(e4.arrayBuffer(), (function(t3) {
          r3 = t3;
        }));
      }), (function() {
        return Kt(e4, r3, n2.details);
      }));
    }));
  }));
  var sr = er((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const { format: r2 = "binary" } = n2;
    if ("binary" !== r2 && "text" !== r2) throw new a({ info: { code: _.InvalidOutputFormat } }, `Invalid output format: ${r2}`);
    return "text" === r2 ? nr(t2, e3, n2) : ir(t2, e3, n2);
  }));
  var or = (t2) => t2;
  function ar(t2, e3) {
    let n2 = "";
    e3.format && e3.indentBy.length > 0 && (n2 = "\n");
    const r2 = [];
    if (e3.stopNodes && Array.isArray(e3.stopNodes)) for (let t3 = 0; t3 < e3.stopNodes.length; t3++) {
      const n3 = e3.stopNodes[t3];
      "string" == typeof n3 ? r2.push(new Ae(n3)) : n3 instanceof Ae && r2.push(n3);
    }
    return hr(t2, e3, n2, new Ee(), r2);
  }
  function hr(t2, e3, n2, r2, i2) {
    let s2 = "", o2 = false;
    if (e3.maxNestedTags && r2.getDepth() > e3.maxNestedTags) throw new Error("Maximum nested tags exceeded");
    if (!Array.isArray(t2)) {
      if (null != t2) {
        let n3 = t2.toString();
        return n3 = gr(n3, e3), n3;
      }
      return "";
    }
    for (let a2 = 0; a2 < t2.length; a2++) {
      const h2 = t2[a2], l2 = pr(h2);
      if (void 0 === l2) continue;
      const u2 = lr(h2[":@"], e3);
      r2.push(l2, u2);
      const c2 = dr(r2, i2);
      if (l2 === e3.textNodeName) {
        let t3 = h2[l2];
        c2 || (t3 = e3.tagValueProcessor(l2, t3), t3 = gr(t3, e3)), o2 && (s2 += n2), s2 += t3, o2 = false, r2.pop();
        continue;
      }
      if (l2 === e3.cdataPropName) {
        o2 && (s2 += n2);
        const t3 = h2[l2][0][e3.textNodeName];
        s2 += `<![CDATA[${String(t3).replace(/\]\]>/g, "]]]]><![CDATA[>")}]]>`, o2 = false, r2.pop();
        continue;
      }
      if (l2 === e3.commentPropName) {
        const t3 = h2[l2][0][e3.textNodeName];
        s2 += n2 + `<!--${String(t3).replace(/--/g, "- -").replace(/-$/, "- ")}-->`, o2 = true, r2.pop();
        continue;
      }
      if ("?" === l2[0]) {
        const t3 = fr(h2[":@"], e3, c2), i3 = "?xml" === l2 ? "" : n2;
        let a3 = h2[l2][0][e3.textNodeName];
        a3 = 0 !== a3.length ? " " + a3 : "", s2 += i3 + `<${l2}${a3}${t3}?>`, o2 = true, r2.pop();
        continue;
      }
      let p2 = n2;
      "" !== p2 && (p2 += e3.indentBy);
      const f = n2 + `<${l2}${fr(h2[":@"], e3, c2)}`;
      let d2;
      d2 = c2 ? ur(h2[l2], e3) : hr(h2[l2], e3, p2, r2, i2), -1 !== e3.unpairedTags.indexOf(l2) ? e3.suppressUnpairedNode ? s2 += f + ">" : s2 += f + "/>" : d2 && 0 !== d2.length || !e3.suppressEmptyNode ? d2 && d2.endsWith(">") ? s2 += f + `>${d2}${n2}</${l2}>` : (s2 += f + ">", d2 && "" !== n2 && (d2.includes("/>") || d2.includes("</")) ? s2 += n2 + e3.indentBy + d2 + n2 : s2 += d2, s2 += `</${l2}>`) : s2 += f + "/>", o2 = true, r2.pop();
    }
    return s2;
  }
  function lr(t2, e3) {
    if (!t2 || e3.ignoreAttributes) return null;
    const n2 = {};
    let r2 = false;
    for (let i2 in t2) Object.prototype.hasOwnProperty.call(t2, i2) && (n2[i2.startsWith(e3.attributeNamePrefix) ? i2.substr(e3.attributeNamePrefix.length) : i2] = t2[i2], r2 = true);
    return r2 ? n2 : null;
  }
  function ur(t2, e3) {
    if (!Array.isArray(t2)) return null != t2 ? t2.toString() : "";
    let n2 = "";
    for (let r2 = 0; r2 < t2.length; r2++) {
      const i2 = t2[r2], s2 = pr(i2);
      if (s2 === e3.textNodeName) n2 += i2[s2];
      else if (s2 === e3.cdataPropName) n2 += i2[s2][0][e3.textNodeName];
      else if (s2 === e3.commentPropName) n2 += i2[s2][0][e3.textNodeName];
      else {
        if (s2 && "?" === s2[0]) continue;
        if (s2) {
          const t3 = cr(i2[":@"], e3), r3 = ur(i2[s2], e3);
          r3 && 0 !== r3.length ? n2 += `<${s2}${t3}>${r3}</${s2}>` : n2 += `<${s2}${t3}/>`;
        }
      }
    }
    return n2;
  }
  function cr(t2, e3) {
    let n2 = "";
    if (t2 && !e3.ignoreAttributes) for (let r2 in t2) {
      if (!Object.prototype.hasOwnProperty.call(t2, r2)) continue;
      let i2 = t2[r2];
      true === i2 && e3.suppressBooleanAttributes ? n2 += ` ${r2.substr(e3.attributeNamePrefix.length)}` : n2 += ` ${r2.substr(e3.attributeNamePrefix.length)}="${i2}"`;
    }
    return n2;
  }
  function pr(t2) {
    const e3 = Object.keys(t2);
    for (let n2 = 0; n2 < e3.length; n2++) {
      const r2 = e3[n2];
      if (Object.prototype.hasOwnProperty.call(t2, r2) && ":@" !== r2) return r2;
    }
  }
  function fr(t2, e3, n2) {
    let r2 = "";
    if (t2 && !e3.ignoreAttributes) for (let i2 in t2) {
      if (!Object.prototype.hasOwnProperty.call(t2, i2)) continue;
      let s2;
      n2 ? s2 = t2[i2] : (s2 = e3.attributeValueProcessor(i2, t2[i2]), s2 = gr(s2, e3)), true === s2 && e3.suppressBooleanAttributes ? r2 += ` ${i2.substr(e3.attributeNamePrefix.length)}` : r2 += ` ${i2.substr(e3.attributeNamePrefix.length)}="${s2}"`;
    }
    return r2;
  }
  function dr(t2, e3) {
    if (!e3 || 0 === e3.length) return false;
    for (let n2 = 0; n2 < e3.length; n2++) if (t2.matches(e3[n2])) return true;
    return false;
  }
  function gr(t2, e3) {
    if (t2 && t2.length > 0 && e3.processEntities) for (let n2 = 0; n2 < e3.entities.length; n2++) {
      const r2 = e3.entities[n2];
      t2 = t2.replace(r2.regex, r2.val);
    }
    return t2;
  }
  var mr = { attributeNamePrefix: "@_", attributesGroupName: false, textNodeName: "#text", ignoreAttributes: true, cdataPropName: false, format: false, indentBy: "  ", suppressEmptyNode: false, suppressUnpairedNode: true, suppressBooleanAttributes: true, tagValueProcessor: function(t2, e3) {
    return e3;
  }, attributeValueProcessor: function(t2, e3) {
    return e3;
  }, preserveOrder: false, commentPropName: false, unpairedTags: [], entities: [{ regex: new RegExp("&", "g"), val: "&amp;" }, { regex: new RegExp(">", "g"), val: "&gt;" }, { regex: new RegExp("<", "g"), val: "&lt;" }, { regex: new RegExp("'", "g"), val: "&apos;" }, { regex: new RegExp('"', "g"), val: "&quot;" }], processEntities: true, stopNodes: [], oneListGroup: false, maxNestedTags: 100, jPath: true };
  function yr(t2) {
    if (this.options = Object.assign({}, mr, t2), this.options.stopNodes && Array.isArray(this.options.stopNodes) && (this.options.stopNodes = this.options.stopNodes.map(((t3) => "string" == typeof t3 && t3.startsWith("*.") ? ".." + t3.substring(2) : t3))), this.stopNodeExpressions = [], this.options.stopNodes && Array.isArray(this.options.stopNodes)) for (let t3 = 0; t3 < this.options.stopNodes.length; t3++) {
      const e4 = this.options.stopNodes[t3];
      "string" == typeof e4 ? this.stopNodeExpressions.push(new Ae(e4)) : e4 instanceof Ae && this.stopNodeExpressions.push(e4);
    }
    var e3;
    true === this.options.ignoreAttributes || this.options.attributesGroupName ? this.isAttribute = function() {
      return false;
    } : (this.ignoreAttributesFn = "function" == typeof (e3 = this.options.ignoreAttributes) ? e3 : Array.isArray(e3) ? (t3) => {
      for (const n2 of e3) {
        if ("string" == typeof n2 && t3 === n2) return true;
        if (n2 instanceof RegExp && n2.test(t3)) return true;
      }
    } : () => false, this.attrPrefixLen = this.options.attributeNamePrefix.length, this.isAttribute = wr), this.processTextOrObjNode = br, this.options.format ? (this.indentate = vr, this.tagEndChar = ">\n", this.newLine = "\n") : (this.indentate = function() {
      return "";
    }, this.tagEndChar = ">", this.newLine = "");
  }
  function br(t2, e3, n2, r2) {
    const i2 = this.extractAttributes(t2);
    if (r2.push(e3, i2), this.checkStopNode(r2)) {
      const i3 = this.buildRawContent(t2), s3 = this.buildAttributesForStopNode(t2);
      return r2.pop(), this.buildObjectNode(i3, e3, s3, n2);
    }
    const s2 = this.j2x(t2, n2 + 1, r2);
    return r2.pop(), void 0 !== t2[this.options.textNodeName] && 1 === Object.keys(t2).length ? this.buildTextValNode(t2[this.options.textNodeName], e3, s2.attrStr, n2, r2) : this.buildObjectNode(s2.val, e3, s2.attrStr, n2);
  }
  function vr(t2) {
    return this.options.indentBy.repeat(t2);
  }
  function wr(t2) {
    return !(!t2.startsWith(this.options.attributeNamePrefix) || t2 === this.options.textNodeName) && t2.substr(this.attrPrefixLen);
  }
  yr.prototype.build = function(t2) {
    if (this.options.preserveOrder) return ar(t2, this.options);
    {
      Array.isArray(t2) && this.options.arrayNodeName && this.options.arrayNodeName.length > 1 && (t2 = { [this.options.arrayNodeName]: t2 });
      const e3 = new Ee();
      return this.j2x(t2, 0, e3).val;
    }
  }, yr.prototype.j2x = function(t2, e3, n2) {
    let r2 = "", i2 = "";
    if (this.options.maxNestedTags && n2.getDepth() >= this.options.maxNestedTags) throw new Error("Maximum nested tags exceeded");
    const s2 = this.options.jPath ? n2.toString() : n2, o2 = this.checkStopNode(n2);
    for (let a2 in t2) if (Object.prototype.hasOwnProperty.call(t2, a2)) if (void 0 === t2[a2]) this.isAttribute(a2) && (i2 += "");
    else if (null === t2[a2]) this.isAttribute(a2) || a2 === this.options.cdataPropName ? i2 += "" : "?" === a2[0] ? i2 += this.indentate(e3) + "<" + a2 + "?" + this.tagEndChar : i2 += this.indentate(e3) + "<" + a2 + "/" + this.tagEndChar;
    else if (t2[a2] instanceof Date) i2 += this.buildTextValNode(t2[a2], a2, "", e3, n2);
    else if ("object" != typeof t2[a2]) {
      const h2 = this.isAttribute(a2);
      if (h2 && !this.ignoreAttributesFn(h2, s2)) r2 += this.buildAttrPairStr(h2, "" + t2[a2], o2);
      else if (!h2) if (a2 === this.options.textNodeName) {
        let e4 = this.options.tagValueProcessor(a2, "" + t2[a2]);
        i2 += this.replaceEntitiesValue(e4);
      } else {
        n2.push(a2);
        const r3 = this.checkStopNode(n2);
        if (n2.pop(), r3) {
          const n3 = "" + t2[a2];
          i2 += "" === n3 ? this.indentate(e3) + "<" + a2 + this.closeTag(a2) + this.tagEndChar : this.indentate(e3) + "<" + a2 + ">" + n3 + "</" + a2 + this.tagEndChar;
        } else i2 += this.buildTextValNode(t2[a2], a2, "", e3, n2);
      }
    } else if (Array.isArray(t2[a2])) {
      const r3 = t2[a2].length;
      let s3 = "", o3 = "";
      for (let h2 = 0; h2 < r3; h2++) {
        const r4 = t2[a2][h2];
        if (void 0 === r4) ;
        else if (null === r4) "?" === a2[0] ? i2 += this.indentate(e3) + "<" + a2 + "?" + this.tagEndChar : i2 += this.indentate(e3) + "<" + a2 + "/" + this.tagEndChar;
        else if ("object" == typeof r4) if (this.options.oneListGroup) {
          n2.push(a2);
          const t3 = this.j2x(r4, e3 + 1, n2);
          n2.pop(), s3 += t3.val, this.options.attributesGroupName && r4.hasOwnProperty(this.options.attributesGroupName) && (o3 += t3.attrStr);
        } else s3 += this.processTextOrObjNode(r4, a2, e3, n2);
        else if (this.options.oneListGroup) {
          let t3 = this.options.tagValueProcessor(a2, r4);
          t3 = this.replaceEntitiesValue(t3), s3 += t3;
        } else {
          n2.push(a2);
          const t3 = this.checkStopNode(n2);
          if (n2.pop(), t3) {
            const t4 = "" + r4;
            s3 += "" === t4 ? this.indentate(e3) + "<" + a2 + this.closeTag(a2) + this.tagEndChar : this.indentate(e3) + "<" + a2 + ">" + t4 + "</" + a2 + this.tagEndChar;
          } else s3 += this.buildTextValNode(r4, a2, "", e3, n2);
        }
      }
      this.options.oneListGroup && (s3 = this.buildObjectNode(s3, a2, o3, e3)), i2 += s3;
    } else if (this.options.attributesGroupName && a2 === this.options.attributesGroupName) {
      const e4 = Object.keys(t2[a2]), n3 = e4.length;
      for (let i3 = 0; i3 < n3; i3++) r2 += this.buildAttrPairStr(e4[i3], "" + t2[a2][e4[i3]], o2);
    } else i2 += this.processTextOrObjNode(t2[a2], a2, e3, n2);
    return { attrStr: r2, val: i2 };
  }, yr.prototype.buildAttrPairStr = function(t2, e3, n2) {
    return n2 || (e3 = this.options.attributeValueProcessor(t2, "" + e3), e3 = this.replaceEntitiesValue(e3)), this.options.suppressBooleanAttributes && "true" === e3 ? " " + t2 : " " + t2 + '="' + e3 + '"';
  }, yr.prototype.extractAttributes = function(t2) {
    if (!t2 || "object" != typeof t2) return null;
    const e3 = {};
    let n2 = false;
    if (this.options.attributesGroupName && t2[this.options.attributesGroupName]) {
      const r2 = t2[this.options.attributesGroupName];
      for (let t3 in r2) Object.prototype.hasOwnProperty.call(r2, t3) && (e3[t3.startsWith(this.options.attributeNamePrefix) ? t3.substring(this.options.attributeNamePrefix.length) : t3] = r2[t3], n2 = true);
    } else for (let r2 in t2) {
      if (!Object.prototype.hasOwnProperty.call(t2, r2)) continue;
      const i2 = this.isAttribute(r2);
      i2 && (e3[i2] = t2[r2], n2 = true);
    }
    return n2 ? e3 : null;
  }, yr.prototype.buildRawContent = function(t2) {
    if ("string" == typeof t2) return t2;
    if ("object" != typeof t2 || null === t2) return String(t2);
    if (void 0 !== t2[this.options.textNodeName]) return t2[this.options.textNodeName];
    let e3 = "";
    for (let n2 in t2) {
      if (!Object.prototype.hasOwnProperty.call(t2, n2)) continue;
      if (this.isAttribute(n2)) continue;
      if (this.options.attributesGroupName && n2 === this.options.attributesGroupName) continue;
      const r2 = t2[n2];
      if (n2 === this.options.textNodeName) e3 += r2;
      else if (Array.isArray(r2)) {
        for (let t3 of r2) if ("string" == typeof t3 || "number" == typeof t3) e3 += `<${n2}>${t3}</${n2}>`;
        else if ("object" == typeof t3 && null !== t3) {
          const r3 = this.buildRawContent(t3), i2 = this.buildAttributesForStopNode(t3);
          e3 += "" === r3 ? `<${n2}${i2}/>` : `<${n2}${i2}>${r3}</${n2}>`;
        }
      } else if ("object" == typeof r2 && null !== r2) {
        const t3 = this.buildRawContent(r2), i2 = this.buildAttributesForStopNode(r2);
        e3 += "" === t3 ? `<${n2}${i2}/>` : `<${n2}${i2}>${t3}</${n2}>`;
      } else e3 += `<${n2}>${r2}</${n2}>`;
    }
    return e3;
  }, yr.prototype.buildAttributesForStopNode = function(t2) {
    if (!t2 || "object" != typeof t2) return "";
    let e3 = "";
    if (this.options.attributesGroupName && t2[this.options.attributesGroupName]) {
      const n2 = t2[this.options.attributesGroupName];
      for (let t3 in n2) {
        if (!Object.prototype.hasOwnProperty.call(n2, t3)) continue;
        const r2 = t3.startsWith(this.options.attributeNamePrefix) ? t3.substring(this.options.attributeNamePrefix.length) : t3, i2 = n2[t3];
        true === i2 && this.options.suppressBooleanAttributes ? e3 += " " + r2 : e3 += " " + r2 + '="' + i2 + '"';
      }
    } else for (let n2 in t2) {
      if (!Object.prototype.hasOwnProperty.call(t2, n2)) continue;
      const r2 = this.isAttribute(n2);
      if (r2) {
        const i2 = t2[n2];
        true === i2 && this.options.suppressBooleanAttributes ? e3 += " " + r2 : e3 += " " + r2 + '="' + i2 + '"';
      }
    }
    return e3;
  }, yr.prototype.buildObjectNode = function(t2, e3, n2, r2) {
    if ("" === t2) return "?" === e3[0] ? this.indentate(r2) + "<" + e3 + n2 + "?" + this.tagEndChar : this.indentate(r2) + "<" + e3 + n2 + this.closeTag(e3) + this.tagEndChar;
    {
      let i2 = "</" + e3 + this.tagEndChar, s2 = "";
      return "?" === e3[0] && (s2 = "?", i2 = ""), !n2 && "" !== n2 || -1 !== t2.indexOf("<") ? false !== this.options.commentPropName && e3 === this.options.commentPropName && 0 === s2.length ? this.indentate(r2) + `<!--${t2}-->` + this.newLine : this.indentate(r2) + "<" + e3 + n2 + s2 + this.tagEndChar + t2 + this.indentate(r2) + i2 : this.indentate(r2) + "<" + e3 + n2 + s2 + ">" + t2 + i2;
    }
  }, yr.prototype.closeTag = function(t2) {
    let e3 = "";
    return -1 !== this.options.unpairedTags.indexOf(t2) ? this.options.suppressUnpairedNode || (e3 = "/") : e3 = this.options.suppressEmptyNode ? "/" : `></${t2}`, e3;
  }, yr.prototype.checkStopNode = function(t2) {
    if (!this.stopNodeExpressions || 0 === this.stopNodeExpressions.length) return false;
    for (let e3 = 0; e3 < this.stopNodeExpressions.length; e3++) if (t2.matches(this.stopNodeExpressions[e3])) return true;
    return false;
  }, yr.prototype.buildTextValNode = function(t2, e3, n2, r2, i2) {
    if (false !== this.options.cdataPropName && e3 === this.options.cdataPropName) {
      const e4 = String(t2).replace(/\]\]>/g, "]]]]><![CDATA[>");
      return this.indentate(r2) + `<![CDATA[${e4}]]>` + this.newLine;
    }
    if (false !== this.options.commentPropName && e3 === this.options.commentPropName) {
      const e4 = String(t2).replace(/--/g, "- -").replace(/-$/, "- ");
      return this.indentate(r2) + `<!--${e4}-->` + this.newLine;
    }
    if ("?" === e3[0]) return this.indentate(r2) + "<" + e3 + n2 + "?" + this.tagEndChar;
    {
      let i3 = this.options.tagValueProcessor(e3, t2);
      return i3 = this.replaceEntitiesValue(i3), "" === i3 ? this.indentate(r2) + "<" + e3 + n2 + this.closeTag(e3) + this.tagEndChar : this.indentate(r2) + "<" + e3 + n2 + ">" + i3 + "</" + e3 + this.tagEndChar;
    }
  }, yr.prototype.replaceEntitiesValue = function(t2) {
    if (t2 && t2.length > 0 && this.options.processEntities) for (let e3 = 0; e3 < this.options.entities.length; e3++) {
      const n2 = this.options.entities[e3];
      t2 = t2.replace(n2.regex, n2.val);
    }
    return t2;
  };
  var xr = yr;
  function Nr(t2) {
    return new xr({ attributeNamePrefix: "@_", format: true, ignoreAttributes: false, suppressEmptyNode: true }).build(Er({ lockinfo: { "@_xmlns:d": "DAV:", lockscope: { exclusive: {} }, locktype: { write: {} }, owner: { href: t2 } } }, "d"));
  }
  function Er(t2, e3) {
    const n2 = { ...t2 };
    for (const t3 in n2) n2.hasOwnProperty(t3) && (n2[t3] && "object" == typeof n2[t3] && -1 === t3.indexOf(":") ? (n2[`${e3}:${t3}`] = Er(n2[t3], e3), delete n2[t3]) : false === /^@_/.test(t3) && (n2[`${e3}:${t3}`] = n2[t3], delete n2[t3]));
    return n2;
  }
  function Ar(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  function Sr(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  }
  var Pr = Sr((function(t2, e3, n2) {
    let r2 = arguments.length > 3 && void 0 !== arguments[3] ? arguments[3] : {};
    const i2 = K({ url: m(t2.remoteURL, p(e3)), method: "UNLOCK", headers: { "Lock-Token": n2 } }, t2, r2);
    return Ar(J(i2, t2), (function(e4) {
      if (Jt(t2, e4), 204 !== e4.status && 200 !== e4.status) throw Zt(e4);
    }));
  }));
  var Tr = Sr((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const { refreshToken: r2, timeout: i2 = Or } = n2, s2 = { Accept: "text/plain,application/xml", Timeout: i2 };
    r2 && (s2.If = r2);
    const o2 = K({ url: m(t2.remoteURL, p(e3)), method: "LOCK", headers: s2, data: Nr(t2.contactHref) }, t2, n2);
    return Ar(J(o2, t2), (function(e4) {
      return Jt(t2, e4), Ar(e4.text(), (function(t3) {
        const n3 = (s3 = t3, new En({ removeNSPrefix: true, parseAttributeValue: true, parseTagValue: true }).parse(s3)), r3 = Sn().get(n3, "prop.lockdiscovery.activelock.locktoken.href"), i3 = Sn().get(n3, "prop.lockdiscovery.activelock.timeout");
        var s3;
        if (!r3) throw Zt(e4, "No lock token received: ");
        return { token: r3, serverTimeout: i3 };
      }));
    }));
  }));
  var Or = "Infinite, Second-4100000000";
  var Mr = n(172);
  var Lr = /* @__PURE__ */ (function(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  })((function(t2, e3) {
    let n2 = arguments.length > 2 && void 0 !== arguments[2] ? arguments[2] : {};
    const r2 = K({ url: m(t2.remoteURL, p(e3)), method: "OPTIONS" }, t2, n2);
    return s2 = function(e4) {
      try {
        Jt(t2, e4);
      } catch (t3) {
        throw t3;
      }
      return { compliance: (e4.headers.get("DAV") ?? "").split(",").map(((t3) => t3.trim())), server: e4.headers.get("Server") ?? "" };
    }, (i2 = J(r2, t2)) && i2.then || (i2 = Promise.resolve(i2)), s2 ? i2.then(s2) : i2;
    var i2, s2;
  }));
  function Dr(t2, e3, n2) {
    return n2 ? e3 ? e3(t2) : t2 : (t2 && t2.then || (t2 = Promise.resolve(t2)), e3 ? t2.then(e3) : t2);
  }
  var Ur = Wr((function(t2, e3, n2, r2, i2) {
    let s2 = arguments.length > 5 && void 0 !== arguments[5] ? arguments[5] : {};
    if (n2 > r2 || n2 < 0) throw new a({ info: { code: _.InvalidUpdateRange } }, `Invalid update range ${n2} for partial update`);
    const o2 = { "Content-Type": "application/octet-stream", "Content-Length": "" + (r2 - n2 + 1), "Content-Range": `bytes ${n2}-${r2}/*` }, h2 = K({ url: m(t2.remoteURL, p(e3)), method: "PUT", headers: o2, data: i2 }, t2, s2);
    return Dr(J(h2, t2), (function(e4) {
      Jt(t2, e4);
    }));
  }));
  function Fr(t2, e3) {
    var n2 = t2();
    return n2 && n2.then ? n2.then(e3) : e3(n2);
  }
  var Vr = Wr((function(t2, e3, n2, r2, i2) {
    let s2 = arguments.length > 5 && void 0 !== arguments[5] ? arguments[5] : {};
    if (n2 > r2 || n2 < 0) throw new a({ info: { code: _.InvalidUpdateRange } }, `Invalid update range ${n2} for partial update`);
    const o2 = { "Content-Type": "application/x-sabredav-partialupdate", "Content-Length": "" + (r2 - n2 + 1), "X-Update-Range": `bytes=${n2}-${r2}` }, h2 = K({ url: m(t2.remoteURL, p(e3)), method: "PATCH", headers: o2, data: i2 }, t2, s2);
    return Dr(J(h2, t2), (function(e4) {
      Jt(t2, e4);
    }));
  }));
  function Wr(t2) {
    return function() {
      for (var e3 = [], n2 = 0; n2 < arguments.length; n2++) e3[n2] = arguments[n2];
      try {
        return Promise.resolve(t2.apply(this, e3));
      } catch (t3) {
        return Promise.reject(t3);
      }
    };
  }
  var Br = Wr((function(t2, e3, n2, r2, i2) {
    let s2 = arguments.length > 5 && void 0 !== arguments[5] ? arguments[5] : {};
    return Dr(Lr(t2, e3, s2), (function(o2) {
      let h2 = false;
      return Fr((function() {
        if (o2.compliance.includes("sabredav-partialupdate")) return Dr(Vr(t2, e3, n2, r2, i2, s2), (function(t3) {
          return h2 = true, t3;
        }));
      }), (function(l2) {
        let u2 = false;
        return h2 ? l2 : Fr((function() {
          if (o2.server.includes("Apache") && o2.compliance.includes("<http://apache.org/dav/propset/fs/1>")) return Dr(Ur(t2, e3, n2, r2, i2, s2), (function(t3) {
            return u2 = true, t3;
          }));
        }), (function(t3) {
          if (u2) return t3;
          throw new a({ info: { code: _.NotSupported } }, "Not supported");
        }));
      }));
    }));
  }));

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

  // node_modules/@nextcloud/files/dist/chunks/dav-Rt1kTtvI.mjs
  var logger = getLoggerBuilder().setApp("@nextcloud/files").detectUser().build();
  var FileType = /* @__PURE__ */ ((FileType2) => {
    FileType2["Folder"] = "folder";
    FileType2["File"] = "file";
    return FileType2;
  })(FileType || {});
  function getRootPath() {
    if (isPublicShare()) {
      return `/files/${getSharingToken()}`;
    }
    return `/files/${getCurrentUser()?.uid}`;
  }
  var defaultRootPath = getRootPath();
  function getRemoteURL() {
    const url = generateRemoteUrl("dav");
    if (isPublicShare()) {
      return url.replace("remote.php", "public.php");
    }
    return url;
  }
  var defaultRemoteURL = getRemoteURL();

  // src/shims/string_decoder.js
  var StringDecoder = class {
    constructor(encoding = "utf-8") {
      this.decoder = new TextDecoder(encoding);
    }
    write(buffer) {
      return this.decoder.decode(buffer, { stream: true });
    }
    end(buffer) {
      return buffer ? this.decoder.decode(buffer) : this.decoder.decode();
    }
  };
  var string_decoder_default = { StringDecoder };

  // node_modules/dompurify/dist/purify.es.mjs
  function _arrayLikeToArray(r2, a2) {
    (null == a2 || a2 > r2.length) && (a2 = r2.length);
    for (var e3 = 0, n2 = Array(a2); e3 < a2; e3++) n2[e3] = r2[e3];
    return n2;
  }
  function _arrayWithHoles(r2) {
    if (Array.isArray(r2)) return r2;
  }
  function _iterableToArrayLimit(r2, l2) {
    var t2 = null == r2 ? null : "undefined" != typeof Symbol && r2[Symbol.iterator] || r2["@@iterator"];
    if (null != t2) {
      var e3, n2, i2, u2, a2 = [], f = true, o2 = false;
      try {
        if (i2 = (t2 = t2.call(r2)).next, 0 === l2) ;
        else for (; !(f = (e3 = i2.call(t2)).done) && (a2.push(e3.value), a2.length !== l2); f = true) ;
      } catch (r3) {
        o2 = true, n2 = r3;
      } finally {
        try {
          if (!f && null != t2.return && (u2 = t2.return(), Object(u2) !== u2)) return;
        } finally {
          if (o2) throw n2;
        }
      }
      return a2;
    }
  }
  function _nonIterableRest() {
    throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
  }
  function _slicedToArray(r2, e3) {
    return _arrayWithHoles(r2) || _iterableToArrayLimit(r2, e3) || _unsupportedIterableToArray(r2, e3) || _nonIterableRest();
  }
  function _unsupportedIterableToArray(r2, a2) {
    if (r2) {
      if ("string" == typeof r2) return _arrayLikeToArray(r2, a2);
      var t2 = {}.toString.call(r2).slice(8, -1);
      return "Object" === t2 && r2.constructor && (t2 = r2.constructor.name), "Map" === t2 || "Set" === t2 ? Array.from(r2) : "Arguments" === t2 || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t2) ? _arrayLikeToArray(r2, a2) : void 0;
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
    freeze = function freeze2(x2) {
      return x2;
    };
  }
  if (!seal) {
    seal = function seal2(x2) {
      return x2;
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
    let l2 = array.length;
    while (l2--) {
      let element2 = array[l2];
      if (typeof element2 === "string") {
        const lcElement = transformCaseFunc(element2);
        if (lcElement !== element2) {
          if (!isFrozen(array)) {
            array[l2] = lcElement;
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
    } catch (_2) {
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
      } catch (_2) {
        remove(node);
        if (!getParentNode(node)) {
          throw typeErrorCreate("a node selected for removal could not be detached from its tree and cannot be safely returned; refusing to sanitize in place");
        }
      }
    };
    const _stripAttributeNode = function _stripAttributeNode2(element2, attribute, name) {
      try {
        removeAttributeNode(element2, attribute);
      } catch (_2) {
        try {
          element2.removeAttribute(name);
        } catch (_3) {
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
          } catch (_2) {
          }
        });
      }
      const attributes = getAttributes(root);
      if (attributes) {
        for (let i2 = attributes.length - 1; i2 >= 0; --i2) {
          const attribute = attributes[i2];
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
        } catch (_2) {
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
      } catch (_2) {
        try {
          element2.removeAttribute(name);
        } catch (_3) {
        }
      }
      if (name === "is") {
        if (RETURN_DOM || RETURN_DOM_FRAGMENT) {
          try {
            _forceRemove(element2);
          } catch (_2) {
          }
        } else {
          try {
            element2.setAttribute(name, "");
          } catch (_2) {
          }
        }
      }
    };
    const _stripDisallowedAttributes = function _stripDisallowedAttributes2(element2) {
      const attributes = getAttributes(element2);
      if (!attributes) {
        return;
      }
      for (let i2 = attributes.length - 1; i2 >= 0; --i2) {
        const attribute = attributes[i2];
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
          for (let i2 = childNodes.length - 1; i2 >= 0; --i2) {
            stack.push(childNodes[i2]);
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
          } catch (_2) {
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
          } catch (_2) {
          }
        }
        const childNodes = getChildNodes(node);
        if (childNodes) {
          for (let i2 = childNodes.length - 1; i2 >= 0; --i2) {
            stack.push(childNodes[i2]);
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
        } catch (_2) {
        }
      }
      if (!doc || !doc.documentElement) {
        doc = implementation.createDocument(NAMESPACE, "template", null);
        try {
          doc.documentElement.innerHTML = IS_EMPTY_INPUT ? emptyHTML : dirtyPayload;
        } catch (_2) {
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
      } catch (_2) {
        return false;
      }
    };
    const _isNode = function _isNode2(value) {
      if (!getNodeType || typeof value !== "object" || value === null) {
        return false;
      }
      try {
        return typeof getNodeType(value) === "number";
      } catch (_2) {
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
          for (let i2 = childCount - 1; i2 >= 0; --i2) {
            const hoisted = currentNode === root ? cloneNode(childNodes[i2], true) : childNodes[i2];
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
      const nt2 = _readNodeType(currentNode);
      if (nt2 === NODE_TYPE.element && !_checkValidNamespace(currentNode)) {
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
      } catch (_2) {
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
      let l2 = attributes.length;
      const lcTag = transformCaseFunc(currentNode.nodeName);
      while (l2--) {
        const attr = attributes[l2];
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
          for (let i2 = childNodes.length - 1; i2 >= 0; --i2) {
            stack.push({
              node: childNodes[i2],
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
          const sr2 = getShadowRoot(node);
          if (_isDocumentFragment(sr2)) {
            stack.push({
              node: null,
              shadow: sr2
            }, {
              node: sr2,
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
        const nn2 = _readNodeName(dirty);
        if (typeof nn2 === "string") {
          const tagName = transformCaseFunc(nn2);
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
          const escape2 = replacement.escape !== false ? import_escape_html.default : identity;
          return escape2(`${replacement.value}`);
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
  var DefaultType = /* @__PURE__ */ ((DefaultType2) => {
    DefaultType2["DEFAULT"] = "default";
    DefaultType2["HIDDEN"] = "hidden";
    return DefaultType2;
  })(DefaultType || {});
  var FileAction = class {
    constructor(action) {
      __publicField(this, "_action");
      this.validateAction(action);
      this._action = action;
    }
    get id() {
      return this._action.id;
    }
    get displayName() {
      return this._action.displayName;
    }
    get title() {
      return this._action.title;
    }
    get iconSvgInline() {
      return this._action.iconSvgInline;
    }
    get enabled() {
      return this._action.enabled;
    }
    get exec() {
      return this._action.exec;
    }
    get execBatch() {
      return this._action.execBatch;
    }
    get hotkey() {
      return this._action.hotkey;
    }
    get order() {
      return this._action.order;
    }
    get parent() {
      return this._action.parent;
    }
    get default() {
      return this._action.default;
    }
    get destructive() {
      return this._action.destructive;
    }
    get inline() {
      return this._action.inline;
    }
    get renderInline() {
      return this._action.renderInline;
    }
    validateAction(action) {
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
  };
  var registerFileAction = function(action) {
    if (typeof window._nc_fileactions === "undefined") {
      window._nc_fileactions = [];
      logger.debug("FileActions initialized");
    }
    if (window._nc_fileactions.find((search) => search.id === action.id)) {
      logger.error(`FileAction ${action.id} already registered`, { action });
      return;
    }
    window._nc_fileactions.push(action);
  };
  var debug_1;
  var hasRequiredDebug;
  function requireDebug() {
    if (hasRequiredDebug) return debug_1;
    hasRequiredDebug = 1;
    const debug = typeof process === "object" && process.env && process.env.NODE_DEBUG && /\bsemver\b/i.test(process.env.NODE_DEBUG) ? (...args) => console.error("SEMVER", ...args) : () => {
    };
    debug_1 = debug;
    return debug_1;
  }
  var constants;
  var hasRequiredConstants;
  function requireConstants() {
    if (hasRequiredConstants) return constants;
    hasRequiredConstants = 1;
    const SEMVER_SPEC_VERSION = "2.0.0";
    const MAX_LENGTH = 256;
    const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER || /* istanbul ignore next */
    9007199254740991;
    const MAX_SAFE_COMPONENT_LENGTH = 16;
    const MAX_SAFE_BUILD_LENGTH = MAX_LENGTH - 6;
    const RELEASE_TYPES = [
      "major",
      "premajor",
      "minor",
      "preminor",
      "patch",
      "prepatch",
      "prerelease"
    ];
    constants = {
      MAX_LENGTH,
      MAX_SAFE_COMPONENT_LENGTH,
      MAX_SAFE_BUILD_LENGTH,
      MAX_SAFE_INTEGER,
      RELEASE_TYPES,
      SEMVER_SPEC_VERSION,
      FLAG_INCLUDE_PRERELEASE: 1,
      FLAG_LOOSE: 2
    };
    return constants;
  }
  var re2 = { exports: {} };
  var hasRequiredRe;
  function requireRe() {
    if (hasRequiredRe) return re2.exports;
    hasRequiredRe = 1;
    (function(module, exports) {
      const {
        MAX_SAFE_COMPONENT_LENGTH,
        MAX_SAFE_BUILD_LENGTH,
        MAX_LENGTH
      } = requireConstants();
      const debug = requireDebug();
      exports = module.exports = {};
      const re22 = exports.re = [];
      const safeRe = exports.safeRe = [];
      const src = exports.src = [];
      const safeSrc = exports.safeSrc = [];
      const t2 = exports.t = {};
      let R2 = 0;
      const LETTERDASHNUMBER = "[a-zA-Z0-9-]";
      const safeRegexReplacements = [
        ["\\s", 1],
        ["\\d", MAX_LENGTH],
        [LETTERDASHNUMBER, MAX_SAFE_BUILD_LENGTH]
      ];
      const makeSafeRegex = (value) => {
        for (const [token, max] of safeRegexReplacements) {
          value = value.split(`${token}*`).join(`${token}{0,${max}}`).split(`${token}+`).join(`${token}{1,${max}}`);
        }
        return value;
      };
      const createToken = (name, value, isGlobal) => {
        const safe = makeSafeRegex(value);
        const index = R2++;
        debug(name, index, value);
        t2[name] = index;
        src[index] = value;
        safeSrc[index] = safe;
        re22[index] = new RegExp(value, isGlobal ? "g" : void 0);
        safeRe[index] = new RegExp(safe, isGlobal ? "g" : void 0);
      };
      createToken("NUMERICIDENTIFIER", "0|[1-9]\\d*");
      createToken("NUMERICIDENTIFIERLOOSE", "\\d+");
      createToken("NONNUMERICIDENTIFIER", `\\d*[a-zA-Z-]${LETTERDASHNUMBER}*`);
      createToken("MAINVERSION", `(${src[t2.NUMERICIDENTIFIER]})\\.(${src[t2.NUMERICIDENTIFIER]})\\.(${src[t2.NUMERICIDENTIFIER]})`);
      createToken("MAINVERSIONLOOSE", `(${src[t2.NUMERICIDENTIFIERLOOSE]})\\.(${src[t2.NUMERICIDENTIFIERLOOSE]})\\.(${src[t2.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASEIDENTIFIER", `(?:${src[t2.NONNUMERICIDENTIFIER]}|${src[t2.NUMERICIDENTIFIER]})`);
      createToken("PRERELEASEIDENTIFIERLOOSE", `(?:${src[t2.NONNUMERICIDENTIFIER]}|${src[t2.NUMERICIDENTIFIERLOOSE]})`);
      createToken("PRERELEASE", `(?:-(${src[t2.PRERELEASEIDENTIFIER]}(?:\\.${src[t2.PRERELEASEIDENTIFIER]})*))`);
      createToken("PRERELEASELOOSE", `(?:-?(${src[t2.PRERELEASEIDENTIFIERLOOSE]}(?:\\.${src[t2.PRERELEASEIDENTIFIERLOOSE]})*))`);
      createToken("BUILDIDENTIFIER", `${LETTERDASHNUMBER}+`);
      createToken("BUILD", `(?:\\+(${src[t2.BUILDIDENTIFIER]}(?:\\.${src[t2.BUILDIDENTIFIER]})*))`);
      createToken("FULLPLAIN", `v?${src[t2.MAINVERSION]}${src[t2.PRERELEASE]}?${src[t2.BUILD]}?`);
      createToken("FULL", `^${src[t2.FULLPLAIN]}$`);
      createToken("LOOSEPLAIN", `[v=\\s]*${src[t2.MAINVERSIONLOOSE]}${src[t2.PRERELEASELOOSE]}?${src[t2.BUILD]}?`);
      createToken("LOOSE", `^${src[t2.LOOSEPLAIN]}$`);
      createToken("GTLT", "((?:<|>)?=?)");
      createToken("XRANGEIDENTIFIERLOOSE", `${src[t2.NUMERICIDENTIFIERLOOSE]}|x|X|\\*`);
      createToken("XRANGEIDENTIFIER", `${src[t2.NUMERICIDENTIFIER]}|x|X|\\*`);
      createToken("XRANGEPLAIN", `[v=\\s]*(${src[t2.XRANGEIDENTIFIER]})(?:\\.(${src[t2.XRANGEIDENTIFIER]})(?:\\.(${src[t2.XRANGEIDENTIFIER]})(?:${src[t2.PRERELEASE]})?${src[t2.BUILD]}?)?)?`);
      createToken("XRANGEPLAINLOOSE", `[v=\\s]*(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:\\.(${src[t2.XRANGEIDENTIFIERLOOSE]})(?:${src[t2.PRERELEASELOOSE]})?${src[t2.BUILD]}?)?)?`);
      createToken("XRANGE", `^${src[t2.GTLT]}\\s*${src[t2.XRANGEPLAIN]}$`);
      createToken("XRANGELOOSE", `^${src[t2.GTLT]}\\s*${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("COERCEPLAIN", `${"(^|[^\\d])(\\d{1,"}${MAX_SAFE_COMPONENT_LENGTH}})(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?(?:\\.(\\d{1,${MAX_SAFE_COMPONENT_LENGTH}}))?`);
      createToken("COERCE", `${src[t2.COERCEPLAIN]}(?:$|[^\\d])`);
      createToken("COERCEFULL", src[t2.COERCEPLAIN] + `(?:${src[t2.PRERELEASE]})?(?:${src[t2.BUILD]})?(?:$|[^\\d])`);
      createToken("COERCERTL", src[t2.COERCE], true);
      createToken("COERCERTLFULL", src[t2.COERCEFULL], true);
      createToken("LONETILDE", "(?:~>?)");
      createToken("TILDETRIM", `(\\s*)${src[t2.LONETILDE]}\\s+`, true);
      exports.tildeTrimReplace = "$1~";
      createToken("TILDE", `^${src[t2.LONETILDE]}${src[t2.XRANGEPLAIN]}$`);
      createToken("TILDELOOSE", `^${src[t2.LONETILDE]}${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("LONECARET", "(?:\\^)");
      createToken("CARETTRIM", `(\\s*)${src[t2.LONECARET]}\\s+`, true);
      exports.caretTrimReplace = "$1^";
      createToken("CARET", `^${src[t2.LONECARET]}${src[t2.XRANGEPLAIN]}$`);
      createToken("CARETLOOSE", `^${src[t2.LONECARET]}${src[t2.XRANGEPLAINLOOSE]}$`);
      createToken("COMPARATORLOOSE", `^${src[t2.GTLT]}\\s*(${src[t2.LOOSEPLAIN]})$|^$`);
      createToken("COMPARATOR", `^${src[t2.GTLT]}\\s*(${src[t2.FULLPLAIN]})$|^$`);
      createToken("COMPARATORTRIM", `(\\s*)${src[t2.GTLT]}\\s*(${src[t2.LOOSEPLAIN]}|${src[t2.XRANGEPLAIN]})`, true);
      exports.comparatorTrimReplace = "$1$2$3";
      createToken("HYPHENRANGE", `^\\s*(${src[t2.XRANGEPLAIN]})\\s+-\\s+(${src[t2.XRANGEPLAIN]})\\s*$`);
      createToken("HYPHENRANGELOOSE", `^\\s*(${src[t2.XRANGEPLAINLOOSE]})\\s+-\\s+(${src[t2.XRANGEPLAINLOOSE]})\\s*$`);
      createToken("STAR", "(<|>)?=?\\s*\\*");
      createToken("GTE0", "^\\s*>=\\s*0\\.0\\.0\\s*$");
      createToken("GTE0PRE", "^\\s*>=\\s*0\\.0\\.0-0\\s*$");
    })(re2, re2.exports);
    return re2.exports;
  }
  var parseOptions_1;
  var hasRequiredParseOptions;
  function requireParseOptions() {
    if (hasRequiredParseOptions) return parseOptions_1;
    hasRequiredParseOptions = 1;
    const looseOption = Object.freeze({ loose: true });
    const emptyOpts = Object.freeze({});
    const parseOptions = (options) => {
      if (!options) {
        return emptyOpts;
      }
      if (typeof options !== "object") {
        return looseOption;
      }
      return options;
    };
    parseOptions_1 = parseOptions;
    return parseOptions_1;
  }
  var identifiers;
  var hasRequiredIdentifiers;
  function requireIdentifiers() {
    if (hasRequiredIdentifiers) return identifiers;
    hasRequiredIdentifiers = 1;
    const numeric = /^[0-9]+$/;
    const compareIdentifiers = (a2, b2) => {
      if (typeof a2 === "number" && typeof b2 === "number") {
        return a2 === b2 ? 0 : a2 < b2 ? -1 : 1;
      }
      const anum = numeric.test(a2);
      const bnum = numeric.test(b2);
      if (anum && bnum) {
        a2 = +a2;
        b2 = +b2;
      }
      return a2 === b2 ? 0 : anum && !bnum ? -1 : bnum && !anum ? 1 : a2 < b2 ? -1 : 1;
    };
    const rcompareIdentifiers = (a2, b2) => compareIdentifiers(b2, a2);
    identifiers = {
      compareIdentifiers,
      rcompareIdentifiers
    };
    return identifiers;
  }
  var semver;
  var hasRequiredSemver;
  function requireSemver() {
    if (hasRequiredSemver) return semver;
    hasRequiredSemver = 1;
    const debug = requireDebug();
    const { MAX_LENGTH, MAX_SAFE_INTEGER } = requireConstants();
    const { safeRe: re22, t: t2 } = requireRe();
    const parseOptions = requireParseOptions();
    const { compareIdentifiers } = requireIdentifiers();
    class SemVer {
      constructor(version, options) {
        options = parseOptions(options);
        if (version instanceof SemVer) {
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
        const m2 = version.trim().match(options.loose ? re22[t2.LOOSE] : re22[t2.FULL]);
        if (!m2) {
          throw new TypeError(`Invalid Version: ${version}`);
        }
        this.raw = version;
        this.major = +m2[1];
        this.minor = +m2[2];
        this.patch = +m2[3];
        if (this.major > MAX_SAFE_INTEGER || this.major < 0) {
          throw new TypeError("Invalid major version");
        }
        if (this.minor > MAX_SAFE_INTEGER || this.minor < 0) {
          throw new TypeError("Invalid minor version");
        }
        if (this.patch > MAX_SAFE_INTEGER || this.patch < 0) {
          throw new TypeError("Invalid patch version");
        }
        if (!m2[4]) {
          this.prerelease = [];
        } else {
          this.prerelease = m2[4].split(".").map((id) => {
            if (/^[0-9]+$/.test(id)) {
              const num = +id;
              if (num >= 0 && num < MAX_SAFE_INTEGER) {
                return num;
              }
            }
            return id;
          });
        }
        this.build = m2[5] ? m2[5].split(".") : [];
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
        if (!(other instanceof SemVer)) {
          if (typeof other === "string" && other === this.version) {
            return 0;
          }
          other = new SemVer(other, this.options);
        }
        if (other.version === this.version) {
          return 0;
        }
        return this.compareMain(other) || this.comparePre(other);
      }
      compareMain(other) {
        if (!(other instanceof SemVer)) {
          other = new SemVer(other, this.options);
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
        if (!(other instanceof SemVer)) {
          other = new SemVer(other, this.options);
        }
        if (this.prerelease.length && !other.prerelease.length) {
          return -1;
        } else if (!this.prerelease.length && other.prerelease.length) {
          return 1;
        } else if (!this.prerelease.length && !other.prerelease.length) {
          return 0;
        }
        let i2 = 0;
        do {
          const a2 = this.prerelease[i2];
          const b2 = other.prerelease[i2];
          debug("prerelease compare", i2, a2, b2);
          if (a2 === void 0 && b2 === void 0) {
            return 0;
          } else if (b2 === void 0) {
            return 1;
          } else if (a2 === void 0) {
            return -1;
          } else if (a2 === b2) {
            continue;
          } else {
            return compareIdentifiers(a2, b2);
          }
        } while (++i2);
      }
      compareBuild(other) {
        if (!(other instanceof SemVer)) {
          other = new SemVer(other, this.options);
        }
        let i2 = 0;
        do {
          const a2 = this.build[i2];
          const b2 = other.build[i2];
          debug("build compare", i2, a2, b2);
          if (a2 === void 0 && b2 === void 0) {
            return 0;
          } else if (b2 === void 0) {
            return 1;
          } else if (a2 === void 0) {
            return -1;
          } else if (a2 === b2) {
            continue;
          } else {
            return compareIdentifiers(a2, b2);
          }
        } while (++i2);
      }
      // preminor will bump the version up to the next minor release, and immediately
      // down to pre-release. premajor and prepatch work the same way.
      inc(release, identifier, identifierBase) {
        if (release.startsWith("pre")) {
          if (!identifier && identifierBase === false) {
            throw new Error("invalid increment argument: identifier is empty");
          }
          if (identifier) {
            const match = `-${identifier}`.match(this.options.loose ? re22[t2.PRERELEASELOOSE] : re22[t2.PRERELEASE]);
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
              let i2 = this.prerelease.length;
              while (--i2 >= 0) {
                if (typeof this.prerelease[i2] === "number") {
                  this.prerelease[i2]++;
                  i2 = -2;
                }
              }
              if (i2 === -1) {
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
              if (compareIdentifiers(this.prerelease[0], identifier) === 0) {
                if (isNaN(this.prerelease[1])) {
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
    }
    semver = SemVer;
    return semver;
  }
  var major_1;
  var hasRequiredMajor;
  function requireMajor() {
    if (hasRequiredMajor) return major_1;
    hasRequiredMajor = 1;
    const SemVer = requireSemver();
    const major2 = (a2, loose) => new SemVer(a2, loose).major;
    major_1 = major2;
    return major_1;
  }
  var majorExports = requireMajor();
  var parse_1;
  var hasRequiredParse;
  function requireParse() {
    if (hasRequiredParse) return parse_1;
    hasRequiredParse = 1;
    const SemVer = requireSemver();
    const parse = (version, options, throwErrors = false) => {
      if (version instanceof SemVer) {
        return version;
      }
      try {
        return new SemVer(version, options);
      } catch (er2) {
        if (!throwErrors) {
          return null;
        }
        throw er2;
      }
    };
    parse_1 = parse;
    return parse_1;
  }
  var valid_1;
  var hasRequiredValid;
  function requireValid() {
    if (hasRequiredValid) return valid_1;
    hasRequiredValid = 1;
    const parse = requireParse();
    const valid2 = (version, options) => {
      const v2 = parse(version, options);
      return v2 ? v2.version : null;
    };
    valid_1 = valid2;
    return valid_1;
  }
  var validExports = requireValid();
  var sax$1 = {};
  var hasRequiredSax;
  function requireSax() {
    if (hasRequiredSax) return sax$1;
    hasRequiredSax = 1;
    (function(exports) {
      (function(sax2) {
        sax2.parser = function(strict, opt) {
          return new SAXParser(strict, opt);
        };
        sax2.SAXParser = SAXParser;
        sax2.SAXStream = SAXStream;
        sax2.createStream = createStream;
        sax2.MAX_BUFFER_LENGTH = 64 * 1024;
        var buffers = [
          "comment",
          "sgmlDecl",
          "textNode",
          "tagName",
          "doctype",
          "procInstName",
          "procInstBody",
          "entity",
          "attribName",
          "attribValue",
          "cdata",
          "script"
        ];
        sax2.EVENTS = [
          "text",
          "processinginstruction",
          "sgmldeclaration",
          "doctype",
          "comment",
          "opentagstart",
          "attribute",
          "opentag",
          "closetag",
          "opencdata",
          "cdata",
          "closecdata",
          "error",
          "end",
          "ready",
          "script",
          "opennamespace",
          "closenamespace"
        ];
        function SAXParser(strict, opt) {
          if (!(this instanceof SAXParser)) {
            return new SAXParser(strict, opt);
          }
          var parser = this;
          clearBuffers(parser);
          parser.q = parser.c = "";
          parser.bufferCheckPosition = sax2.MAX_BUFFER_LENGTH;
          parser.opt = opt || {};
          parser.opt.lowercase = parser.opt.lowercase || parser.opt.lowercasetags;
          parser.looseCase = parser.opt.lowercase ? "toLowerCase" : "toUpperCase";
          parser.tags = [];
          parser.closed = parser.closedRoot = parser.sawRoot = false;
          parser.tag = parser.error = null;
          parser.strict = !!strict;
          parser.noscript = !!(strict || parser.opt.noscript);
          parser.state = S2.BEGIN;
          parser.strictEntities = parser.opt.strictEntities;
          parser.ENTITIES = parser.strictEntities ? Object.create(sax2.XML_ENTITIES) : Object.create(sax2.ENTITIES);
          parser.attribList = [];
          if (parser.opt.xmlns) {
            parser.ns = Object.create(rootNS);
          }
          if (parser.opt.unquotedAttributeValues === void 0) {
            parser.opt.unquotedAttributeValues = !strict;
          }
          parser.trackPosition = parser.opt.position !== false;
          if (parser.trackPosition) {
            parser.position = parser.line = parser.column = 0;
          }
          emit2(parser, "onready");
        }
        if (!Object.create) {
          Object.create = function(o2) {
            function F2() {
            }
            F2.prototype = o2;
            var newf = new F2();
            return newf;
          };
        }
        if (!Object.keys) {
          Object.keys = function(o2) {
            var a2 = [];
            for (var i2 in o2) if (o2.hasOwnProperty(i2)) a2.push(i2);
            return a2;
          };
        }
        function checkBufferLength(parser) {
          var maxAllowed = Math.max(sax2.MAX_BUFFER_LENGTH, 10);
          var maxActual = 0;
          for (var i2 = 0, l2 = buffers.length; i2 < l2; i2++) {
            var len = parser[buffers[i2]].length;
            if (len > maxAllowed) {
              switch (buffers[i2]) {
                case "textNode":
                  closeText(parser);
                  break;
                case "cdata":
                  emitNode(parser, "oncdata", parser.cdata);
                  parser.cdata = "";
                  break;
                case "script":
                  emitNode(parser, "onscript", parser.script);
                  parser.script = "";
                  break;
                default:
                  error(parser, "Max buffer length exceeded: " + buffers[i2]);
              }
            }
            maxActual = Math.max(maxActual, len);
          }
          var m2 = sax2.MAX_BUFFER_LENGTH - maxActual;
          parser.bufferCheckPosition = m2 + parser.position;
        }
        function clearBuffers(parser) {
          for (var i2 = 0, l2 = buffers.length; i2 < l2; i2++) {
            parser[buffers[i2]] = "";
          }
        }
        function flushBuffers(parser) {
          closeText(parser);
          if (parser.cdata !== "") {
            emitNode(parser, "oncdata", parser.cdata);
            parser.cdata = "";
          }
          if (parser.script !== "") {
            emitNode(parser, "onscript", parser.script);
            parser.script = "";
          }
        }
        SAXParser.prototype = {
          end: function() {
            end(this);
          },
          write,
          resume: function() {
            this.error = null;
            return this;
          },
          close: function() {
            return this.write(null);
          },
          flush: function() {
            flushBuffers(this);
          }
        };
        var Stream;
        try {
          Stream = __require("stream").Stream;
        } catch (ex) {
          Stream = function() {
          };
        }
        if (!Stream) Stream = function() {
        };
        var streamWraps = sax2.EVENTS.filter(function(ev) {
          return ev !== "error" && ev !== "end";
        });
        function createStream(strict, opt) {
          return new SAXStream(strict, opt);
        }
        function SAXStream(strict, opt) {
          if (!(this instanceof SAXStream)) {
            return new SAXStream(strict, opt);
          }
          Stream.apply(this);
          this._parser = new SAXParser(strict, opt);
          this.writable = true;
          this.readable = true;
          var me2 = this;
          this._parser.onend = function() {
            me2.emit("end");
          };
          this._parser.onerror = function(er2) {
            me2.emit("error", er2);
            me2._parser.error = null;
          };
          this._decoder = null;
          streamWraps.forEach(function(ev) {
            Object.defineProperty(me2, "on" + ev, {
              get: function() {
                return me2._parser["on" + ev];
              },
              set: function(h2) {
                if (!h2) {
                  me2.removeAllListeners(ev);
                  me2._parser["on" + ev] = h2;
                  return h2;
                }
                me2.on(ev, h2);
              },
              enumerable: true,
              configurable: false
            });
          });
        }
        SAXStream.prototype = Object.create(Stream.prototype, {
          constructor: {
            value: SAXStream
          }
        });
        SAXStream.prototype.write = function(data) {
          if (typeof Buffer === "function" && typeof Buffer.isBuffer === "function" && Buffer.isBuffer(data)) {
            if (!this._decoder) {
              var SD = string_decoder_default.StringDecoder;
              this._decoder = new SD("utf8");
            }
            data = this._decoder.write(data);
          }
          this._parser.write(data.toString());
          this.emit("data", data);
          return true;
        };
        SAXStream.prototype.end = function(chunk) {
          if (chunk && chunk.length) {
            this.write(chunk);
          }
          this._parser.end();
          return true;
        };
        SAXStream.prototype.on = function(ev, handler) {
          var me2 = this;
          if (!me2._parser["on" + ev] && streamWraps.indexOf(ev) !== -1) {
            me2._parser["on" + ev] = function() {
              var args = arguments.length === 1 ? [arguments[0]] : Array.apply(null, arguments);
              args.splice(0, 0, ev);
              me2.emit.apply(me2, args);
            };
          }
          return Stream.prototype.on.call(me2, ev, handler);
        };
        var CDATA = "[CDATA[";
        var DOCTYPE = "DOCTYPE";
        var XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace";
        var XMLNS_NAMESPACE = "http://www.w3.org/2000/xmlns/";
        var rootNS = { xml: XML_NAMESPACE, xmlns: XMLNS_NAMESPACE };
        var nameStart = /[:_A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD]/;
        var nameBody = /[:_A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\u00B7\u0300-\u036F\u203F-\u2040.\d-]/;
        var entityStart = /[#:_A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD]/;
        var entityBody = /[#:_A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\u00B7\u0300-\u036F\u203F-\u2040.\d-]/;
        function isWhitespace(c2) {
          return c2 === " " || c2 === "\n" || c2 === "\r" || c2 === "	";
        }
        function isQuote(c2) {
          return c2 === '"' || c2 === "'";
        }
        function isAttribEnd(c2) {
          return c2 === ">" || isWhitespace(c2);
        }
        function isMatch(regex, c2) {
          return regex.test(c2);
        }
        function notMatch(regex, c2) {
          return !isMatch(regex, c2);
        }
        var S2 = 0;
        sax2.STATE = {
          BEGIN: S2++,
          // leading byte order mark or whitespace
          BEGIN_WHITESPACE: S2++,
          // leading whitespace
          TEXT: S2++,
          // general stuff
          TEXT_ENTITY: S2++,
          // &amp and such.
          OPEN_WAKA: S2++,
          // <
          SGML_DECL: S2++,
          // <!BLARG
          SGML_DECL_QUOTED: S2++,
          // <!BLARG foo "bar
          DOCTYPE: S2++,
          // <!DOCTYPE
          DOCTYPE_QUOTED: S2++,
          // <!DOCTYPE "//blah
          DOCTYPE_DTD: S2++,
          // <!DOCTYPE "//blah" [ ...
          DOCTYPE_DTD_QUOTED: S2++,
          // <!DOCTYPE "//blah" [ "foo
          COMMENT_STARTING: S2++,
          // <!-
          COMMENT: S2++,
          // <!--
          COMMENT_ENDING: S2++,
          // <!-- blah -
          COMMENT_ENDED: S2++,
          // <!-- blah --
          CDATA: S2++,
          // <![CDATA[ something
          CDATA_ENDING: S2++,
          // ]
          CDATA_ENDING_2: S2++,
          // ]]
          PROC_INST: S2++,
          // <?hi
          PROC_INST_BODY: S2++,
          // <?hi there
          PROC_INST_ENDING: S2++,
          // <?hi "there" ?
          OPEN_TAG: S2++,
          // <strong
          OPEN_TAG_SLASH: S2++,
          // <strong /
          ATTRIB: S2++,
          // <a
          ATTRIB_NAME: S2++,
          // <a foo
          ATTRIB_NAME_SAW_WHITE: S2++,
          // <a foo _
          ATTRIB_VALUE: S2++,
          // <a foo=
          ATTRIB_VALUE_QUOTED: S2++,
          // <a foo="bar
          ATTRIB_VALUE_CLOSED: S2++,
          // <a foo="bar"
          ATTRIB_VALUE_UNQUOTED: S2++,
          // <a foo=bar
          ATTRIB_VALUE_ENTITY_Q: S2++,
          // <foo bar="&quot;"
          ATTRIB_VALUE_ENTITY_U: S2++,
          // <foo bar=&quot
          CLOSE_TAG: S2++,
          // </a
          CLOSE_TAG_SAW_WHITE: S2++,
          // </a   >
          SCRIPT: S2++,
          // <script> ...
          SCRIPT_ENDING: S2++
          // <script> ... <
        };
        sax2.XML_ENTITIES = {
          "amp": "&",
          "gt": ">",
          "lt": "<",
          "quot": '"',
          "apos": "'"
        };
        sax2.ENTITIES = {
          "amp": "&",
          "gt": ">",
          "lt": "<",
          "quot": '"',
          "apos": "'",
          "AElig": 198,
          "Aacute": 193,
          "Acirc": 194,
          "Agrave": 192,
          "Aring": 197,
          "Atilde": 195,
          "Auml": 196,
          "Ccedil": 199,
          "ETH": 208,
          "Eacute": 201,
          "Ecirc": 202,
          "Egrave": 200,
          "Euml": 203,
          "Iacute": 205,
          "Icirc": 206,
          "Igrave": 204,
          "Iuml": 207,
          "Ntilde": 209,
          "Oacute": 211,
          "Ocirc": 212,
          "Ograve": 210,
          "Oslash": 216,
          "Otilde": 213,
          "Ouml": 214,
          "THORN": 222,
          "Uacute": 218,
          "Ucirc": 219,
          "Ugrave": 217,
          "Uuml": 220,
          "Yacute": 221,
          "aacute": 225,
          "acirc": 226,
          "aelig": 230,
          "agrave": 224,
          "aring": 229,
          "atilde": 227,
          "auml": 228,
          "ccedil": 231,
          "eacute": 233,
          "ecirc": 234,
          "egrave": 232,
          "eth": 240,
          "euml": 235,
          "iacute": 237,
          "icirc": 238,
          "igrave": 236,
          "iuml": 239,
          "ntilde": 241,
          "oacute": 243,
          "ocirc": 244,
          "ograve": 242,
          "oslash": 248,
          "otilde": 245,
          "ouml": 246,
          "szlig": 223,
          "thorn": 254,
          "uacute": 250,
          "ucirc": 251,
          "ugrave": 249,
          "uuml": 252,
          "yacute": 253,
          "yuml": 255,
          "copy": 169,
          "reg": 174,
          "nbsp": 160,
          "iexcl": 161,
          "cent": 162,
          "pound": 163,
          "curren": 164,
          "yen": 165,
          "brvbar": 166,
          "sect": 167,
          "uml": 168,
          "ordf": 170,
          "laquo": 171,
          "not": 172,
          "shy": 173,
          "macr": 175,
          "deg": 176,
          "plusmn": 177,
          "sup1": 185,
          "sup2": 178,
          "sup3": 179,
          "acute": 180,
          "micro": 181,
          "para": 182,
          "middot": 183,
          "cedil": 184,
          "ordm": 186,
          "raquo": 187,
          "frac14": 188,
          "frac12": 189,
          "frac34": 190,
          "iquest": 191,
          "times": 215,
          "divide": 247,
          "OElig": 338,
          "oelig": 339,
          "Scaron": 352,
          "scaron": 353,
          "Yuml": 376,
          "fnof": 402,
          "circ": 710,
          "tilde": 732,
          "Alpha": 913,
          "Beta": 914,
          "Gamma": 915,
          "Delta": 916,
          "Epsilon": 917,
          "Zeta": 918,
          "Eta": 919,
          "Theta": 920,
          "Iota": 921,
          "Kappa": 922,
          "Lambda": 923,
          "Mu": 924,
          "Nu": 925,
          "Xi": 926,
          "Omicron": 927,
          "Pi": 928,
          "Rho": 929,
          "Sigma": 931,
          "Tau": 932,
          "Upsilon": 933,
          "Phi": 934,
          "Chi": 935,
          "Psi": 936,
          "Omega": 937,
          "alpha": 945,
          "beta": 946,
          "gamma": 947,
          "delta": 948,
          "epsilon": 949,
          "zeta": 950,
          "eta": 951,
          "theta": 952,
          "iota": 953,
          "kappa": 954,
          "lambda": 955,
          "mu": 956,
          "nu": 957,
          "xi": 958,
          "omicron": 959,
          "pi": 960,
          "rho": 961,
          "sigmaf": 962,
          "sigma": 963,
          "tau": 964,
          "upsilon": 965,
          "phi": 966,
          "chi": 967,
          "psi": 968,
          "omega": 969,
          "thetasym": 977,
          "upsih": 978,
          "piv": 982,
          "ensp": 8194,
          "emsp": 8195,
          "thinsp": 8201,
          "zwnj": 8204,
          "zwj": 8205,
          "lrm": 8206,
          "rlm": 8207,
          "ndash": 8211,
          "mdash": 8212,
          "lsquo": 8216,
          "rsquo": 8217,
          "sbquo": 8218,
          "ldquo": 8220,
          "rdquo": 8221,
          "bdquo": 8222,
          "dagger": 8224,
          "Dagger": 8225,
          "bull": 8226,
          "hellip": 8230,
          "permil": 8240,
          "prime": 8242,
          "Prime": 8243,
          "lsaquo": 8249,
          "rsaquo": 8250,
          "oline": 8254,
          "frasl": 8260,
          "euro": 8364,
          "image": 8465,
          "weierp": 8472,
          "real": 8476,
          "trade": 8482,
          "alefsym": 8501,
          "larr": 8592,
          "uarr": 8593,
          "rarr": 8594,
          "darr": 8595,
          "harr": 8596,
          "crarr": 8629,
          "lArr": 8656,
          "uArr": 8657,
          "rArr": 8658,
          "dArr": 8659,
          "hArr": 8660,
          "forall": 8704,
          "part": 8706,
          "exist": 8707,
          "empty": 8709,
          "nabla": 8711,
          "isin": 8712,
          "notin": 8713,
          "ni": 8715,
          "prod": 8719,
          "sum": 8721,
          "minus": 8722,
          "lowast": 8727,
          "radic": 8730,
          "prop": 8733,
          "infin": 8734,
          "ang": 8736,
          "and": 8743,
          "or": 8744,
          "cap": 8745,
          "cup": 8746,
          "int": 8747,
          "there4": 8756,
          "sim": 8764,
          "cong": 8773,
          "asymp": 8776,
          "ne": 8800,
          "equiv": 8801,
          "le": 8804,
          "ge": 8805,
          "sub": 8834,
          "sup": 8835,
          "nsub": 8836,
          "sube": 8838,
          "supe": 8839,
          "oplus": 8853,
          "otimes": 8855,
          "perp": 8869,
          "sdot": 8901,
          "lceil": 8968,
          "rceil": 8969,
          "lfloor": 8970,
          "rfloor": 8971,
          "lang": 9001,
          "rang": 9002,
          "loz": 9674,
          "spades": 9824,
          "clubs": 9827,
          "hearts": 9829,
          "diams": 9830
        };
        Object.keys(sax2.ENTITIES).forEach(function(key) {
          var e22 = sax2.ENTITIES[key];
          var s3 = typeof e22 === "number" ? String.fromCharCode(e22) : e22;
          sax2.ENTITIES[key] = s3;
        });
        for (var s2 in sax2.STATE) {
          sax2.STATE[sax2.STATE[s2]] = s2;
        }
        S2 = sax2.STATE;
        function emit2(parser, event, data) {
          parser[event] && parser[event](data);
        }
        function emitNode(parser, nodeType, data) {
          if (parser.textNode) closeText(parser);
          emit2(parser, nodeType, data);
        }
        function closeText(parser) {
          parser.textNode = textopts(parser.opt, parser.textNode);
          if (parser.textNode) emit2(parser, "ontext", parser.textNode);
          parser.textNode = "";
        }
        function textopts(opt, text2) {
          if (opt.trim) text2 = text2.trim();
          if (opt.normalize) text2 = text2.replace(/\s+/g, " ");
          return text2;
        }
        function error(parser, er2) {
          closeText(parser);
          if (parser.trackPosition) {
            er2 += "\nLine: " + parser.line + "\nColumn: " + parser.column + "\nChar: " + parser.c;
          }
          er2 = new Error(er2);
          parser.error = er2;
          emit2(parser, "onerror", er2);
          return parser;
        }
        function end(parser) {
          if (parser.sawRoot && !parser.closedRoot) strictFail(parser, "Unclosed root tag");
          if (parser.state !== S2.BEGIN && parser.state !== S2.BEGIN_WHITESPACE && parser.state !== S2.TEXT) {
            error(parser, "Unexpected end");
          }
          closeText(parser);
          parser.c = "";
          parser.closed = true;
          emit2(parser, "onend");
          SAXParser.call(parser, parser.strict, parser.opt);
          return parser;
        }
        function strictFail(parser, message) {
          if (typeof parser !== "object" || !(parser instanceof SAXParser)) {
            throw new Error("bad call to strictFail");
          }
          if (parser.strict) {
            error(parser, message);
          }
        }
        function newTag(parser) {
          if (!parser.strict) parser.tagName = parser.tagName[parser.looseCase]();
          var parent = parser.tags[parser.tags.length - 1] || parser;
          var tag = parser.tag = { name: parser.tagName, attributes: {} };
          if (parser.opt.xmlns) {
            tag.ns = parent.ns;
          }
          parser.attribList.length = 0;
          emitNode(parser, "onopentagstart", tag);
        }
        function qname(name, attribute) {
          var i2 = name.indexOf(":");
          var qualName = i2 < 0 ? ["", name] : name.split(":");
          var prefix = qualName[0];
          var local = qualName[1];
          if (attribute && name === "xmlns") {
            prefix = "xmlns";
            local = "";
          }
          return { prefix, local };
        }
        function attrib(parser) {
          if (!parser.strict) {
            parser.attribName = parser.attribName[parser.looseCase]();
          }
          if (parser.attribList.indexOf(parser.attribName) !== -1 || parser.tag.attributes.hasOwnProperty(parser.attribName)) {
            parser.attribName = parser.attribValue = "";
            return;
          }
          if (parser.opt.xmlns) {
            var qn2 = qname(parser.attribName, true);
            var prefix = qn2.prefix;
            var local = qn2.local;
            if (prefix === "xmlns") {
              if (local === "xml" && parser.attribValue !== XML_NAMESPACE) {
                strictFail(
                  parser,
                  "xml: prefix must be bound to " + XML_NAMESPACE + "\nActual: " + parser.attribValue
                );
              } else if (local === "xmlns" && parser.attribValue !== XMLNS_NAMESPACE) {
                strictFail(
                  parser,
                  "xmlns: prefix must be bound to " + XMLNS_NAMESPACE + "\nActual: " + parser.attribValue
                );
              } else {
                var tag = parser.tag;
                var parent = parser.tags[parser.tags.length - 1] || parser;
                if (tag.ns === parent.ns) {
                  tag.ns = Object.create(parent.ns);
                }
                tag.ns[local] = parser.attribValue;
              }
            }
            parser.attribList.push([parser.attribName, parser.attribValue]);
          } else {
            parser.tag.attributes[parser.attribName] = parser.attribValue;
            emitNode(parser, "onattribute", {
              name: parser.attribName,
              value: parser.attribValue
            });
          }
          parser.attribName = parser.attribValue = "";
        }
        function openTag(parser, selfClosing) {
          if (parser.opt.xmlns) {
            var tag = parser.tag;
            var qn2 = qname(parser.tagName);
            tag.prefix = qn2.prefix;
            tag.local = qn2.local;
            tag.uri = tag.ns[qn2.prefix] || "";
            if (tag.prefix && !tag.uri) {
              strictFail(parser, "Unbound namespace prefix: " + JSON.stringify(parser.tagName));
              tag.uri = qn2.prefix;
            }
            var parent = parser.tags[parser.tags.length - 1] || parser;
            if (tag.ns && parent.ns !== tag.ns) {
              Object.keys(tag.ns).forEach(function(p2) {
                emitNode(parser, "onopennamespace", {
                  prefix: p2,
                  uri: tag.ns[p2]
                });
              });
            }
            for (var i2 = 0, l2 = parser.attribList.length; i2 < l2; i2++) {
              var nv = parser.attribList[i2];
              var name = nv[0];
              var value = nv[1];
              var qualName = qname(name, true);
              var prefix = qualName.prefix;
              var local = qualName.local;
              var uri = prefix === "" ? "" : tag.ns[prefix] || "";
              var a2 = {
                name,
                value,
                prefix,
                local,
                uri
              };
              if (prefix && prefix !== "xmlns" && !uri) {
                strictFail(parser, "Unbound namespace prefix: " + JSON.stringify(prefix));
                a2.uri = prefix;
              }
              parser.tag.attributes[name] = a2;
              emitNode(parser, "onattribute", a2);
            }
            parser.attribList.length = 0;
          }
          parser.tag.isSelfClosing = !!selfClosing;
          parser.sawRoot = true;
          parser.tags.push(parser.tag);
          emitNode(parser, "onopentag", parser.tag);
          if (!selfClosing) {
            if (!parser.noscript && parser.tagName.toLowerCase() === "script") {
              parser.state = S2.SCRIPT;
            } else {
              parser.state = S2.TEXT;
            }
            parser.tag = null;
            parser.tagName = "";
          }
          parser.attribName = parser.attribValue = "";
          parser.attribList.length = 0;
        }
        function closeTag(parser) {
          if (!parser.tagName) {
            strictFail(parser, "Weird empty close tag.");
            parser.textNode += "</>";
            parser.state = S2.TEXT;
            return;
          }
          if (parser.script) {
            if (parser.tagName !== "script") {
              parser.script += "</" + parser.tagName + ">";
              parser.tagName = "";
              parser.state = S2.SCRIPT;
              return;
            }
            emitNode(parser, "onscript", parser.script);
            parser.script = "";
          }
          var t2 = parser.tags.length;
          var tagName = parser.tagName;
          if (!parser.strict) {
            tagName = tagName[parser.looseCase]();
          }
          var closeTo = tagName;
          while (t2--) {
            var close = parser.tags[t2];
            if (close.name !== closeTo) {
              strictFail(parser, "Unexpected close tag");
            } else {
              break;
            }
          }
          if (t2 < 0) {
            strictFail(parser, "Unmatched closing tag: " + parser.tagName);
            parser.textNode += "</" + parser.tagName + ">";
            parser.state = S2.TEXT;
            return;
          }
          parser.tagName = tagName;
          var s3 = parser.tags.length;
          while (s3-- > t2) {
            var tag = parser.tag = parser.tags.pop();
            parser.tagName = parser.tag.name;
            emitNode(parser, "onclosetag", parser.tagName);
            var x2 = {};
            for (var i2 in tag.ns) {
              x2[i2] = tag.ns[i2];
            }
            var parent = parser.tags[parser.tags.length - 1] || parser;
            if (parser.opt.xmlns && tag.ns !== parent.ns) {
              Object.keys(tag.ns).forEach(function(p2) {
                var n2 = tag.ns[p2];
                emitNode(parser, "onclosenamespace", { prefix: p2, uri: n2 });
              });
            }
          }
          if (t2 === 0) parser.closedRoot = true;
          parser.tagName = parser.attribValue = parser.attribName = "";
          parser.attribList.length = 0;
          parser.state = S2.TEXT;
        }
        function parseEntity(parser) {
          var entity = parser.entity;
          var entityLC = entity.toLowerCase();
          var num;
          var numStr = "";
          if (parser.ENTITIES[entity]) {
            return parser.ENTITIES[entity];
          }
          if (parser.ENTITIES[entityLC]) {
            return parser.ENTITIES[entityLC];
          }
          entity = entityLC;
          if (entity.charAt(0) === "#") {
            if (entity.charAt(1) === "x") {
              entity = entity.slice(2);
              num = parseInt(entity, 16);
              numStr = num.toString(16);
            } else {
              entity = entity.slice(1);
              num = parseInt(entity, 10);
              numStr = num.toString(10);
            }
          }
          entity = entity.replace(/^0+/, "");
          if (isNaN(num) || numStr.toLowerCase() !== entity) {
            strictFail(parser, "Invalid character entity");
            return "&" + parser.entity + ";";
          }
          return String.fromCodePoint(num);
        }
        function beginWhiteSpace(parser, c2) {
          if (c2 === "<") {
            parser.state = S2.OPEN_WAKA;
            parser.startTagPosition = parser.position;
          } else if (!isWhitespace(c2)) {
            strictFail(parser, "Non-whitespace before first tag.");
            parser.textNode = c2;
            parser.state = S2.TEXT;
          }
        }
        function charAt(chunk, i2) {
          var result = "";
          if (i2 < chunk.length) {
            result = chunk.charAt(i2);
          }
          return result;
        }
        function write(chunk) {
          var parser = this;
          if (this.error) {
            throw this.error;
          }
          if (parser.closed) {
            return error(
              parser,
              "Cannot write after close. Assign an onready handler."
            );
          }
          if (chunk === null) {
            return end(parser);
          }
          if (typeof chunk === "object") {
            chunk = chunk.toString();
          }
          var i2 = 0;
          var c2 = "";
          while (true) {
            c2 = charAt(chunk, i2++);
            parser.c = c2;
            if (!c2) {
              break;
            }
            if (parser.trackPosition) {
              parser.position++;
              if (c2 === "\n") {
                parser.line++;
                parser.column = 0;
              } else {
                parser.column++;
              }
            }
            switch (parser.state) {
              case S2.BEGIN:
                parser.state = S2.BEGIN_WHITESPACE;
                if (c2 === "\uFEFF") {
                  continue;
                }
                beginWhiteSpace(parser, c2);
                continue;
              case S2.BEGIN_WHITESPACE:
                beginWhiteSpace(parser, c2);
                continue;
              case S2.TEXT:
                if (parser.sawRoot && !parser.closedRoot) {
                  var starti = i2 - 1;
                  while (c2 && c2 !== "<" && c2 !== "&") {
                    c2 = charAt(chunk, i2++);
                    if (c2 && parser.trackPosition) {
                      parser.position++;
                      if (c2 === "\n") {
                        parser.line++;
                        parser.column = 0;
                      } else {
                        parser.column++;
                      }
                    }
                  }
                  parser.textNode += chunk.substring(starti, i2 - 1);
                }
                if (c2 === "<" && !(parser.sawRoot && parser.closedRoot && !parser.strict)) {
                  parser.state = S2.OPEN_WAKA;
                  parser.startTagPosition = parser.position;
                } else {
                  if (!isWhitespace(c2) && (!parser.sawRoot || parser.closedRoot)) {
                    strictFail(parser, "Text data outside of root node.");
                  }
                  if (c2 === "&") {
                    parser.state = S2.TEXT_ENTITY;
                  } else {
                    parser.textNode += c2;
                  }
                }
                continue;
              case S2.SCRIPT:
                if (c2 === "<") {
                  parser.state = S2.SCRIPT_ENDING;
                } else {
                  parser.script += c2;
                }
                continue;
              case S2.SCRIPT_ENDING:
                if (c2 === "/") {
                  parser.state = S2.CLOSE_TAG;
                } else {
                  parser.script += "<" + c2;
                  parser.state = S2.SCRIPT;
                }
                continue;
              case S2.OPEN_WAKA:
                if (c2 === "!") {
                  parser.state = S2.SGML_DECL;
                  parser.sgmlDecl = "";
                } else if (isWhitespace(c2)) ;
                else if (isMatch(nameStart, c2)) {
                  parser.state = S2.OPEN_TAG;
                  parser.tagName = c2;
                } else if (c2 === "/") {
                  parser.state = S2.CLOSE_TAG;
                  parser.tagName = "";
                } else if (c2 === "?") {
                  parser.state = S2.PROC_INST;
                  parser.procInstName = parser.procInstBody = "";
                } else {
                  strictFail(parser, "Unencoded <");
                  if (parser.startTagPosition + 1 < parser.position) {
                    var pad = parser.position - parser.startTagPosition;
                    c2 = new Array(pad).join(" ") + c2;
                  }
                  parser.textNode += "<" + c2;
                  parser.state = S2.TEXT;
                }
                continue;
              case S2.SGML_DECL:
                if (parser.sgmlDecl + c2 === "--") {
                  parser.state = S2.COMMENT;
                  parser.comment = "";
                  parser.sgmlDecl = "";
                  continue;
                }
                if (parser.doctype && parser.doctype !== true && parser.sgmlDecl) {
                  parser.state = S2.DOCTYPE_DTD;
                  parser.doctype += "<!" + parser.sgmlDecl + c2;
                  parser.sgmlDecl = "";
                } else if ((parser.sgmlDecl + c2).toUpperCase() === CDATA) {
                  emitNode(parser, "onopencdata");
                  parser.state = S2.CDATA;
                  parser.sgmlDecl = "";
                  parser.cdata = "";
                } else if ((parser.sgmlDecl + c2).toUpperCase() === DOCTYPE) {
                  parser.state = S2.DOCTYPE;
                  if (parser.doctype || parser.sawRoot) {
                    strictFail(
                      parser,
                      "Inappropriately located doctype declaration"
                    );
                  }
                  parser.doctype = "";
                  parser.sgmlDecl = "";
                } else if (c2 === ">") {
                  emitNode(parser, "onsgmldeclaration", parser.sgmlDecl);
                  parser.sgmlDecl = "";
                  parser.state = S2.TEXT;
                } else if (isQuote(c2)) {
                  parser.state = S2.SGML_DECL_QUOTED;
                  parser.sgmlDecl += c2;
                } else {
                  parser.sgmlDecl += c2;
                }
                continue;
              case S2.SGML_DECL_QUOTED:
                if (c2 === parser.q) {
                  parser.state = S2.SGML_DECL;
                  parser.q = "";
                }
                parser.sgmlDecl += c2;
                continue;
              case S2.DOCTYPE:
                if (c2 === ">") {
                  parser.state = S2.TEXT;
                  emitNode(parser, "ondoctype", parser.doctype);
                  parser.doctype = true;
                } else {
                  parser.doctype += c2;
                  if (c2 === "[") {
                    parser.state = S2.DOCTYPE_DTD;
                  } else if (isQuote(c2)) {
                    parser.state = S2.DOCTYPE_QUOTED;
                    parser.q = c2;
                  }
                }
                continue;
              case S2.DOCTYPE_QUOTED:
                parser.doctype += c2;
                if (c2 === parser.q) {
                  parser.q = "";
                  parser.state = S2.DOCTYPE;
                }
                continue;
              case S2.DOCTYPE_DTD:
                if (c2 === "]") {
                  parser.doctype += c2;
                  parser.state = S2.DOCTYPE;
                } else if (c2 === "<") {
                  parser.state = S2.OPEN_WAKA;
                  parser.startTagPosition = parser.position;
                } else if (isQuote(c2)) {
                  parser.doctype += c2;
                  parser.state = S2.DOCTYPE_DTD_QUOTED;
                  parser.q = c2;
                } else {
                  parser.doctype += c2;
                }
                continue;
              case S2.DOCTYPE_DTD_QUOTED:
                parser.doctype += c2;
                if (c2 === parser.q) {
                  parser.state = S2.DOCTYPE_DTD;
                  parser.q = "";
                }
                continue;
              case S2.COMMENT:
                if (c2 === "-") {
                  parser.state = S2.COMMENT_ENDING;
                } else {
                  parser.comment += c2;
                }
                continue;
              case S2.COMMENT_ENDING:
                if (c2 === "-") {
                  parser.state = S2.COMMENT_ENDED;
                  parser.comment = textopts(parser.opt, parser.comment);
                  if (parser.comment) {
                    emitNode(parser, "oncomment", parser.comment);
                  }
                  parser.comment = "";
                } else {
                  parser.comment += "-" + c2;
                  parser.state = S2.COMMENT;
                }
                continue;
              case S2.COMMENT_ENDED:
                if (c2 !== ">") {
                  strictFail(parser, "Malformed comment");
                  parser.comment += "--" + c2;
                  parser.state = S2.COMMENT;
                } else if (parser.doctype && parser.doctype !== true) {
                  parser.state = S2.DOCTYPE_DTD;
                } else {
                  parser.state = S2.TEXT;
                }
                continue;
              case S2.CDATA:
                if (c2 === "]") {
                  parser.state = S2.CDATA_ENDING;
                } else {
                  parser.cdata += c2;
                }
                continue;
              case S2.CDATA_ENDING:
                if (c2 === "]") {
                  parser.state = S2.CDATA_ENDING_2;
                } else {
                  parser.cdata += "]" + c2;
                  parser.state = S2.CDATA;
                }
                continue;
              case S2.CDATA_ENDING_2:
                if (c2 === ">") {
                  if (parser.cdata) {
                    emitNode(parser, "oncdata", parser.cdata);
                  }
                  emitNode(parser, "onclosecdata");
                  parser.cdata = "";
                  parser.state = S2.TEXT;
                } else if (c2 === "]") {
                  parser.cdata += "]";
                } else {
                  parser.cdata += "]]" + c2;
                  parser.state = S2.CDATA;
                }
                continue;
              case S2.PROC_INST:
                if (c2 === "?") {
                  parser.state = S2.PROC_INST_ENDING;
                } else if (isWhitespace(c2)) {
                  parser.state = S2.PROC_INST_BODY;
                } else {
                  parser.procInstName += c2;
                }
                continue;
              case S2.PROC_INST_BODY:
                if (!parser.procInstBody && isWhitespace(c2)) {
                  continue;
                } else if (c2 === "?") {
                  parser.state = S2.PROC_INST_ENDING;
                } else {
                  parser.procInstBody += c2;
                }
                continue;
              case S2.PROC_INST_ENDING:
                if (c2 === ">") {
                  emitNode(parser, "onprocessinginstruction", {
                    name: parser.procInstName,
                    body: parser.procInstBody
                  });
                  parser.procInstName = parser.procInstBody = "";
                  parser.state = S2.TEXT;
                } else {
                  parser.procInstBody += "?" + c2;
                  parser.state = S2.PROC_INST_BODY;
                }
                continue;
              case S2.OPEN_TAG:
                if (isMatch(nameBody, c2)) {
                  parser.tagName += c2;
                } else {
                  newTag(parser);
                  if (c2 === ">") {
                    openTag(parser);
                  } else if (c2 === "/") {
                    parser.state = S2.OPEN_TAG_SLASH;
                  } else {
                    if (!isWhitespace(c2)) {
                      strictFail(parser, "Invalid character in tag name");
                    }
                    parser.state = S2.ATTRIB;
                  }
                }
                continue;
              case S2.OPEN_TAG_SLASH:
                if (c2 === ">") {
                  openTag(parser, true);
                  closeTag(parser);
                } else {
                  strictFail(parser, "Forward-slash in opening tag not followed by >");
                  parser.state = S2.ATTRIB;
                }
                continue;
              case S2.ATTRIB:
                if (isWhitespace(c2)) {
                  continue;
                } else if (c2 === ">") {
                  openTag(parser);
                } else if (c2 === "/") {
                  parser.state = S2.OPEN_TAG_SLASH;
                } else if (isMatch(nameStart, c2)) {
                  parser.attribName = c2;
                  parser.attribValue = "";
                  parser.state = S2.ATTRIB_NAME;
                } else {
                  strictFail(parser, "Invalid attribute name");
                }
                continue;
              case S2.ATTRIB_NAME:
                if (c2 === "=") {
                  parser.state = S2.ATTRIB_VALUE;
                } else if (c2 === ">") {
                  strictFail(parser, "Attribute without value");
                  parser.attribValue = parser.attribName;
                  attrib(parser);
                  openTag(parser);
                } else if (isWhitespace(c2)) {
                  parser.state = S2.ATTRIB_NAME_SAW_WHITE;
                } else if (isMatch(nameBody, c2)) {
                  parser.attribName += c2;
                } else {
                  strictFail(parser, "Invalid attribute name");
                }
                continue;
              case S2.ATTRIB_NAME_SAW_WHITE:
                if (c2 === "=") {
                  parser.state = S2.ATTRIB_VALUE;
                } else if (isWhitespace(c2)) {
                  continue;
                } else {
                  strictFail(parser, "Attribute without value");
                  parser.tag.attributes[parser.attribName] = "";
                  parser.attribValue = "";
                  emitNode(parser, "onattribute", {
                    name: parser.attribName,
                    value: ""
                  });
                  parser.attribName = "";
                  if (c2 === ">") {
                    openTag(parser);
                  } else if (isMatch(nameStart, c2)) {
                    parser.attribName = c2;
                    parser.state = S2.ATTRIB_NAME;
                  } else {
                    strictFail(parser, "Invalid attribute name");
                    parser.state = S2.ATTRIB;
                  }
                }
                continue;
              case S2.ATTRIB_VALUE:
                if (isWhitespace(c2)) {
                  continue;
                } else if (isQuote(c2)) {
                  parser.q = c2;
                  parser.state = S2.ATTRIB_VALUE_QUOTED;
                } else {
                  if (!parser.opt.unquotedAttributeValues) {
                    error(parser, "Unquoted attribute value");
                  }
                  parser.state = S2.ATTRIB_VALUE_UNQUOTED;
                  parser.attribValue = c2;
                }
                continue;
              case S2.ATTRIB_VALUE_QUOTED:
                if (c2 !== parser.q) {
                  if (c2 === "&") {
                    parser.state = S2.ATTRIB_VALUE_ENTITY_Q;
                  } else {
                    parser.attribValue += c2;
                  }
                  continue;
                }
                attrib(parser);
                parser.q = "";
                parser.state = S2.ATTRIB_VALUE_CLOSED;
                continue;
              case S2.ATTRIB_VALUE_CLOSED:
                if (isWhitespace(c2)) {
                  parser.state = S2.ATTRIB;
                } else if (c2 === ">") {
                  openTag(parser);
                } else if (c2 === "/") {
                  parser.state = S2.OPEN_TAG_SLASH;
                } else if (isMatch(nameStart, c2)) {
                  strictFail(parser, "No whitespace between attributes");
                  parser.attribName = c2;
                  parser.attribValue = "";
                  parser.state = S2.ATTRIB_NAME;
                } else {
                  strictFail(parser, "Invalid attribute name");
                }
                continue;
              case S2.ATTRIB_VALUE_UNQUOTED:
                if (!isAttribEnd(c2)) {
                  if (c2 === "&") {
                    parser.state = S2.ATTRIB_VALUE_ENTITY_U;
                  } else {
                    parser.attribValue += c2;
                  }
                  continue;
                }
                attrib(parser);
                if (c2 === ">") {
                  openTag(parser);
                } else {
                  parser.state = S2.ATTRIB;
                }
                continue;
              case S2.CLOSE_TAG:
                if (!parser.tagName) {
                  if (isWhitespace(c2)) {
                    continue;
                  } else if (notMatch(nameStart, c2)) {
                    if (parser.script) {
                      parser.script += "</" + c2;
                      parser.state = S2.SCRIPT;
                    } else {
                      strictFail(parser, "Invalid tagname in closing tag.");
                    }
                  } else {
                    parser.tagName = c2;
                  }
                } else if (c2 === ">") {
                  closeTag(parser);
                } else if (isMatch(nameBody, c2)) {
                  parser.tagName += c2;
                } else if (parser.script) {
                  parser.script += "</" + parser.tagName;
                  parser.tagName = "";
                  parser.state = S2.SCRIPT;
                } else {
                  if (!isWhitespace(c2)) {
                    strictFail(parser, "Invalid tagname in closing tag");
                  }
                  parser.state = S2.CLOSE_TAG_SAW_WHITE;
                }
                continue;
              case S2.CLOSE_TAG_SAW_WHITE:
                if (isWhitespace(c2)) {
                  continue;
                }
                if (c2 === ">") {
                  closeTag(parser);
                } else {
                  strictFail(parser, "Invalid characters in closing tag");
                }
                continue;
              case S2.TEXT_ENTITY:
              case S2.ATTRIB_VALUE_ENTITY_Q:
              case S2.ATTRIB_VALUE_ENTITY_U:
                var returnState;
                var buffer;
                switch (parser.state) {
                  case S2.TEXT_ENTITY:
                    returnState = S2.TEXT;
                    buffer = "textNode";
                    break;
                  case S2.ATTRIB_VALUE_ENTITY_Q:
                    returnState = S2.ATTRIB_VALUE_QUOTED;
                    buffer = "attribValue";
                    break;
                  case S2.ATTRIB_VALUE_ENTITY_U:
                    returnState = S2.ATTRIB_VALUE_UNQUOTED;
                    buffer = "attribValue";
                    break;
                }
                if (c2 === ";") {
                  var parsedEntity = parseEntity(parser);
                  if (parser.opt.unparsedEntities && !Object.values(sax2.XML_ENTITIES).includes(parsedEntity)) {
                    parser.entity = "";
                    parser.state = returnState;
                    parser.write(parsedEntity);
                  } else {
                    parser[buffer] += parsedEntity;
                    parser.entity = "";
                    parser.state = returnState;
                  }
                } else if (isMatch(parser.entity.length ? entityBody : entityStart, c2)) {
                  parser.entity += c2;
                } else {
                  strictFail(parser, "Invalid character in entity name");
                  parser[buffer] += "&" + parser.entity + c2;
                  parser.entity = "";
                  parser.state = returnState;
                }
                continue;
              default: {
                throw new Error(parser, "Unknown state: " + parser.state);
              }
            }
          }
          if (parser.position >= parser.bufferCheckPosition) {
            checkBufferLength(parser);
          }
          return parser;
        }
        if (!String.fromCodePoint) {
          (function() {
            var stringFromCharCode = String.fromCharCode;
            var floor = Math.floor;
            var fromCodePoint = function() {
              var MAX_SIZE = 16384;
              var codeUnits = [];
              var highSurrogate;
              var lowSurrogate;
              var index = -1;
              var length = arguments.length;
              if (!length) {
                return "";
              }
              var result = "";
              while (++index < length) {
                var codePoint = Number(arguments[index]);
                if (!isFinite(codePoint) || // `NaN`, `+Infinity`, or `-Infinity`
                codePoint < 0 || // not a valid Unicode code point
                codePoint > 1114111 || // not a valid Unicode code point
                floor(codePoint) !== codePoint) {
                  throw RangeError("Invalid code point: " + codePoint);
                }
                if (codePoint <= 65535) {
                  codeUnits.push(codePoint);
                } else {
                  codePoint -= 65536;
                  highSurrogate = (codePoint >> 10) + 55296;
                  lowSurrogate = codePoint % 1024 + 56320;
                  codeUnits.push(highSurrogate, lowSurrogate);
                }
                if (index + 1 === length || codeUnits.length > MAX_SIZE) {
                  result += stringFromCharCode.apply(null, codeUnits);
                  codeUnits.length = 0;
                }
              }
              return result;
            };
            if (Object.defineProperty) {
              Object.defineProperty(String, "fromCodePoint", {
                value: fromCodePoint,
                configurable: true,
                writable: true
              });
            } else {
              String.fromCodePoint = fromCodePoint;
            }
          })();
        }
      })(exports);
    })(sax$1);
    return sax$1;
  }
  var saxExports = requireSax();

  // node_modules/axios/lib/helpers/bind.js
  function bind(fn2, thisArg) {
    return function wrap() {
      return fn2.apply(thisArg, arguments);
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
    } catch (e3) {
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
  var G2 = getGlobal3();
  var FormDataCtor = typeof G2.FormData !== "undefined" ? G2.FormData : void 0;
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
  function forEach(obj, fn2, { allOwnKeys = false } = {}) {
    if (obj === null || typeof obj === "undefined") {
      return;
    }
    let i2;
    let l2;
    if (typeof obj !== "object") {
      obj = [obj];
    }
    if (isArray(obj)) {
      for (i2 = 0, l2 = obj.length; i2 < l2; i2++) {
        fn2.call(null, obj[i2], i2, obj);
      }
    } else {
      if (isBuffer(obj)) {
        return;
      }
      const keys = allOwnKeys ? Object.getOwnPropertyNames(obj) : Object.keys(obj);
      const len = keys.length;
      let key;
      for (i2 = 0; i2 < len; i2++) {
        key = keys[i2];
        fn2.call(null, obj[key], key, obj);
      }
    }
  }
  function findKey(obj, key) {
    if (isBuffer(obj)) {
      return null;
    }
    key = key.toLowerCase();
    const keys = Object.keys(obj);
    let i2 = keys.length;
    let _key;
    while (i2-- > 0) {
      _key = keys[i2];
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
    for (let i2 = 0, l2 = objs.length; i2 < l2; i2++) {
      const source = objs[i2];
      if (!source || isBuffer(source)) {
        continue;
      }
      forEach(source, assignValue);
      if (typeof source !== "object" || isArray(source)) {
        continue;
      }
      const symbols = Object.getOwnPropertySymbols(source);
      for (let j2 = 0; j2 < symbols.length; j2++) {
        const symbol = symbols[j2];
        if (propertyIsEnumerable.call(source, symbol)) {
          assignValue(source[symbol], symbol);
        }
      }
    }
    return result;
  }
  var extend = (a2, b2, thisArg, { allOwnKeys } = {}) => {
    forEach(
      b2,
      (val, key) => {
        if (thisArg && isFunction(val)) {
          Object.defineProperty(a2, key, {
            // Null-proto descriptor so a polluted Object.prototype.get cannot
            // hijack defineProperty's accessor-vs-data resolution.
            __proto__: null,
            value: bind(val, thisArg),
            writable: true,
            enumerable: true,
            configurable: true
          });
        } else {
          Object.defineProperty(a2, key, {
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
    return a2;
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
    let i2;
    let prop;
    const merged = {};
    destObj = destObj || {};
    if (sourceObj == null) return destObj;
    do {
      props = Object.getOwnPropertyNames(sourceObj);
      i2 = props.length;
      while (i2-- > 0) {
        prop = props[i2];
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
    let i2 = thing.length;
    if (!isNumber(i2)) return null;
    const arr = new Array(i2);
    while (i2-- > 0) {
      arr[i2] = thing[i2];
    }
    return arr;
  };
  var isTypedArray = /* @__PURE__ */ ((TypedArray) => {
    return (thing) => {
      return TypedArray && thing instanceof TypedArray;
    };
  })(typeof Uint8Array !== "undefined" && getPrototypeOf2(Uint8Array));
  var forEachEntry = (obj, fn2) => {
    const generator = obj && obj[iterator];
    const _iterator = generator.call(obj);
    let result;
    while ((result = _iterator.next()) && !result.done) {
      const pair = result.value;
      fn2.call(obj, pair[0], pair[1]);
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
    return str.toLowerCase().replace(/[-_\s]([a-z\d])(\w*)/g, function replacer(m2, p1, p2) {
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
    const define2 = (arr) => {
      arr.forEach((value) => {
        obj[value] = true;
      });
    };
    isArray(arrayOrString) ? define2(arrayOrString) : define2(String(arrayOrString).split(delimiter));
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
    let i2;
    rawHeaders && rawHeaders.split("\n").forEach(function parser(line) {
      i2 = line.indexOf(":");
      key = line.substring(0, i2).trim().toLowerCase();
      val = line.substring(i2 + 1).trim();
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
    for (let i2 = 1; i2 < last; i2++) {
      const code = value.charCodeAt(i2);
      if (code === 34) {
        return value;
      }
      if (code === 92) {
        i2 += 1;
        if (i2 >= last) {
          return value;
        }
      }
      decoded += value[i2];
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
    for (let i2 = 0; i2 < str.length; i2++) {
      const code = str.charCodeAt(i2);
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
        parseParameter(i2);
        start = i2 + 1;
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
    return header.trim().toLowerCase().replace(/([a-z\d])(\w*)/g, (w2, char, str) => {
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
      let i2 = keys.length;
      let deleted = false;
      while (i2--) {
        const key = keys[i2];
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
    const lowerKeys = new Set(redactKeys.map((k2) => String(k2).toLowerCase()));
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
        source.forEach((v2, i2) => {
          const reducedValue = visit(v2);
          if (!utils_default.isUndefined(reducedValue)) {
            result[i2] = reducedValue;
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
    return path.concat(key).map(function each(token, i2) {
      token = removeBrackets(token);
      return !dots && i2 ? "[" + token + "]" : token;
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
    forEach(fn2) {
      const internals = this[$internals2];
      syncHandlerEntries(this, internals);
      internals.iterationDepth++;
      try {
        utils_default.forEach(this.handlers, function forEachHandler(h2) {
          if (h2 !== null) {
            fn2(h2);
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
    let i2;
    const len = keys.length;
    let key;
    for (i2 = 0; i2 < len; i2++) {
      key = keys[i2];
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
      } catch (e3) {
        if (e3.name !== "SyntaxError") {
          throw e3;
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
          } catch (e3) {
            if (strictJSONParsing) {
              if (e3.name === "SyntaxError") {
                throw AxiosError_default.from(e3, AxiosError_default.ERR_BAD_RESPONSE, this, null, own(this, "response"));
              }
              throw e3;
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
    utils_default.forEach(fns, function transform(fn2) {
      data = fn2.call(config, data, headers.normalize(), response ? response.status : void 0);
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
      let i2 = tail;
      let bytesCount = 0;
      while (i2 !== head) {
        bytesCount += bytes[i2++];
        i2 = i2 % samplesCount;
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
  function throttle(fn2, freq) {
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
      fn2(...args);
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
    return throttle_default((e3) => {
      if (!e3 || !utils_default.isNumber(e3.loaded)) {
        return;
      }
      const rawLoaded = e3.loaded;
      const total = e3.lengthComputable ? e3.total : void 0;
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
        event: e3,
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
  var asyncDecorator = (fn2, scheduler = utils_default.asap) => (...args) => scheduler(() => fn2(...args));

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
        for (let i2 = 0; i2 < cookies.length; i2++) {
          const cookie = cookies[i2].replace(/^\s+/, "");
          const eq = cookie.indexOf("=");
          if (eq !== -1 && cookie.slice(0, eq) === name) {
            try {
              return decodeURIComponent(cookie.slice(eq + 1));
            } catch (e3) {
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
    function mergeDeepProperties(a2, b2, prop, caseless) {
      if (!utils_default.isUndefined(b2)) {
        return getMergedValue(a2, b2, prop, caseless);
      } else if (!utils_default.isUndefined(a2)) {
        return getMergedValue(void 0, a2, prop, caseless);
      }
    }
    function valueFromConfig2(a2, b2) {
      if (!utils_default.isUndefined(b2)) {
        return getMergedValue(void 0, b2);
      }
    }
    function defaultToConfig2(a2, b2) {
      if (!utils_default.isUndefined(b2)) {
        return getMergedValue(void 0, b2);
      } else if (!utils_default.isUndefined(a2)) {
        return getMergedValue(void 0, a2);
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
    function mergeDirectKeys(a2, b2, prop) {
      if (utils_default.hasOwnProp(config2, prop)) {
        return getMergedValue(a2, b2);
      } else if (utils_default.hasOwnProp(config1, prop)) {
        return getMergedValue(void 0, a2);
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
      headers: (a2, b2, prop) => mergeDeepProperties(headersToObject(a2), headersToObject(b2), prop, true)
    };
    utils_default.forEach(ownEnumerableKeys({ ...config1, ...config2 }), function computeConfigValue(prop) {
      if (prop === "__proto__" || prop === "constructor" || prop === "prototype") return;
      const merge2 = utils_default.hasOwnProp(mergeMap, prop) ? mergeMap[prop] : mergeDeepProperties;
      const a2 = utils_default.hasOwnProp(config1, prop) ? config1[prop] : void 0;
      const b2 = utils_default.hasOwnProp(config2, prop) ? config2[prop] : void 0;
      const configValue = merge2(a2, b2, prop);
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
    (_2, hex) => String.fromCharCode(parseInt(hex, 16))
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
      } catch (e3) {
        throw AxiosError_default.from(e3, AxiosError_default.ERR_BAD_OPTION_VALUE, config);
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
    let _onFinish = (e3) => {
      if (!done) {
        done = true;
        onFinish && onFinish(e3);
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
  var isPercentEncodedByte = (str, i2, len) => i2 + 2 < len && isHexDigit(str.charCodeAt(i2 + 1)) && isHexDigit(str.charCodeAt(i2 + 2));
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
    for (let i2 = 0; i2 < len; i2++) {
      let code = body.charCodeAt(i2);
      if (code === 37 && isPercentEncodedByte(body, i2, len)) {
        code = hexValue(body.charCodeAt(i2 + 1)) * 16 + hexValue(body.charCodeAt(i2 + 2));
        i2 += 2;
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
    for (let i2 = 0, len = body.length; i2 < len; i2++) {
      const c2 = body.charCodeAt(i2);
      if (c2 === 37 && isPercentEncodedByte(body, i2, len)) {
        bytes += 1;
        i2 += 2;
      } else if (c2 < 128) {
        bytes += 1;
      } else if (c2 < 2048) {
        bytes += 2;
      } else if (c2 >= 55296 && c2 <= 56319 && i2 + 1 < len) {
        const next = body.charCodeAt(i2 + 1);
        if (next >= 56320 && next <= 57343) {
          bytes += 4;
          i2++;
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
    (_2, hex) => String.fromCharCode(parseInt(hex, 16))
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
  var test = (fn2, ...args) => {
    try {
      return !!fn2(...args);
    } catch (e3) {
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
    let len = seeds.length, i2 = len, seed, target, map = seedCache;
    while (i2--) {
      seed = seeds[i2];
      target = map.get(seed);
      target === void 0 && map.set(seed, target = i2 ? /* @__PURE__ */ new Map() : factory(env));
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
  utils_default.forEach(knownAdapters, (fn2, value) => {
    if (fn2) {
      try {
        Object.defineProperty(fn2, "name", { __proto__: null, value });
      } catch (e3) {
      }
      Object.defineProperty(fn2, "adapterName", { __proto__: null, value });
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
    for (let i2 = 0; i2 < length; i2++) {
      nameOrAdapter = adapters[i2];
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
      rejectedReasons[id || "#" + i2] = adapter2;
    }
    if (!adapter2) {
      const reasons = Object.entries(rejectedReasons).map(
        ([id, state]) => `adapter ${id} ` + (state === false ? "is not supported by the environment" : "is not available in the build")
      );
      let s2 = length ? reasons.length > 1 ? "since :\n" + reasons.map(renderReason).join("\n") : " " + renderReason(reasons[0]) : "as no adapter specified";
      throw new AxiosError_default(
        `There is no suitable adapter to dispatch the request ` + s2,
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
  ["object", "boolean", "number", "function", "string", "symbol"].forEach((type, i2) => {
    validators[type] = function validator(thing) {
      return typeof thing === type || "a" + (i2 < 1 ? "n " : " ") + type;
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
    let i2 = keys.length;
    while (i2-- > 0) {
      const opt = keys[i2];
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
          } catch (e3) {
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
      let i2 = 0;
      let len;
      if (!synchronousRequestInterceptors) {
        const chain = [dispatchRequest.bind(this), void 0];
        chain.unshift(...requestInterceptorChain);
        chain.push(...responseInterceptorChain);
        len = chain.length;
        promise = Promise.resolve(config);
        while (i2 < len) {
          promise = promise.then(chain[i2++], chain[i2++]);
        }
        return promise;
      }
      len = requestInterceptorChain.length;
      let newConfig = config;
      while (i2 < len) {
        const onFulfilled = requestInterceptorChain[i2++];
        const onRejected = requestInterceptorChain[i2++];
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
      i2 = 0;
      len = responseInterceptorChain.length;
      while (i2 < len) {
        promise = promise.then(responseInterceptorChain[i2++], responseInterceptorChain[i2++]);
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
        let i2 = token._listeners.length;
        while (i2-- > 0) {
          token._listeners[i2](cancel);
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
      const token = new _CancelToken(function executor(c2) {
        cancel = c2;
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
  cancelableClient.interceptors.response.use((r2) => r2, onCsrfTokenError(cancelableClient));
  cancelableClient.interceptors.response.use((r2) => r2, onMaintenanceModeError(cancelableClient));
  cancelableClient.interceptors.response.use((r2) => r2, onNotLoggedInError);
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
  registerFileAction(new FileAction({
    id: "shake-tags",
    displayName: () => translate("shake_tags", "\u30BF\u30B0\u3092\u7DE8\u96C6"),
    iconSvgInline: () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M21.41 11.58l-9-9A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 .59 1.42l9 9A2 2 0 0 0 13 22a2 2 0 0 0 1.41-.59l7-7A2 2 0 0 0 21.41 11.58zM6.5 8A1.5 1.5 0 1 1 8 6.5 1.5 1.5 0 0 1 6.5 8z"/></svg>',
    enabled: (nodes) => nodes.length === 1 && nodes[0].type === FileType.File && (nodes[0].extension || "").toLowerCase() === "mp3",
    exec: (node) => openEditor(node.fileid),
    order: 27
  }));
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
@nextcloud/files/dist/index.mjs:
@nextcloud/files/dist/index.mjs:
@nextcloud/files/dist/index.mjs:
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
@nextcloud/sharing/dist/public.js:
  (*!
   * SPDX-FileCopyrightText: 2024 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

webdav/dist/web/index.js:
  (*! For license information please see index.js.LICENSE.txt *)

dompurify/dist/purify.es.mjs:
  (*! @license DOMPurify 3.4.15 | (c) Cure53 and other contributors | Released under the Apache license 2.0 and Mozilla Public License 2.0 | github.com/cure53/DOMPurify/blob/3.4.15/LICENSE *)

@nextcloud/l10n/dist/chunks/translation-DoG5ZELJ.mjs:
@nextcloud/l10n/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2022 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: GPL-3.0-or-later
   *)

@nextcloud/files/dist/index.mjs:
  (*!
   * SPDX-FileCopyrightText: 2023 Nextcloud GmbH and Nextcloud contributors
   * SPDX-License-Identifier: AGPL-3.0-or-later
   *)

@nextcloud/files/dist/index.mjs:
  (*! http://mths.be/fromcodepoint v0.1.0 by @mathias *)

@nextcloud/axios/dist/client.js:
  (*!
   * SPDX-License-Identifier: GPL-3.0-or-later
   * SPDX-FileCopyrightText: 2025 Nextcloud GmbH and Nextcloud contributors
   *)
*/
