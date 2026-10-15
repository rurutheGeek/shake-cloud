/* タッチパネルの表示アプリで共有する型と関数。 */
#ifndef TOUCH_PANEL_APP_H
#define TOUCH_PANEL_APP_H

#include <pthread.h>
#include <stdbool.h>
#include <time.h>

#define MAX_ITEMS 64
#define MAX_HOSTS 16
#define MAX_GROUPS 32
#define MAX_FPS 128
#define NAME_LEN 48
#define MAX_ALIASES 48
#define MAX_BACKUPS 16
#define MAX_FS 32
#define MAX_COUNTS 8

/* 設定ファイル（読むだけ）。 */
typedef struct {
    char prometheus[128];
    char alertmanager[128];
    char settings_file[256];
    char font[256];
    char backlight[128];
    char drm[128];
    char touch_name[64];
    char disk_alerts[128];
    int n_aliases;
    char alias_from[MAX_ALIASES][NAME_LEN];
    char alias_to[MAX_ALIASES][NAME_LEN];
    double ups_watts;        /* UPS の定格（W）。負荷 % から消費電力を出す */
    double yen_per_kwh;      /* 電力量単価 */
    char q_services[256], q_hosts[256], q_host_names[256], q_vms[512], q_latency[256];
    char q_ups_charge[256], q_ups_load[256], q_ups_runtime[256], q_ups_input[256];
    char q_ups_onbattery[256], q_ups_lowbattery[256];
    char q_host_cpu[256], q_host_mem[256], q_host_disk[256], q_host_temp[256];
    char q_vm_cpu[512], q_vm_mem[512];
    char q_backup_age[256], q_backup_max[256], q_cloud_backup_age[256];
    char q_fs_size[256], q_fs_avail[256], q_smart_healthy[256], q_smart_temp[256];
    char q_pve_storage_size[256], q_pve_storage_used[256];
    char q_ups_load_today[256], q_ups_load_week[256];
    char q_wan_rx[256], q_wan_tx[256], q_wan_rx_max[256], q_wan_tx_max[256], q_wan_rx_today[256], q_wan_tx_today[256];
    char q_wifi[256], q_segments[256];
} config_t;

/* 画面の設定（利用者が選び、保存する）。 */
typedef struct {
    int brightness;   /* 25・50・75・100 */
    int dim_after;    /* 秒。0 は無制限 */
    int dim_level;    /* 0 は消す、それ以外は % */
} settings_t;

typedef struct {
    char name[NAME_LEN];
    bool ok;
} item_t;

typedef struct {
    char name[NAME_LEN];
    bool up;
    bool vm;          /* node_exporter が無く、Proxmox の値だけで見る VM */
    double cpu, mem, disk, temp; /* 読めないときは負の値 */
} host_t;

typedef struct {
    char name[NAME_LEN];
    double age;      /* 秒。成功が一度も無ければ負 */
    double max_age;
} backup_t;

typedef struct {
    char host[NAME_LEN];
    char mount[NAME_LEN];
    double size, avail;
    int health;      /* -1 不明、0 異常、1 正常 */
    double temp;     /* 不明は負 */
} fs_t;

typedef struct {
    char name[NAME_LEN];
    double n;
} count_t;

typedef struct {
    char alertname[64];
    char label[64];
    char target[NAME_LEN];
    int severity; /* 1 注意、2 危険 */
    int count;
    time_t since;
} alert_group_t;

typedef struct {
    bool prom_stale;  /* 2 回続けて読めない */
    bool am_stale;
    bool am_seen;     /* 一度でも Alertmanager を読めた */
    item_t services[MAX_ITEMS];
    int n_services;
    item_t hosts[MAX_HOSTS];
    int n_hosts;
    item_t vms[MAX_ITEMS];
    int n_vms;
    host_t hostinfo[MAX_ITEMS];
    int n_hostinfo;
    double latency_ms;
    bool ups_ok;
    double ups_charge, ups_load, ups_runtime, ups_input;
    bool ups_onbattery, ups_lowbattery;
    backup_t backups[MAX_BACKUPS];
    int n_backups;
    fs_t fs[MAX_FS];
    int n_fs;
    double load_today, load_week; /* UPS の負荷 % の平均。不明は負 */
    double today_seconds;
    double wan_rx, wan_tx, wan_rx_max, wan_tx_max, wan_rx_today, wan_tx_today; /* bit/s と byte。不明は負 */
    count_t ssids[MAX_COUNTS], segments[MAX_COUNTS];
    int n_ssids, n_segments;
    alert_group_t groups[MAX_GROUPS];
    int n_groups;
    int n_warn, n_crit, n_disk;
    char fps[MAX_FPS][24];
    bool fp_crit[MAX_FPS];
    int n_fps;
} snapshot_t;

/* config.c */
int config_load(config_t *cfg, const char *path);
void settings_load(settings_t *s, const char *path);
void settings_save(const settings_t *s, const char *path);
const char *config_alias(const config_t *cfg, const char *name);

/* data.c：別スレッドで定期的に読み、最新の写しを渡す。 */
void data_start(const config_t *cfg);
/* 新しい写しがあれば out へ写して true を返す。 */
bool data_take(snapshot_t *out, unsigned *seen_version);

/* backlight.c */
void backlight_init(const char *dir);
void backlight_set(int percent); /* 0 は消す */

/* ui.c */
void ui_init(const config_t *cfg, settings_t *settings);
void ui_tick(void);
void ui_next_page(void);

#endif
