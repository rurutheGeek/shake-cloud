/* 画面。設計は docs/development/M02-touch-panel.md の「画面の設計」。 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "app.h"
#include "lvgl.h"

#define W 800
#define H 480
#define BAND_H 72
#define NAV_H 96
#define BODY_Y BAND_H
#define BODY_H (H - BAND_H - NAV_H)
#define GAP 8

#define C_BG 0x1c1f24
#define C_SURF 0x2a2e35
#define C_SURF_ON 0x3a404a
#define C_PRESSED 0x4a5260
#define C_TEXT 0xe6e6e6
#define C_MUTED 0x8a9099
#define C_WARN 0xf2b600
#define C_CRIT 0xe53935
#define C_STALE 0x5c6370

#define IDLE_HOME_MS 60000
#define DEBOUNCE_MS 300
#define BLINK_MS 10000
#define SHIFT_MS (10 * 60 * 1000)

enum page { P_OVERVIEW, P_ALERTS, P_STATUS, P_POWER, P_HOSTS, P_SETTINGS, P_COUNT };
enum kind { K_SERVICE, K_HOST, K_VM };
enum state { S_OK, S_WARN, S_CRIT, S_STALE };

static const char *PAGE_NAMES[P_COUNT] = {"概要", "警告", "死活", "電源", "ホスト", "設定"};

static const config_t *cfg;
static settings_t *settings;
static snapshot_t snap;
static unsigned snap_version;
static bool have_snap;

static lv_font_t *f20, *f24, *f28, *f36, *f56, *f96;
static lv_obj_t *root, *band, *band_icon, *band_state, *band_alert, *band_ack, *clock_label, *body, *wake;
static lv_obj_t *nav_btn[P_COUNT], *nav_badge[P_COUNT];

static enum page page = P_OVERVIEW;
static int page_offset;
static enum kind status_kind = K_SERVICE;
static uint32_t last_switch;
static bool dirty = true;
static bool dimmed;

/* 確認：起動時に出ていた警告は確認済みとする。 */
static char acked[MAX_FPS][24];
static int n_acked;
static bool acked_init;
static bool unacked;
static uint32_t blink_until;

/* ---------- 部品 ---------- */

static lv_color_t col(uint32_t c)
{
    return lv_color_hex(c);
}

static lv_obj_t *box(lv_obj_t *parent, int x, int y, int w, int h, uint32_t bg)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_bg_color(o, col(bg), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(o, 8, 0);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *text(lv_obj_t *parent, const char *s, lv_font_t *font, uint32_t color)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, s);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, col(color), 0);
    return l;
}

static bool debounced(void)
{
    return lv_tick_elaps(last_switch) < DEBOUNCE_MS;
}

static void go(enum page p)
{
    if (p != page) page_offset = 0;
    page = p;
    last_switch = lv_tick_get();
    dirty = true;
}

static void on_nav(lv_event_t *e)
{
    if (debounced()) return;
    go((enum page)(intptr_t)lv_event_get_user_data(e));
}

/* 押した瞬間に色を変え、離したときに決める（LV_EVENT_CLICKED）。 */
static lv_obj_t *button(lv_obj_t *parent, int x, int y, int w, int h, uint32_t bg, lv_event_cb_t cb, void *user)
{
    lv_obj_t *b = box(parent, x, y, w, h, bg);
    lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_bg_color(b, col(C_PRESSED), LV_STATE_PRESSED);
    if (cb) lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, user);
    return b;
}

static uint32_t state_color(enum state s)
{
    return s == S_CRIT ? C_CRIT : s == S_WARN ? C_WARN : s == S_STALE ? C_STALE : C_TEXT;
}

static const char *state_mark(enum state s)
{
    return s == S_CRIT ? "◆" : s == S_WARN ? "▲" : s == S_STALE ? "？" : "";
}

static void outline(lv_obj_t *o, enum state s)
{
    if (s != S_WARN && s != S_CRIT) return;
    lv_obj_set_style_border_color(o, col(state_color(s)), 0);
    lv_obj_set_style_border_width(o, 4, 0);
}

static void format_age(time_t since, char *out, size_t len)
{
    long d = since ? (long)difftime(time(NULL), since) : 0;
    if (d < 3600) snprintf(out, len, "%ld分", d / 60);
    else if (d < 86400) snprintf(out, len, "%ld時間", d / 3600);
    else snprintf(out, len, "%ld日", d / 86400);
}

/* ▲▼（または ◀▶）のページ送り。押せないときは灰色。 */
static void on_page_step(lv_event_t *e)
{
    if (debounced()) return;
    page_offset += (int)(intptr_t)lv_event_get_user_data(e);
    last_switch = lv_tick_get();
    dirty = true;
}

static void pager(lv_obj_t *parent, int pages)
{
    int x = W - GAP - 96, ind_h = 32, h = (BODY_H - 2 * GAP - ind_h) / 2;
    bool can_up = page_offset > 0, can_down = page_offset < pages - 1;
    lv_obj_t *up = button(parent, x, GAP, 96, h, C_SURF, can_up ? on_page_step : NULL, (void *)(intptr_t)-1);
    lv_obj_t *dn = button(parent, x, GAP + h + ind_h, 96, h, C_SURF, can_down ? on_page_step : NULL, (void *)(intptr_t)1);
    if (!can_up) lv_obj_remove_flag(up, LV_OBJ_FLAG_CLICKABLE);
    if (!can_down) lv_obj_remove_flag(dn, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_center(text(up, "▲", f36, can_up ? C_TEXT : C_STALE));
    lv_obj_center(text(dn, "▼", f36, can_down ? C_TEXT : C_STALE));
    char ind[16];
    snprintf(ind, sizeof ind, "%d/%d", page_offset + 1, pages < 1 ? 1 : pages);
    lv_obj_t *l = text(parent, ind, f20, C_MUTED);
    lv_obj_set_width(l, 96);
    lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(l, x, GAP + h + 4);
}

/* ---------- 概要 ---------- */

static int count_ok(const item_t *items, int n)
{
    int ok = 0;
    for (int i = 0; i < n; i++) ok += items[i].ok;
    return ok;
}

static void on_tile(lv_event_t *e)
{
    if (debounced()) return;
    intptr_t v = (intptr_t)lv_event_get_user_data(e);
    if (v >= 100) {
        status_kind = (enum kind)(v - 100);
        go(P_STATUS);
    } else {
        go((enum page)v);
    }
}

static void tile(int i, const char *label, const char *value, const char *sub, enum state s, intptr_t target)
{
    int w = (W - 4 * GAP) / 3, h = (BODY_H - 3 * GAP) / 2;
    int x = GAP + (i % 3) * (w + GAP), y = GAP + (i / 3) * (h + GAP);
    lv_obj_t *t = button(body, x, y, w, h, C_SURF, on_tile, (void *)target);
    outline(t, s);
    lv_obj_t *l = text(t, label, f24, C_MUTED);
    lv_obj_set_pos(l, 16, 12);
    if (s == S_WARN || s == S_CRIT) {
        lv_obj_t *m = text(t, state_mark(s), f28, state_color(s));
        lv_obj_align(m, LV_ALIGN_TOP_RIGHT, -14, 10);
    }
    lv_obj_t *v = text(t, value, f56, state_color(s));
    lv_obj_set_pos(v, 16, 44);
    if (sub && sub[0]) {
        lv_obj_t *sl = text(t, sub, f20, C_MUTED);
        lv_obj_set_pos(sl, 16, h - 34);
    }
}

static enum state ratio_state(int ok, int n, bool stale)
{
    if (stale) return S_STALE;
    return ok < n ? S_WARN : S_OK;
}

static void build_overview(void)
{
    bool st = snap.prom_stale;
    char v[32], sub[64];
    if (snap.latency_ms >= 0) snprintf(v, sizeof v, "%.0f ms", snap.latency_ms);
    else snprintf(v, sizeof v, "—");
    tile(0, "回線", v, "", st ? S_STALE : snap.latency_ms > 1000 ? S_WARN : S_OK, 100 + K_SERVICE);

    int ok = count_ok(snap.services, snap.n_services);
    snprintf(v, sizeof v, "%d/%d", ok, snap.n_services);
    tile(1, "サービス", v, "", ratio_state(ok, snap.n_services, st), 100 + K_SERVICE);

    ok = count_ok(snap.hosts, snap.n_hosts);
    snprintf(v, sizeof v, "%d/%d", ok, snap.n_hosts);
    tile(2, "ホスト", v, "", ratio_state(ok, snap.n_hosts, st), P_HOSTS);

    ok = count_ok(snap.vms, snap.n_vms);
    snprintf(v, sizeof v, "%d/%d", ok, snap.n_vms);
    tile(3, "VM", v, "", ratio_state(ok, snap.n_vms, st), 100 + K_VM);

    enum state ups = st || !snap.ups_ok ? S_STALE
                   : snap.ups_onbattery || snap.ups_lowbattery ? S_CRIT : S_OK;
    if (snap.ups_ok) snprintf(v, sizeof v, "%.0f %%", snap.ups_charge);
    else snprintf(v, sizeof v, "—");
    snprintf(sub, sizeof sub, "%s・負荷 %.0f %%", snap.ups_onbattery ? "停電中" : "商用", snap.ups_load);
    tile(4, "電源", v, snap.ups_ok ? sub : "", ups, P_POWER);

    enum state disk = snap.am_stale ? S_STALE : snap.n_disk ? S_WARN : S_OK;
    if (snap.n_disk) snprintf(v, sizeof v, "異常 %d", snap.n_disk);
    else snprintf(v, sizeof v, "正常");
    tile(5, "ディスク", v, "", disk, P_ALERTS);
}

/* ---------- 警告 ---------- */

#define ALERT_ROWS 4

static void build_alerts(void)
{
    if (snap.am_stale) {
        lv_obj_center(text(body, "？ 読めない", f36, C_STALE));
        return;
    }
    if (!snap.n_groups) {
        lv_obj_center(text(body, "警告なし", f36, C_MUTED));
        return;
    }
    int pages = (snap.n_groups + ALERT_ROWS - 1) / ALERT_ROWS;
    if (page_offset >= pages) page_offset = pages - 1;
    int row_h = (BODY_H - GAP * (ALERT_ROWS + 1)) / ALERT_ROWS;
    int w = W - 3 * GAP - 96;
    for (int r = 0; r < ALERT_ROWS; r++) {
        int i = page_offset * ALERT_ROWS + r;
        if (i >= snap.n_groups) break;
        alert_group_t *g = &snap.groups[i];
        enum state s = g->severity == 2 ? S_CRIT : S_WARN;
        lv_obj_t *row = box(body, GAP, GAP + r * (row_h + GAP), w, row_h, C_SURF);
        lv_obj_t *strip = box(row, 0, 0, 12, row_h, state_color(s));
        lv_obj_set_style_radius(strip, 4, 0);
        lv_obj_t *m = text(row, state_mark(s), f28, state_color(s));
        lv_obj_align(m, LV_ALIGN_LEFT_MID, 26, 0);
        lv_obj_t *n = text(row, g->label, f28, C_TEXT);
        lv_obj_set_pos(n, 72, 6);
        char t[96];
        if (g->count > 1) snprintf(t, sizeof t, "%s ほか %d", g->target, g->count - 1);
        else snprintf(t, sizeof t, "%s", g->target);
        lv_obj_t *tl = text(row, t, f20, C_MUTED);
        lv_obj_set_pos(tl, 72, row_h - 28);
        char age[16];
        format_age(g->since, age, sizeof age);
        lv_obj_t *al = text(row, age, f24, C_MUTED);
        lv_obj_align(al, LV_ALIGN_RIGHT_MID, -16, 0);
    }
    pager(body, pages);
}

/* ---------- 死活 ---------- */

#define STATUS_COLS 2
#define STATUS_ROWS 4

static void on_kind(lv_event_t *e)
{
    if (debounced()) return;
    status_kind = (enum kind)(intptr_t)lv_event_get_user_data(e);
    page_offset = 0;
    last_switch = lv_tick_get();
    dirty = true;
}

static void build_status(void)
{
    static const char *names[] = {"サービス", "ホスト", "VM"};
    const item_t *lists[] = {snap.services, snap.hosts, snap.vms};
    int counts[] = {snap.n_services, snap.n_hosts, snap.n_vms};
    int kh = (BODY_H - 4 * GAP) / 3;
    for (int k = 0; k < 3; k++) {
        int bad = counts[k] - count_ok(lists[k], counts[k]);
        lv_obj_t *b = button(body, GAP, GAP + k * (kh + GAP), 136, kh,
                             k == (int)status_kind ? C_SURF_ON : C_SURF, on_kind, (void *)(intptr_t)k);
        if (k == (int)status_kind) {
            lv_obj_set_style_border_side(b, LV_BORDER_SIDE_LEFT, 0);
            lv_obj_set_style_border_width(b, 6, 0);
            lv_obj_set_style_border_color(b, col(C_TEXT), 0);
        }
        lv_obj_t *l = text(b, names[k], f24, k == (int)status_kind ? C_TEXT : C_MUTED);
        lv_obj_align(l, LV_ALIGN_LEFT_MID, 14, bad ? -14 : 0);
        if (bad) {
            char s[16];
            snprintf(s, sizeof s, "▲ %d", bad);
            lv_obj_t *bl = text(b, s, f24, C_WARN);
            lv_obj_align(bl, LV_ALIGN_LEFT_MID, 14, 16);
        }
    }

    const item_t *items = lists[status_kind];
    int n = counts[status_kind];
    /* 異常を先に。 */
    static item_t sorted[MAX_ITEMS];
    int m = 0;
    for (int pass = 0; pass < 2; pass++)
        for (int i = 0; i < n; i++)
            if (items[i].ok == (pass == 1)) sorted[m++] = items[i];

    int per = STATUS_COLS * STATUS_ROWS;
    int pages = n ? (n + per - 1) / per : 1;
    if (page_offset >= pages) page_offset = pages - 1;
    int x0 = GAP + 136 + GAP, area_w = W - x0 - GAP - 96 - GAP;
    int cw = (area_w - GAP) / STATUS_COLS, ch = (BODY_H - GAP * (STATUS_ROWS + 1)) / STATUS_ROWS;
    for (int c = 0; c < per; c++) {
        int i = page_offset * per + c;
        if (i >= m) break;
        int col_i = c % STATUS_COLS, row_i = c / STATUS_COLS;
        enum state s = snap.prom_stale ? S_STALE : sorted[i].ok ? S_OK : S_WARN;
        lv_obj_t *cell = box(body, x0 + col_i * (cw + GAP), GAP + row_i * (ch + GAP), cw, ch, C_SURF);
        outline(cell, s);
        lv_obj_t *nl = text(cell, sorted[i].name, f24, s == S_OK ? C_TEXT : state_color(s));
        lv_label_set_long_mode(nl, LV_LABEL_LONG_MODE_DOTS);
        lv_obj_set_width(nl, cw - 80);
        lv_obj_align(nl, LV_ALIGN_LEFT_MID, 14, 0);
        if (s != S_OK) {
            lv_obj_t *ml = text(cell, s == S_STALE ? "？" : "▲ 停止", f24, state_color(s));
            lv_obj_align(ml, LV_ALIGN_RIGHT_MID, -12, 0);
        }
    }
    pager(body, pages);
}

/* ---------- 電源 ---------- */

static void stat_line(int y, const char *label, const char *value, uint32_t color)
{
    lv_obj_t *l = text(body, label, f24, C_MUTED);
    lv_obj_set_pos(l, 440, y + 10);
    lv_obj_t *v = text(body, value, f36, color);
    lv_obj_set_pos(v, 560, y);
}

static void build_power(void)
{
    if (!snap.ups_ok || snap.prom_stale) {
        lv_obj_center(text(body, "？ 読めない", f36, C_STALE));
        return;
    }
    enum state s = snap.ups_onbattery || snap.ups_lowbattery ? S_CRIT : S_OK;
    lv_obj_t *panel = box(body, GAP, GAP, 416, BODY_H - 2 * GAP, C_SURF);
    outline(panel, s);
    lv_obj_t *l = text(panel, "電池", f24, C_MUTED);
    lv_obj_set_pos(l, 20, 16);
    char v[32];
    snprintf(v, sizeof v, "%.0f %%", snap.ups_charge);
    lv_obj_t *big = text(panel, v, f96, state_color(s));
    lv_obj_set_pos(big, 20, 64);
    const char *st = snap.ups_lowbattery ? "◆ 電池残り少" : snap.ups_onbattery ? "◆ 停電中" : "商用電源";
    lv_obj_t *sl = text(panel, st, f36, s == S_CRIT ? C_CRIT : C_TEXT);
    lv_obj_set_pos(sl, 20, BODY_H - 2 * GAP - 64);

    snprintf(v, sizeof v, "%.0f %%", snap.ups_load);
    stat_line(32, "負荷", v, C_TEXT);
    snprintf(v, sizeof v, "%.0f 分", snap.ups_runtime / 60);
    stat_line(128, "残り", v, C_TEXT);
    snprintf(v, sizeof v, "%.0f V", snap.ups_input);
    stat_line(224, "入力", v, C_TEXT);
}

/* ---------- ホスト ---------- */

/* 値の無い行は出さず、次の行を詰める。 */
static void metric_row(lv_obj_t *card, int *row, const char *name, double v, double warn, bool percent)
{
    if (v < 0) return;
    int y = 40 + 26 * (*row)++;
    lv_obj_t *l = text(card, name, f20, C_MUTED);
    lv_obj_set_pos(l, 14, y);
    char s[16];
    uint32_t c = v >= warn ? C_WARN : C_TEXT;
    if (v < 0) snprintf(s, sizeof s, "—");
    else if (percent) snprintf(s, sizeof s, "%.0f %%", v * 100);
    else snprintf(s, sizeof s, "%.0f ℃", v);
    lv_obj_t *vl = text(card, s, f20, c);
    lv_obj_align(vl, LV_ALIGN_TOP_RIGHT, -14, y);
    if (percent && v >= 0) {
        /* 値（右寄せ、最大「100 %」）と重ならない長さにする。 */
        int bar = lv_obj_get_style_width(card, 0) - 100 - 76;
        lv_obj_t *track = box(card, 100, y + 8, bar, 8, C_BG);
        lv_obj_set_style_radius(track, 2, 0);
        int w = (int)(bar * (v > 1 ? 1 : v));
        if (w > 0) {
            lv_obj_t *bar = box(track, 0, 0, w, 8, c == C_TEXT ? C_MUTED : c);
            lv_obj_set_style_radius(bar, 2, 0);
        }
    }
}

static void build_hosts(void)
{
    int per = 6;
    int pages = snap.n_hostinfo ? (snap.n_hostinfo + per - 1) / per : 1;
    if (page_offset >= pages) page_offset = pages - 1;
    /* 2 ページ以上なら、右にページ送りの列を空ける。 */
    int area = pages > 1 ? W - GAP - 96 : W;
    int w = (area - 4 * GAP) / 3, h = (BODY_H - 3 * GAP) / 2;
    for (int c = 0; c < per; c++) {
        int i = page_offset * per + c;
        if (i >= snap.n_hostinfo) break;
        host_t *hst = &snap.hostinfo[i];
        bool hot = hst->cpu >= 0.9 || hst->mem >= 0.9 || hst->disk >= 0.85 || hst->temp >= 80;
        enum state s = snap.prom_stale ? S_STALE : !hst->up || hot ? S_WARN : S_OK;
        lv_obj_t *card = box(body, GAP + (c % 3) * (w + GAP), GAP + (c / 3) * (h + GAP), w, h, C_SURF);
        outline(card, s);
        lv_obj_t *nl = text(card, hst->name, f24, C_TEXT);
        lv_obj_set_pos(nl, 14, 6);
        if (!hst->up) {
            lv_obj_t *dl = text(card, "▲ 応答なし", f28, C_WARN);
            lv_obj_align(dl, LV_ALIGN_LEFT_MID, 14, 12);
            continue;
        }
        int row = 0;
        metric_row(card, &row, "CPU", hst->cpu, 0.9, true);
        metric_row(card, &row, "メモリ", hst->mem, 0.9, true);
        metric_row(card, &row, "ディスク", hst->disk, 0.85, true);
        metric_row(card, &row, "温度", hst->temp, 80, false);
    }
    if (pages > 1) pager(body, pages);
}

/* ---------- 設定 ---------- */

typedef struct {
    int *field;
    int value;
} choice_t;

static void apply_brightness(void)
{
    backlight_set(dimmed ? settings->dim_level : settings->brightness);
}

static void on_choice(lv_event_t *e)
{
    if (debounced()) return;
    choice_t *c = lv_event_get_user_data(e);
    *c->field = c->value;
    settings_save(settings, cfg->settings_file);
    apply_brightness();
    dirty = true;
}

static void choice_row(int row, const char *label, int *field, const int *values, const char *const *names, int n)
{
    static choice_t choices[3][4];
    int rh = (BODY_H - 4 * GAP) / 3, y = GAP + row * (rh + GAP);
    lv_obj_t *l = text(body, label, f24, C_MUTED);
    lv_obj_set_pos(l, 16, y + rh / 2 - 14);
    int bw = (W - 200 - GAP * 4) / 4;
    for (int i = 0; i < n; i++) {
        choices[row][i] = (choice_t){field, values[i]};
        bool on = *field == values[i];
        lv_obj_t *b = button(body, 200 + i * (bw + GAP), y, bw, rh, on ? C_SURF_ON : C_SURF, on_choice, &choices[row][i]);
        if (on) {
            lv_obj_set_style_border_side(b, LV_BORDER_SIDE_BOTTOM, 0);
            lv_obj_set_style_border_width(b, 6, 0);
            lv_obj_set_style_border_color(b, col(C_TEXT), 0);
        }
        lv_obj_center(text(b, names[i], f28, on ? C_TEXT : C_MUTED));
    }
}

static void build_settings(void)
{
    static const int bv[] = {25, 50, 75, 100};
    static const char *const bn[] = {"25 %", "50 %", "75 %", "100 %"};
    static const int dv[] = {60, 300, 1800, 0};
    static const char *const dn[] = {"1分", "5分", "30分", "無制限"};
    static const int lv[] = {0, 10};
    static const char *const ln[] = {"消す", "10 %"};
    choice_row(0, "明るさ", &settings->brightness, bv, bn, 4);
    choice_row(1, "暗くなるまで", &settings->dim_after, dv, dn, 4);
    choice_row(2, "暗くなったとき", &settings->dim_level, lv, ln, 2);
}

/* ---------- 帯と切り替え ---------- */

static void ack_all(void)
{
    n_acked = 0;
    for (int i = 0; i < snap.n_fps && n_acked < MAX_FPS; i++)
        snprintf(acked[n_acked++], 24, "%s", snap.fps[i]);
    unacked = false;
    blink_until = 0;
}

static void on_ack(lv_event_t *e)
{
    lv_event_stop_bubbling(e);
    if (debounced()) return;
    ack_all();
    last_switch = lv_tick_get();
}

static void on_band(lv_event_t *e)
{
    if (debounced()) return;
    go(P_ALERTS);
}

static bool is_acked(const char *fp)
{
    for (int i = 0; i < n_acked; i++)
        if (strcmp(acked[i], fp) == 0) return true;
    return false;
}

static void undim(void)
{
    dimmed = false;
    apply_brightness();
    lv_obj_add_flag(wake, LV_OBJ_FLAG_HIDDEN);
}

static void update_alert_tracking(void)
{
    if (snap.am_stale || !snap.am_seen) return;
    if (!acked_init) {
        acked_init = true;
        ack_all();
        return;
    }
    bool fresh = false, fresh_crit = false;
    for (int i = 0; i < snap.n_fps; i++)
        if (!is_acked(snap.fps[i])) {
            fresh = true;
            fresh_crit |= snap.fp_crit[i];
        }
    if (fresh && !unacked) blink_until = lv_tick_get() + BLINK_MS;
    unacked = fresh;
    if (fresh_crit && dimmed) {
        undim();
        lv_display_trigger_activity(NULL);
    }
}

static void update_band(void)
{
    enum state s;
    char state[48], alert[96] = "";
    if (!have_snap || (snap.prom_stale && snap.am_stale)) {
        s = S_STALE;
        snprintf(state, sizeof state, have_snap ? "？ 読めない" : "読み込み中");
    } else if (snap.am_stale) {
        s = S_STALE;
        snprintf(state, sizeof state, "？ 警告を読めない");
    } else if (snap.n_crit) {
        s = S_CRIT;
        snprintf(state, sizeof state, "危険 %d", snap.n_crit);
    } else if (snap.n_warn) {
        s = S_WARN;
        snprintf(state, sizeof state, "注意 %d", snap.n_warn);
    } else if (snap.prom_stale) {
        s = S_STALE;
        snprintf(state, sizeof state, "？ 値を読めない");
    } else {
        s = S_OK;
        snprintf(state, sizeof state, "異常なし");
    }
    if ((s == S_WARN || s == S_CRIT) && snap.n_groups) snprintf(alert, sizeof alert, "%s", snap.groups[0].label);

    uint32_t bg = s == S_CRIT ? C_CRIT : s == S_WARN ? C_WARN : s == S_STALE ? C_STALE : C_SURF;
    uint32_t fg = s == S_WARN ? 0x000000 : s == S_CRIT ? 0xffffff : C_TEXT;
    if (blink_until && lv_tick_get() < blink_until && (lv_tick_get() / 500) % 2) bg = C_BG, fg = C_TEXT;

    /* 変わったときだけ描き直す（毎回書き換えると帯を描き続けて CPU を使う）。 */
    static char last[256];
    char sig[256];
    snprintf(sig, sizeof sig, "%d|%s|%s|%x|%x|%d|%d|%u", (int)s, state, alert, bg, fg, unacked, have_snap, snap_version);
    if (strcmp(sig, last) == 0) return;
    snprintf(last, sizeof last, "%s", sig);
    lv_obj_set_style_bg_color(band, col(bg), 0);
    lv_label_set_text(band_icon, state_mark(s == S_STALE ? S_OK : s));
    lv_obj_set_style_text_color(band_icon, col(fg), 0);
    lv_label_set_text(band_state, state);
    lv_obj_set_style_text_color(band_state, col(fg), 0);
    lv_label_set_text(band_alert, alert);
    lv_obj_set_style_text_color(band_alert, col(fg), 0);
    lv_obj_set_style_text_color(clock_label, col(fg), 0);
    lv_obj_align_to(band_state, band_icon, LV_ALIGN_OUT_RIGHT_MID, s == S_WARN || s == S_CRIT ? 10 : 0, 0);
    lv_obj_align_to(band_alert, band_state, LV_ALIGN_OUT_RIGHT_MID, 20, 0);
    if (unacked) lv_obj_remove_flag(band_ack, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(band_ack, LV_OBJ_FLAG_HIDDEN);

    for (int p = 0; p < P_COUNT; p++) {
        int n = 0;
        uint32_t c = C_WARN;
        if (p == P_ALERTS) {
            n = snap.n_warn + snap.n_crit;
            if (snap.n_crit) c = C_CRIT;
        } else if (p == P_STATUS) {
            n = snap.n_services - count_ok(snap.services, snap.n_services) + snap.n_hosts -
                count_ok(snap.hosts, snap.n_hosts) + snap.n_vms - count_ok(snap.vms, snap.n_vms);
        } else if (p == P_POWER && (snap.ups_onbattery || snap.ups_lowbattery)) {
            n = 1;
            c = C_CRIT;
        }
        if (!have_snap || n == 0) {
            lv_obj_add_flag(nav_badge[p], LV_OBJ_FLAG_HIDDEN);
            continue;
        }
        lv_obj_remove_flag(nav_badge[p], LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_bg_color(nav_badge[p], col(c), 0);
        lv_obj_t *l = lv_obj_get_child(nav_badge[p], 0);
        char s[8];
        snprintf(s, sizeof s, "%d", n > 99 ? 99 : n);
        lv_label_set_text(l, s);
        lv_obj_set_style_text_color(l, col(c == C_WARN ? 0x000000 : 0xffffff), 0);
    }
}

static void update_nav(void)
{
    for (int p = 0; p < P_COUNT; p++) {
        bool on = p == (int)page;
        lv_obj_set_style_bg_color(nav_btn[p], col(on ? C_SURF_ON : C_SURF), 0);
        lv_obj_set_style_border_width(nav_btn[p], on ? 6 : 0, 0);
        lv_obj_t *l = lv_obj_get_child(nav_btn[p], 0);
        lv_obj_set_style_text_color(l, col(on ? C_TEXT : C_MUTED), 0);
    }
}

static void build_body(void)
{
    lv_obj_clean(body);
    if (!have_snap) {
        lv_obj_center(text(body, "読み込み中", f36, C_MUTED));
    } else {
        switch (page) {
        case P_OVERVIEW: build_overview(); break;
        case P_ALERTS: build_alerts(); break;
        case P_STATUS: build_status(); break;
        case P_POWER: build_power(); break;
        case P_HOSTS: build_hosts(); break;
        case P_SETTINGS: build_settings(); break;
        default: break;
        }
    }
    update_nav();
}

/* ---------- 明るさ・放置・焼き付き ---------- */

static void on_wake_press(lv_event_t *e)
{
    dimmed = false;
    apply_brightness();
}

static void on_wake_release(lv_event_t *e)
{
    lv_obj_add_flag(wake, LV_OBJ_FLAG_HIDDEN);
    last_switch = lv_tick_get();
}

static void update_idle(void)
{
    uint32_t idle = lv_display_get_inactive_time(NULL);
    if (settings->dim_after && !dimmed && idle >= (uint32_t)settings->dim_after * 1000) {
        dimmed = true;
        apply_brightness();
        lv_obj_remove_flag(wake, LV_OBJ_FLAG_HIDDEN);
    }
    if (idle >= IDLE_HOME_MS && page != P_OVERVIEW) go(P_OVERVIEW);
}

static void shift_timer(lv_timer_t *t)
{
    static const int dx[] = {0, 2, 2, 0}, dy[] = {0, 0, 2, 2};
    static int step;
    step = (step + 1) % 4;
    lv_obj_set_pos(root, dx[step] - 1, dy[step] - 1);
}

static void clock_timer(lv_timer_t *t)
{
    char s[8];
    time_t now = time(NULL);
    strftime(s, sizeof s, "%H:%M", localtime(&now));
    if (strcmp(lv_label_get_text(clock_label), s) != 0) lv_label_set_text(clock_label, s);
}

/* ---------- 入口 ---------- */

static lv_font_t *font(int size)
{
    char path[300];
    snprintf(path, sizeof path, "A:%s", cfg->font);
    lv_font_t *f = lv_tiny_ttf_create_file(path, size);
    return f ? f : (lv_font_t *)LV_FONT_DEFAULT;
}

void ui_init(const config_t *c, settings_t *s)
{
    cfg = c;
    settings = s;
    f20 = font(20);
    f24 = font(24);
    f28 = font(28);
    f36 = font(36);
    f56 = font(56);
    f96 = font(96);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, col(C_BG), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    root = box(scr, -1, -1, W, H, C_BG);
    lv_obj_set_style_radius(root, 0, 0);

    band = button(root, 0, 0, W, BAND_H, C_SURF, on_band, NULL);
    lv_obj_set_style_radius(band, 0, 0);
    lv_obj_set_style_bg_color(band, col(C_SURF), LV_STATE_PRESSED);
    band_icon = text(band, "", f36, C_TEXT);
    lv_obj_align(band_icon, LV_ALIGN_LEFT_MID, 24, 0);
    band_state = text(band, "", f36, C_TEXT);
    band_alert = text(band, "", f28, C_TEXT);
    lv_label_set_long_mode(band_alert, LV_LABEL_LONG_MODE_DOTS);
    lv_obj_set_width(band_alert, 300);
    clock_label = text(band, "", f36, C_TEXT);
    lv_obj_align(clock_label, LV_ALIGN_RIGHT_MID, -24, 0);
    band_ack = button(band, W - 24 - 110 - 24 - 140, (BAND_H - 56) / 2, 140, 56, 0x000000, on_ack, NULL);
    lv_obj_center(text(band_ack, "確認", f28, 0xffffff));
    lv_obj_add_flag(band_ack, LV_OBJ_FLAG_HIDDEN);

    body = box(root, 0, BODY_Y, W, BODY_H, C_BG);
    lv_obj_set_style_radius(body, 0, 0);

    int bw = W / P_COUNT;
    for (int p = 0; p < P_COUNT; p++) {
        int x = p * W / P_COUNT;
        nav_btn[p] = button(root, x + 4, H - NAV_H + 4, bw - 8, NAV_H - 8, C_SURF, on_nav, (void *)(intptr_t)p);
        lv_obj_set_style_border_side(nav_btn[p], LV_BORDER_SIDE_TOP, 0);
        lv_obj_set_style_border_color(nav_btn[p], col(C_TEXT), 0);
        lv_obj_center(text(nav_btn[p], PAGE_NAMES[p], f28, C_MUTED));
        nav_badge[p] = box(nav_btn[p], bw - 8 - 40, 6, 34, 30, C_WARN);
        lv_obj_set_style_radius(nav_badge[p], 15, 0);
        lv_obj_center(text(nav_badge[p], "", f20, 0x000000));
        lv_obj_add_flag(nav_badge[p], LV_OBJ_FLAG_HIDDEN);
    }

    /* 暗いときの最初のタッチを受け止め、下のボタンへ渡さない。 */
    wake = lv_obj_create(lv_layer_top());
    lv_obj_remove_style_all(wake);
    lv_obj_set_size(wake, W, H);
    lv_obj_add_flag(wake, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(wake, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_event_cb(wake, on_wake_press, LV_EVENT_PRESSED, NULL);
    lv_obj_add_event_cb(wake, on_wake_release, LV_EVENT_RELEASED, NULL);
    lv_obj_add_event_cb(wake, on_wake_release, LV_EVENT_PRESS_LOST, NULL);

    lv_timer_create(clock_timer, 1000, NULL);
    lv_timer_create(shift_timer, SHIFT_MS, NULL);
    clock_timer(NULL);
    apply_brightness();
    update_band();
    build_body();
}

/* 確認用：次のページへ進める（SIGUSR2）。 */
void ui_next_page(void)
{
    go((enum page)((page + 1) % P_COUNT));
}

void ui_tick(void)
{
    if (data_take(&snap, &snap_version)) {
        have_snap = true;
        update_alert_tracking();
        dirty = true;
    }
    update_idle();
    update_band();
    /* 押している最中に作り直すと押した物が消えるので、離すまで待つ。 */
    lv_indev_t *indev = lv_indev_get_next(NULL);
    bool pressed = indev && lv_indev_get_state(indev) == LV_INDEV_STATE_PRESSED;
    if (dirty && !pressed) {
        dirty = false;
        build_body();
    }
}
