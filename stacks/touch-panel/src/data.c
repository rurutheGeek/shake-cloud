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
static cJSON *query(CURL *curl, const char *expr, cJSON **root)
{
    *root = NULL;
    if (!expr[0]) return NULL;
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
        h->cpu = h->mem = h->disk = h->temp = -1;
    }
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

static bool fetch_alerts(CURL *curl, snapshot_t *snap, regex_t *disk_re)
{
    char url[256];
    snprintf(url, sizeof url, "%s/api/v2/alerts?active=true&silenced=false&inhibited=false", cfg->alertmanager);
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
        } else {
            am_fail++;
        }
        snap->prom_stale = prom_fail >= 2;
        snap->am_stale = am_fail >= 2;
        pthread_mutex_lock(&lock);
        shared = *snap;
        version++;
        pthread_mutex_unlock(&lock);
        sleep(POLL_SECONDS);
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
