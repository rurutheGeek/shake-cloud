/* 設定ファイル（読むだけ）と、画面の設定（保存する）の読み書き。 */
#include <cjson/cJSON.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "app.h"

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc((size_t)n + 1);
    if (buf && fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf);
        buf = NULL;
    }
    if (buf) buf[n] = '\0';
    fclose(f);
    return buf;
}

static void copy_str(cJSON *obj, const char *key, char *dst, size_t len)
{
    cJSON *v = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (cJSON_IsString(v) && v->valuestring) snprintf(dst, len, "%s", v->valuestring);
}

#define Q(field, key) copy_str(q, key, cfg->field, sizeof cfg->field)

int config_load(config_t *cfg, const char *path)
{
    memset(cfg, 0, sizeof *cfg);
    char *text = read_file(path);
    if (!text) {
        fprintf(stderr, "設定を読めない: %s\n", path);
        return -1;
    }
    cJSON *root = cJSON_Parse(text);
    free(text);
    if (!root) {
        fprintf(stderr, "設定の JSON が壊れている: %s\n", path);
        return -1;
    }
    copy_str(root, "prometheus", cfg->prometheus, sizeof cfg->prometheus);
    copy_str(root, "alertmanager", cfg->alertmanager, sizeof cfg->alertmanager);
    copy_str(root, "settings_file", cfg->settings_file, sizeof cfg->settings_file);
    copy_str(root, "font", cfg->font, sizeof cfg->font);
    copy_str(root, "backlight", cfg->backlight, sizeof cfg->backlight);
    copy_str(root, "drm", cfg->drm, sizeof cfg->drm);
    copy_str(root, "touch_name", cfg->touch_name, sizeof cfg->touch_name);
    copy_str(root, "disk_alerts", cfg->disk_alerts, sizeof cfg->disk_alerts);

    cJSON *aliases = cJSON_GetObjectItemCaseSensitive(root, "aliases");
    cJSON *a;
    cJSON_ArrayForEach(a, aliases) {
        if (cfg->n_aliases >= MAX_ALIASES || !cJSON_IsString(a)) continue;
        snprintf(cfg->alias_from[cfg->n_aliases], NAME_LEN, "%s", a->string);
        snprintf(cfg->alias_to[cfg->n_aliases], NAME_LEN, "%s", a->valuestring);
        cfg->n_aliases++;
    }

    cJSON *num;
    cfg->ups_watts = cJSON_IsNumber(num = cJSON_GetObjectItemCaseSensitive(root, "ups_watts")) ? num->valuedouble : 0;
    cfg->yen_per_kwh = cJSON_IsNumber(num = cJSON_GetObjectItemCaseSensitive(root, "yen_per_kwh")) ? num->valuedouble : 0;

    cJSON *q = cJSON_GetObjectItemCaseSensitive(root, "queries");
    Q(q_services, "services");
    Q(q_hosts, "hosts");
    Q(q_host_names, "host_names");
    Q(q_vms, "vms");
    Q(q_latency, "latency");
    Q(q_ups_charge, "ups_charge");
    Q(q_ups_load, "ups_load");
    Q(q_ups_runtime, "ups_runtime");
    Q(q_ups_input, "ups_input");
    Q(q_ups_onbattery, "ups_onbattery");
    Q(q_ups_lowbattery, "ups_lowbattery");
    Q(q_host_cpu, "host_cpu");
    Q(q_host_mem, "host_mem");
    Q(q_host_disk, "host_disk");
    Q(q_host_temp, "host_temp");
    Q(q_vm_cpu, "vm_cpu");
    Q(q_vm_mem, "vm_mem");
    Q(q_backup_age, "backup_age");
    Q(q_backup_max, "backup_max");
    Q(q_cloud_backup_age, "cloud_backup_age");
    Q(q_fs_size, "fs_size");
    Q(q_fs_avail, "fs_avail");
    Q(q_smart_healthy, "smart_healthy");
    Q(q_smart_temp, "smart_temp");
    Q(q_pve_storage_size, "pve_storage_size");
    Q(q_pve_storage_used, "pve_storage_used");
    Q(q_ups_load_today, "ups_load_today");
    Q(q_ups_load_week, "ups_load_week");
    Q(q_wan_rx, "wan_rx");
    Q(q_wan_tx, "wan_tx");
    Q(q_wan_rx_max, "wan_rx_max");
    Q(q_wan_tx_max, "wan_tx_max");
    Q(q_wan_rx_today, "wan_rx_today");
    Q(q_wan_tx_today, "wan_tx_today");
    Q(q_wifi, "wifi");
    Q(q_segments, "segments");
    Q(q_speed_down, "speed_down");
    Q(q_speed_up, "speed_up");
    Q(q_speed_age, "speed_age");
    Q(q_speed_by_hour, "speed_by_hour");
    cJSON_Delete(root);
    return 0;
}

const char *config_alias(const config_t *cfg, const char *name)
{
    for (int i = 0; i < cfg->n_aliases; i++)
        if (strcmp(cfg->alias_from[i], name) == 0) return cfg->alias_to[i];
    return name;
}

static int pick(int v, const int *allowed, int n, int fallback)
{
    for (int i = 0; i < n; i++)
        if (allowed[i] == v) return v;
    return fallback;
}

static const int BRIGHTNESS[] = {25, 50, 75, 100};
static const int DIM_AFTER[] = {60, 300, 1800, 0};
static const int DIM_LEVEL[] = {0, 10};

void settings_load(settings_t *s, const char *path)
{
    s->brightness = 100;
    s->dim_after = 0;
    s->dim_level = 10;
    char *text = path[0] ? read_file(path) : NULL;
    if (!text) return;
    cJSON *root = cJSON_Parse(text);
    free(text);
    if (!root) return;
    cJSON *v;
    if (cJSON_IsNumber(v = cJSON_GetObjectItemCaseSensitive(root, "brightness")))
        s->brightness = pick(v->valueint, BRIGHTNESS, 4, 100);
    if (cJSON_IsNumber(v = cJSON_GetObjectItemCaseSensitive(root, "dim_after")))
        s->dim_after = pick(v->valueint, DIM_AFTER, 4, 0);
    if (cJSON_IsNumber(v = cJSON_GetObjectItemCaseSensitive(root, "dim_level")))
        s->dim_level = pick(v->valueint, DIM_LEVEL, 2, 10);
    cJSON_Delete(root);
}

/* 置き場（HDD）が無いときは保存しない。表示は初期値のまま動く。 */
void settings_save(const settings_t *s, const char *path)
{
    if (!path[0]) return;
    char tmp[300];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f) return;
    fprintf(f, "{\"brightness\": %d, \"dim_after\": %d, \"dim_level\": %d}\n",
            s->brightness, s->dim_after, s->dim_level);
    if (fclose(f) == 0) rename(tmp, path);
    else unlink(tmp);
}
