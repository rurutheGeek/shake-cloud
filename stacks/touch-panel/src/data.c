/* Prometheus と Alertmanager を別スレッドで読み、画面へ渡す写しを作る。 */
#define _GNU_SOURCE
#include <stddef.h>
#include <cjson/cJSON.h>
#include <curl/curl.h>
#include <regex.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "app.h"

#define POLL_SECONDS 15
#define TIMEOUT_SECONDS 3

static const config_t *cfg;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t wake = PTHREAD_COND_INITIALIZER;
static enum maint_action req_action;
static int req_minutes;
static snapshot_t shared;
static unsigned version;

/* instance → ホスト名。ホストが落ちて node_uname_info が消えても名前を保つ。 */
static char name_key[MAX_HOSTS][NAME_LEN];
static char name_val[MAX_HOSTS][NAME_LEN];
static int n_names;

typedef struct {
    char *data;
    size_t len;
} buf_t;

static size_t on_body(void *p, size_t size, size_t n, void *user)
{
    buf_t *b = user;
    size_t add = size * n;
    char *grown = realloc(b->data, b->len + add + 1);
    if (!grown) return 0;
    b->data = grown;
    memcpy(b->data + b->len, p, add);
    b->len += add;
    b->data[b->len] = '\0';
    return add;
}

static cJSON *get_json(CURL *curl, const char *url)
{
    buf_t b = {0};
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, on_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &b);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, (long)TIMEOUT_SECONDS);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    CURLcode rc = curl_easy_perform(curl);
    long status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    cJSON *json = NULL;
    if (rc == CURLE_OK && status == 200 && b.data) json = cJSON_Parse(b.data);
    free(b.data);
    return json;
}

/* 問い合わせの結果（vector）を返す。失敗は NULL。呼び出し側が root を消す。 */
/* 今日の 0 時からの秒数（最低 60）。問い合わせの {since} をこれに置き換える。 */
static long seconds_since_midnight(void)
{
    time_t now = time(NULL);
    struct tm tm;
    localtime_r(&now, &tm);
    long s = tm.tm_hour * 3600L + tm.tm_min * 60L + tm.tm_sec;
    return s < 60 ? 60 : s;
}

static void expand(const char *expr, char *out, size_t len)
{
    const char *p = strstr(expr, "{since}");
    if (!p) {
        snprintf(out, len, "%s", expr);
        return;
    }
    snprintf(out, len, "%.*s%lds%s", (int)(p - expr), expr, seconds_since_midnight(), p + 7);
}

static cJSON *query(CURL *curl, const char *raw, cJSON **root)
{
    *root = NULL;
    if (!raw[0]) return NULL;
    char expr[1024];
    expand(raw, expr, sizeof expr);
    char *esc = curl_easy_escape(curl, expr, 0);
    char url[2048];
    snprintf(url, sizeof url, "%s/api/v1/query?query=%s", cfg->prometheus, esc);
    curl_free(esc);
    *root = get_json(curl, url);
    if (!*root) return NULL;
    cJSON *data = cJSON_GetObjectItemCaseSensitive(*root, "data");
    return cJSON_GetObjectItemCaseSensitive(data, "result");
}

static double sample_value(cJSON *sample)
{
    cJSON *v = cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(sample, "value"), 1);
    return cJSON_IsString(v) ? atof(v->valuestring) : 0;
}

static const char *label(cJSON *sample, const char *key)
{
    cJSON *m = cJSON_GetObjectItemCaseSensitive(sample, "metric");
    cJSON *v = cJSON_GetObjectItemCaseSensitive(m, key);
    return cJSON_IsString(v) ? v->valuestring : "";
}

/* 1 つの値だけを返す問い合わせ。読めないときは false。 */
static bool scalar(CURL *curl, const char *expr, double *out, bool *empty)
{
    cJSON *root;
    cJSON *res = query(curl, expr, &root);
    bool ok = res != NULL;
    *empty = !cJSON_GetArraySize(res);
    if (ok && !*empty) *out = sample_value(cJSON_GetArrayItem(res, 0));
    cJSON_Delete(root);
    return ok;
}

/* https://awx.example/... → awx */
static void service_name(const char *url, char *out)
{
    const char *p = strstr(url, "://");
    p = p ? p + 3 : url;
    size_t n = strcspn(p, ".:/");
    if (n >= NAME_LEN) n = NAME_LEN - 1;
    memcpy(out, p, n);
    out[n] = '\0';
}

static const char *host_name(const char *instance)
{
    for (int i = 0; i < n_names; i++)
        if (strcmp(name_key[i], instance) == 0) return config_alias(cfg, name_val[i]);
    return instance;
}

static void remember_name(const char *instance, const char *nodename)
{
    for (int i = 0; i < n_names; i++)
        if (strcmp(name_key[i], instance) == 0) {
            snprintf(name_val[i], NAME_LEN, "%s", nodename);
            return;
        }
    if (n_names >= MAX_HOSTS) return;
    snprintf(name_key[n_names], NAME_LEN, "%s", instance);
    snprintf(name_val[n_names], NAME_LEN, "%s", nodename);
    n_names++;
}

static int by_name(const void *a, const void *b)
{
    return strcmp(((const item_t *)a)->name, ((const item_t *)b)->name);
}

static bool fetch_items(CURL *curl, const char *expr, const char *kind, item_t *items, int *n, int max)
{
    cJSON *root;
    cJSON *res = query(curl, expr, &root);
    if (!res) {
        cJSON_Delete(root);
        return false;
    }
    *n = 0;
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        if (*n >= max) break;
        item_t *it = &items[(*n)++];
        if (strcmp(kind, "service") == 0) service_name(label(s, "instance"), it->name);
        else if (strcmp(kind, "host") == 0) snprintf(it->name, NAME_LEN, "%s", host_name(label(s, "instance")));
        else snprintf(it->name, NAME_LEN, "%s", label(s, "name"));
        it->ok = sample_value(s) >= 1;
    }
    qsort(items, (size_t)*n, sizeof *items, by_name);
    cJSON_Delete(root);
    return true;
}

static host_t *hostinfo_for(snapshot_t *snap, const char *instance)
{
    const char *name = host_name(instance);
    for (int i = 0; i < snap->n_hostinfo; i++)
        if (strcmp(snap->hostinfo[i].name, name) == 0) return &snap->hostinfo[i];
    return NULL;
}

static void fetch_host_metric(CURL *curl, snapshot_t *snap, const char *expr, size_t offset)
{
    cJSON *root;
    cJSON *res = query(curl, expr, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        host_t *h = hostinfo_for(snap, label(s, "instance"));
        if (h) *(double *)((char *)h + offset) = sample_value(s);
    }
    cJSON_Delete(root);
}

/* node_exporter の無い VM は、Proxmox の値（name ラベル）で CPU とメモリだけ埋める。 */
static void fetch_vm_metric(CURL *curl, snapshot_t *snap, const char *expr, size_t offset)
{
    cJSON *root;
    cJSON *res = query(curl, expr, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        const char *name = label(s, "name");
        for (int i = 0; i < snap->n_hostinfo; i++)
            if (snap->hostinfo[i].vm && strcmp(snap->hostinfo[i].name, name) == 0)
                *(double *)((char *)&snap->hostinfo[i] + offset) = sample_value(s);
    }
    cJSON_Delete(root);
}

/* ---------- その他のページ ---------- */

static double scalar_or(CURL *curl, const char *expr, double fallback)
{
    double v = fallback;
    bool empty = true;
    if (!scalar(curl, expr, &v, &empty) || empty) return fallback;
    return v;
}

static void fetch_backups(CURL *curl, snapshot_t *snap)
{
    snap->n_backups = 0;
    cJSON *root;
    cJSON *res = query(curl, cfg->q_backup_age, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        if (snap->n_backups >= MAX_BACKUPS) break;
        backup_t *b = &snap->backups[snap->n_backups++];
        snprintf(b->name, NAME_LEN, "%s", config_alias(cfg, label(s, "target")));
        double age = sample_value(s);
        /* 一度も成功していない（時刻 0）は、とても古い値になる。 */
        b->age = age > 50.0 * 365 * 86400 ? -1 : age;
        b->max_age = 0;
    }
    cJSON_Delete(root);
    res = query(curl, cfg->q_backup_max, &root);
    cJSON_ArrayForEach(s, res) {
        const char *name = config_alias(cfg, label(s, "target"));
        for (int i = 0; i < snap->n_backups; i++)
            if (strcmp(snap->backups[i].name, name) == 0) snap->backups[i].max_age = sample_value(s);
    }
    cJSON_Delete(root);
    double cloud = scalar_or(curl, cfg->q_cloud_backup_age, -2);
    if (cloud > -2 && snap->n_backups < MAX_BACKUPS) {
        backup_t *b = &snap->backups[snap->n_backups++];
        snprintf(b->name, NAME_LEN, "%s", config_alias(cfg, "cloud-db"));
        b->age = cloud;
        b->max_age = 36 * 3600;
    }
}

/* /dev/sdb1 → /dev/sdb、/dev/nvme0n1p2 → /dev/nvme0n1 */
static void whole_disk(const char *dev, char *out, size_t len)
{
    snprintf(out, len, "%s", dev);
    size_t n = strlen(out);
    while (n && out[n - 1] >= '0' && out[n - 1] <= '9') n--;
    if (strstr(out, "nvme") && n && out[n - 1] == 'p') n--;
    else if (strstr(out, "mmcblk") && n && out[n - 1] == 'p') n--;
    out[n] = '\0';
}

static fs_t *find_fs(snapshot_t *snap, const char *host, const char *mount)
{
    for (int i = 0; i < snap->n_fs; i++)
        if (strcmp(snap->fs[i].host, host) == 0 && strcmp(snap->fs[i].mount, mount) == 0) return &snap->fs[i];
    return NULL;
}

static void fetch_storage(CURL *curl, snapshot_t *snap)
{
    snap->n_fs = 0;
    static char devices[MAX_FS][NAME_LEN], instances[MAX_FS][NAME_LEN];
    cJSON *root;
    cJSON *res = query(curl, cfg->q_fs_size, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        if (snap->n_fs >= MAX_FS) break;
        int i = snap->n_fs++;
        fs_t *f = &snap->fs[i];
        snprintf(f->host, NAME_LEN, "%s", host_name(label(s, "instance")));
        snprintf(f->mount, NAME_LEN, "%s", label(s, "mountpoint"));
        f->size = sample_value(s);
        f->avail = -1;
        f->health = -1;
        f->temp = -1;
        snprintf(devices[i], NAME_LEN, "%s", label(s, "device"));
        snprintf(instances[i], NAME_LEN, "%s", label(s, "instance"));
    }
    cJSON_Delete(root);
    res = query(curl, cfg->q_fs_avail, &root);
    cJSON_ArrayForEach(s, res) {
        fs_t *f = find_fs(snap, host_name(label(s, "instance")), label(s, "mountpoint"));
        if (f) f->avail = sample_value(s);
    }
    cJSON_Delete(root);

    /* SMART は disk ラベル（/dev/sdb）で、同じ instance のファイルシステムへ付ける。 */
    for (int pass = 0; pass < 2; pass++) {
        res = query(curl, pass ? cfg->q_smart_temp : cfg->q_smart_healthy, &root);
        cJSON_ArrayForEach(s, res) {
            for (int i = 0; i < snap->n_fs; i++) {
                char disk[NAME_LEN];
                whole_disk(devices[i], disk, sizeof disk);
                if (strcmp(instances[i], label(s, "instance")) != 0 || strcmp(disk, label(s, "disk")) != 0) continue;
                if (pass) snap->fs[i].temp = sample_value(s);
                else snap->fs[i].health = sample_value(s) >= 1;
            }
        }
        cJSON_Delete(root);
    }

    /* Proxmox の置き場（VM のディスクが乗る local-lvm など）。 */
    res = query(curl, cfg->q_pve_storage_size, &root);
    cJSON_ArrayForEach(s, res) {
        if (snap->n_fs >= MAX_FS) break;
        const char *id = label(s, "id");
        const char *store = strrchr(id, '/');
        fs_t *f = &snap->fs[snap->n_fs++];
        snprintf(f->host, NAME_LEN, "%s", config_alias(cfg, label(s, "node")[0] ? label(s, "node") : "apextox"));
        snprintf(f->mount, NAME_LEN, "%s", store ? store + 1 : id);
        f->size = sample_value(s);
        f->avail = -1;
        f->health = -1;
        f->temp = -1;
    }
    cJSON_Delete(root);
    res = query(curl, cfg->q_pve_storage_used, &root);
    cJSON_ArrayForEach(s, res) {
        const char *id = label(s, "id");
        const char *store = strrchr(id, '/');
        for (int i = 0; i < snap->n_fs; i++)
            if (store && strcmp(snap->fs[i].mount, store + 1) == 0) snap->fs[i].avail = snap->fs[i].size - sample_value(s);
    }
    cJSON_Delete(root);
}

static void fetch_counts(CURL *curl, const char *expr, const char *key, count_t *out, int *n)
{
    *n = 0;
    cJSON *root;
    cJSON *res = query(curl, expr, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        if (*n >= MAX_COUNTS) break;
        count_t *c = &out[(*n)++];
        snprintf(c->name, NAME_LEN, "%s", config_alias(cfg, label(s, key)));
        c->n = sample_value(s);
    }
    cJSON_Delete(root);
}

static void fetch_more(CURL *curl, snapshot_t *snap)
{
    fetch_backups(curl, snap);
    fetch_storage(curl, snap);
    snap->today_seconds = (double)seconds_since_midnight();
    snap->load_today = scalar_or(curl, cfg->q_ups_load_today, -1);
    snap->load_week = scalar_or(curl, cfg->q_ups_load_week, -1);
    snap->wan_rx = scalar_or(curl, cfg->q_wan_rx, -1);
    snap->wan_tx = scalar_or(curl, cfg->q_wan_tx, -1);
    snap->wan_rx_max = scalar_or(curl, cfg->q_wan_rx_max, -1);
    snap->wan_tx_max = scalar_or(curl, cfg->q_wan_tx_max, -1);
    snap->wan_rx_today = scalar_or(curl, cfg->q_wan_rx_today, -1);
    snap->wan_tx_today = scalar_or(curl, cfg->q_wan_tx_today, -1);
    snap->speed_down = scalar_or(curl, cfg->q_speed_down, -1);
    snap->speed_up = scalar_or(curl, cfg->q_speed_up, -1);
    snap->speed_age = scalar_or(curl, cfg->q_speed_age, -1);
    for (int h = 0; h < 24; h++) snap->speed_by_hour[h] = -1;
    cJSON *root;
    cJSON *res = query(curl, cfg->q_speed_by_hour, &root);
    cJSON *s;
    cJSON_ArrayForEach(s, res) {
        int h = atoi(label(s, "hour"));
        if (h >= 0 && h < 24) snap->speed_by_hour[h] = sample_value(s);
    }
    cJSON_Delete(root);
    fetch_counts(curl, cfg->q_wifi, "ssid", snap->ssids, &snap->n_ssids);
    fetch_counts(curl, cfg->q_segments, "segment", snap->segments, &snap->n_segments);
}

static bool fetch_prometheus(CURL *curl, snapshot_t *snap)
{
    cJSON *root;
    cJSON *res = query(curl, cfg->q_host_names, &root);
    if (!res) {
        cJSON_Delete(root);
        return false;
    }
    cJSON *s;
    cJSON_ArrayForEach(s, res) remember_name(label(s, "instance"), label(s, "nodename"));
    cJSON_Delete(root);

    if (!fetch_items(curl, cfg->q_services, "service", snap->services, &snap->n_services, MAX_ITEMS)) return false;
    if (!fetch_items(curl, cfg->q_hosts, "host", snap->hosts, &snap->n_hosts, MAX_HOSTS)) return false;
    if (!fetch_items(curl, cfg->q_vms, "vm", snap->vms, &snap->n_vms, MAX_ITEMS)) return false;

    snap->n_hostinfo = snap->n_hosts;
    for (int i = 0; i < snap->n_hosts; i++) {
        host_t *h = &snap->hostinfo[i];
        snprintf(h->name, NAME_LEN, "%s", snap->hosts[i].name);
        h->up = snap->hosts[i].ok;
        h->vm = false;
        h->cpu = h->mem = h->disk = h->temp = -1;
    }
    for (int i = 0; i < snap->n_vms && snap->n_hostinfo < MAX_ITEMS; i++) {
        bool known = false;
        for (int j = 0; j < snap->n_hosts; j++) known |= strcmp(snap->hostinfo[j].name, snap->vms[i].name) == 0;
        if (known) continue;
        host_t *h = &snap->hostinfo[snap->n_hostinfo++];
        snprintf(h->name, NAME_LEN, "%s", snap->vms[i].name);
        h->up = snap->vms[i].ok;
        h->vm = true;
        h->cpu = h->mem = h->disk = h->temp = -1;
    }
    fetch_vm_metric(curl, snap, cfg->q_vm_cpu, offsetof(host_t, cpu));
    fetch_vm_metric(curl, snap, cfg->q_vm_mem, offsetof(host_t, mem));
    fetch_host_metric(curl, snap, cfg->q_host_cpu, offsetof(host_t, cpu));
    fetch_host_metric(curl, snap, cfg->q_host_mem, offsetof(host_t, mem));
    fetch_host_metric(curl, snap, cfg->q_host_disk, offsetof(host_t, disk));
    fetch_host_metric(curl, snap, cfg->q_host_temp, offsetof(host_t, temp));

    bool empty;
    snap->latency_ms = -1;
    scalar(curl, cfg->q_latency, &snap->latency_ms, &empty);
    if (empty) snap->latency_ms = -1;

    snap->ups_ok = scalar(curl, cfg->q_ups_charge, &snap->ups_charge, &empty) && !empty;
    double v = 0;
    scalar(curl, cfg->q_ups_load, &snap->ups_load, &empty);
    scalar(curl, cfg->q_ups_runtime, &snap->ups_runtime, &empty);
    scalar(curl, cfg->q_ups_input, &snap->ups_input, &empty);
    snap->ups_onbattery = scalar(curl, cfg->q_ups_onbattery, &v, &empty) && !empty && v >= 1;
    v = 0;
    snap->ups_lowbattery = scalar(curl, cfg->q_ups_lowbattery, &v, &empty) && !empty && v >= 1;
    fetch_more(curl, snap);
    return true;
}

static time_t parse_time(const char *s)
{
    struct tm tm = {0};
    if (!strptime(s, "%Y-%m-%dT%H:%M:%S", &tm)) return 0;
    return timegm(&tm);
}

/* 警告の対象を人が読める名前にする。VM は名前、ホストはホスト名（＋ユニットやディスク）。 */
static const char *alert_target(cJSON *labels)
{
    static char out[NAME_LEN * 2];
    cJSON *id = cJSON_GetObjectItemCaseSensitive(labels, "id");
    cJSON *name = cJSON_GetObjectItemCaseSensitive(labels, "name");
    cJSON *disk = cJSON_GetObjectItemCaseSensitive(labels, "disk");
    cJSON *inst = cJSON_GetObjectItemCaseSensitive(labels, "instance");
    const char *extra = cJSON_IsString(disk) ? disk->valuestring : cJSON_IsString(name) ? name->valuestring : "";
    if (cJSON_IsString(id) && cJSON_IsString(name)) return name->valuestring;
    if (!cJSON_IsString(inst)) return extra;
    if (strstr(inst->valuestring, "://")) {
        service_name(inst->valuestring, out);
        return out;
    }
    const char *host = host_name(inst->valuestring);
    if (strchr(host, ':') == NULL && strcmp(host, inst->valuestring) == 0) {
        /* pve-exporter の instance（ポート無しの IP）は K11 のこと。 */
        for (int i = 0; i < n_names; i++)
            if (strncmp(name_key[i], inst->valuestring, strlen(inst->valuestring)) == 0 &&
                name_key[i][strlen(inst->valuestring)] == ':') host = config_alias(cfg, name_val[i]);
    }
    snprintf(out, sizeof out, extra[0] ? "%s %s" : "%s", host, extra);
    return out;
}

/* 作業中（消音）でも表示は続けるので、消音された警告も読む。 */
static bool fetch_alerts(CURL *curl, snapshot_t *snap, regex_t *disk_re)
{
    char url[256];
    snprintf(url, sizeof url, "%s/api/v2/alerts?active=true&silenced=true&inhibited=false", cfg->alertmanager);
    cJSON *root = get_json(curl, url);
    if (!cJSON_IsArray(root)) {
        cJSON_Delete(root);
        return false;
    }
    snap->n_groups = snap->n_warn = snap->n_crit = snap->n_disk = snap->n_fps = 0;
    cJSON *a;
    cJSON_ArrayForEach(a, root) {
        cJSON *labels = cJSON_GetObjectItemCaseSensitive(a, "labels");
        cJSON *ann = cJSON_GetObjectItemCaseSensitive(a, "annotations");
        cJSON *jn = cJSON_GetObjectItemCaseSensitive(labels, "alertname");
        cJSON *js = cJSON_GetObjectItemCaseSensitive(labels, "severity");
        const char *name = cJSON_IsString(jn) ? jn->valuestring : "";
        const char *sev = cJSON_IsString(js) ? js->valuestring : "";
        int severity = strcmp(sev, "critical") == 0 ? 2 : strcmp(sev, "warning") == 0 ? 1 : 0;
        if (!severity) continue; /* Watchdog など */
        if (severity == 2) snap->n_crit++;
        else snap->n_warn++;
        if (disk_re && regexec(disk_re, name, 0, NULL, 0) == 0) snap->n_disk++;

        cJSON *fp = cJSON_GetObjectItemCaseSensitive(a, "fingerprint");
        if (cJSON_IsString(fp) && snap->n_fps < MAX_FPS) {
            snprintf(snap->fps[snap->n_fps], 24, "%s", fp->valuestring);
            snap->fp_crit[snap->n_fps++] = severity == 2;
        }
        cJSON *starts = cJSON_GetObjectItemCaseSensitive(a, "startsAt");
        time_t since = cJSON_IsString(starts) ? parse_time(starts->valuestring) : 0;

        alert_group_t *g = NULL;
        for (int i = 0; i < snap->n_groups; i++)
            if (strcmp(snap->groups[i].alertname, name) == 0) g = &snap->groups[i];
        if (!g) {
            if (snap->n_groups >= MAX_GROUPS) continue;
            g = &snap->groups[snap->n_groups++];
            memset(g, 0, sizeof *g);
            snprintf(g->alertname, sizeof g->alertname, "%s", name);
            cJSON *panel = cJSON_GetObjectItemCaseSensitive(ann, "panel");
            snprintf(g->label, sizeof g->label, "%s", cJSON_IsString(panel) ? panel->valuestring : name);
            snprintf(g->target, NAME_LEN, "%.47s", alert_target(labels));
            g->since = since;
        }
        g->count++;
        if (severity > g->severity) g->severity = severity;
        if (since && (!g->since || since > g->since)) g->since = since; /* 新しい順に並べるため最新を持つ */
    }
    cJSON_Delete(root);
    /* 重い順、同じ重さなら新しい順。 */
    for (int i = 1; i < snap->n_groups; i++)
        for (int j = i; j > 0; j--) {
            alert_group_t *x = &snap->groups[j - 1], *y = &snap->groups[j];
            if (x->severity > y->severity || (x->severity == y->severity && x->since >= y->since)) break;
            alert_group_t t = *x;
            *x = *y;
            *y = t;
        }
    return true;
}

/* ---------- 作業中（Alertmanager の消音） ---------- */

#define MAINT_CREATOR "touch-panel"

static void fetch_silences(CURL *curl, snapshot_t *snap)
{
    char url[256];
    snprintf(url, sizeof url, "%s/api/v2/silences", cfg->alertmanager);
    cJSON *root = get_json(curl, url);
    if (!cJSON_IsArray(root)) {
        cJSON_Delete(root);
        return; /* 読めないときは前の状態のまま */
    }
    snap->maint_active = false;
    snap->maint_id[0] = '\0';
    snap->maint_ends = 0;
    cJSON *si;
    cJSON_ArrayForEach(si, root) {
        cJSON *by = cJSON_GetObjectItemCaseSensitive(si, "createdBy");
        cJSON *st = cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(si, "status"), "state");
        cJSON *id = cJSON_GetObjectItemCaseSensitive(si, "id");
        cJSON *ends = cJSON_GetObjectItemCaseSensitive(si, "endsAt");
        if (!cJSON_IsString(by) || strcmp(by->valuestring, MAINT_CREATOR) != 0) continue;
        if (!cJSON_IsString(st) || strcmp(st->valuestring, "active") != 0) continue;
        time_t e = cJSON_IsString(ends) ? parse_time(ends->valuestring) : 0;
        if (e <= snap->maint_ends || !cJSON_IsString(id)) continue;
        snap->maint_active = true;
        snap->maint_ends = e;
        snprintf(snap->maint_id, sizeof snap->maint_id, "%s", id->valuestring);
    }
    cJSON_Delete(root);
}

static bool http_send(const char *method, const char *url, const char *body)
{
    CURL *c = curl_easy_init();
    if (!c) return false;
    struct curl_slist *hdr = curl_slist_append(NULL, "Content-Type: application/json");
    buf_t b = {0};
    curl_easy_setopt(c, CURLOPT_URL, url);
    curl_easy_setopt(c, CURLOPT_CUSTOMREQUEST, method);
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, hdr);
    if (body) curl_easy_setopt(c, CURLOPT_POSTFIELDS, body);
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, on_body);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &b);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, (long)TIMEOUT_SECONDS);
    curl_easy_setopt(c, CURLOPT_NOSIGNAL, 1L);
    CURLcode rc = curl_easy_perform(c);
    long status = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &status);
    free(b.data);
    curl_slist_free_all(hdr);
    curl_easy_cleanup(c);
    return rc == CURLE_OK && status == 200;
}

static void rfc3339(time_t t, char *out, size_t len)
{
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(out, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

/* Watchdog だけは止めない（止めると外の見張りが「監視が死んだ」と判断する）。 */
static bool create_silence(time_t ends)
{
    char start[32], end[32], url[256];
    rfc3339(time(NULL), start, sizeof start);
    rfc3339(ends, end, sizeof end);
    cJSON *body = cJSON_CreateObject();
    cJSON *matchers = cJSON_AddArrayToObject(body, "matchers");
    cJSON *m = cJSON_CreateObject();
    cJSON_AddStringToObject(m, "name", "alertname");
    cJSON_AddStringToObject(m, "value", "Watchdog");
    cJSON_AddBoolToObject(m, "isRegex", false);
    cJSON_AddBoolToObject(m, "isEqual", false);
    cJSON_AddItemToArray(matchers, m);
    cJSON_AddStringToObject(body, "startsAt", start);
    cJSON_AddStringToObject(body, "endsAt", end);
    cJSON_AddStringToObject(body, "createdBy", MAINT_CREATOR);
    cJSON_AddStringToObject(body, "comment", "作業中（タッチパネル）");
    char *json = cJSON_PrintUnformatted(body);
    snprintf(url, sizeof url, "%s/api/v2/silences", cfg->alertmanager);
    bool ok = http_send("POST", url, json);
    cJSON_free(json);
    cJSON_Delete(body);
    return ok;
}

static bool expire_silence(const char *id)
{
    char url[256];
    snprintf(url, sizeof url, "%s/api/v2/silence/%s", cfg->alertmanager, id);
    return http_send("DELETE", url, NULL);
}

static void carry_out(CURL *curl, snapshot_t *snap, enum maint_action action, int minutes)
{
    fetch_silences(curl, snap);
    bool ok = true;
    char old[48];
    snprintf(old, sizeof old, "%s", snap->maint_id);
    switch (action) {
    case MAINT_START:
        ok = create_silence(time(NULL) + minutes * 60);
        break;
    case MAINT_EXTEND:
        /* 延ばした消音を作ってから、古い方を消す（間で通知が漏れない）。 */
        ok = snap->maint_active && create_silence(snap->maint_ends + minutes * 60) && expire_silence(old);
        break;
    case MAINT_END:
        ok = !snap->maint_active || expire_silence(old);
        break;
    default:
        break;
    }
    snap->maint_failed = !ok;
    fetch_silences(curl, snap);
}

void data_request_maintenance(enum maint_action action, int minutes)
{
    pthread_mutex_lock(&lock);
    req_action = action;
    req_minutes = minutes;
    pthread_cond_signal(&wake);
    pthread_mutex_unlock(&lock);
}

static void publish(snapshot_t *snap)
{
    pthread_mutex_lock(&lock);
    shared = *snap;
    version++;
    pthread_mutex_unlock(&lock);
}

static void *worker(void *arg)
{
    CURL *curl = curl_easy_init();
    regex_t disk_re;
    bool have_re = cfg->disk_alerts[0] && regcomp(&disk_re, cfg->disk_alerts, REG_EXTENDED | REG_NOSUB) == 0;
    snapshot_t *snap = calloc(1, sizeof *snap);
    snap->prom_stale = snap->am_stale = true;
    int prom_fail = 2, am_fail = 2;
    for (;;) {
        if (fetch_prometheus(curl, snap)) prom_fail = 0;
        else prom_fail++;
        if (fetch_alerts(curl, snap, have_re ? &disk_re : NULL)) {
            am_fail = 0;
            snap->am_seen = true;
            fetch_silences(curl, snap);
        } else {
            am_fail++;
        }
        snap->prom_stale = prom_fail >= 2;
        snap->am_stale = am_fail >= 2;
        publish(snap);

        /* 次の読み取りまで待つ。作業中の切り替えを頼まれたら、すぐ行う。 */
        struct timespec until;
        clock_gettime(CLOCK_REALTIME, &until);
        until.tv_sec += POLL_SECONDS;
        for (;;) {
            pthread_mutex_lock(&lock);
            while (req_action == MAINT_NONE &&
                   pthread_cond_timedwait(&wake, &lock, &until) == 0) {
            }
            enum maint_action action = req_action;
            int minutes = req_minutes;
            req_action = MAINT_NONE;
            pthread_mutex_unlock(&lock);
            if (action == MAINT_NONE) break; /* 時間切れ */
            carry_out(curl, snap, action, minutes);
            publish(snap);
        }
    }
    return NULL;
}

void data_start(const config_t *c)
{
    cfg = c;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    pthread_t t;
    pthread_create(&t, NULL, worker, NULL);
    pthread_detach(t);
}

bool data_take(snapshot_t *out, unsigned *seen)
{
    bool fresh = false;
    pthread_mutex_lock(&lock);
    if (version != *seen) {
        *out = shared;
        *seen = version;
        fresh = true;
    }
    pthread_mutex_unlock(&lock);
    return fresh;
}
