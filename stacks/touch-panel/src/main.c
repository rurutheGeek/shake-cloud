/* 監視のタッチパネル。docs/development/M02-touch-panel.md */
#include <dirent.h>
#include <stddef.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#include "app.h"
#include "lvgl.h"

static volatile sig_atomic_t want_snapshot, want_next;

static uint32_t tick_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

static void on_usr1(int sig)
{
    want_snapshot = 1;
}

static void on_usr2(int sig)
{
    want_next = 1;
}

/* systemd の WatchdogSec へ生きていることを知らせる（libsystemd を使わずに送る）。 */
static void notify_watchdog(void)
{
    const char *path = getenv("NOTIFY_SOCKET");
    if (!path || !path[0]) return;
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    snprintf(addr.sun_path, sizeof addr.sun_path, "%s", path);
    if (addr.sun_path[0] == '@') addr.sun_path[0] = '\0';
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return;
    sendto(fd, "WATCHDOG=1", 10, 0, (struct sockaddr *)&addr,
           (socklen_t)(offsetof(struct sockaddr_un, sun_path) + strlen(path)));
    close(fd);
}

/* 名前に touch_name を含む evdev を探す（番号は起動ごとに変わりうる）。 */
static int find_touch(const char *want, char *out, size_t len)
{
    DIR *d = opendir("/dev/input");
    if (!d) return -1;
    struct dirent *e;
    int found = -1;
    while ((e = readdir(d)) && found < 0) {
        if (strncmp(e->d_name, "event", 5) != 0) continue;
        char path[300];
        snprintf(path, sizeof path, "/dev/input/%s", e->d_name);
        int fd = open(path, O_RDONLY);
        if (fd < 0) continue;
        char name[128] = "";
        ioctl(fd, EVIOCGNAME(sizeof name), name);
        close(fd);
        if (strstr(name, want)) {
            snprintf(out, len, "%s", path);
            found = 0;
        }
    }
    closedir(d);
    return found;
}

/* 画面の写しを PPM で /run/touch-panel/screen.ppm へ書く（確認用、SIGUSR1）。SIGUSR2 で次のページへ進む。 */
static void write_snapshot(void)
{
    lv_draw_buf_t *b = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_RGB888);
    if (!b) return;
    FILE *f = fopen("/run/touch-panel/screen.ppm", "wb");
    if (f) {
        uint32_t w = b->header.w, h = b->header.h;
        fprintf(f, "P6\n%u %u\n255\n", w, h);
        for (uint32_t y = 0; y < h; y++) {
            const uint8_t *row = b->data + y * b->header.stride;
            for (uint32_t x = 0; x < w; x++) {
                uint8_t px[3] = {row[x * 3 + 2], row[x * 3 + 1], row[x * 3]};
                fwrite(px, 1, 3, f);
            }
        }
        fclose(f);
    }
    lv_draw_buf_destroy(b);
}

int main(int argc, char **argv)
{
    const char *config_path = argc > 1 ? argv[1] : "/etc/touch-panel/panel.json";
    static config_t cfg;
    if (config_load(&cfg, config_path) != 0) return 1;
    static settings_t settings;
    settings_load(&settings, cfg.settings_file);

    signal(SIGUSR1, on_usr1);
    signal(SIGUSR2, on_usr2);
    lv_init();
    lv_tick_set_cb(tick_ms);

    lv_display_t *disp = lv_linux_drm_create();
    char *drm = cfg.drm[0] ? strdup(cfg.drm) : lv_linux_drm_find_device_path();
    if (!drm || lv_linux_drm_set_file(disp, drm, -1) != LV_RESULT_OK) {
        fprintf(stderr, "画面（DRM）を開けない: %s\n", drm ? drm : "(見つからない)");
        return 1;
    }

    char touch[300];
    if (find_touch(cfg.touch_name[0] ? cfg.touch_name : "ft5x06", touch, sizeof touch) == 0)
        lv_evdev_create(LV_INDEV_TYPE_POINTER, touch);
    else
        fprintf(stderr, "タッチが見つからない: %s\n", cfg.touch_name);

    backlight_init(cfg.backlight);
    data_start(&cfg);
    ui_init(&cfg, &settings);

    uint32_t last_notify = 0;
    for (;;) {
        ui_tick();
        if (lv_tick_elaps(last_notify) >= 5000) {
            last_notify = lv_tick_get();
            notify_watchdog();
        }
        if (want_next) {
            want_next = 0;
            ui_next_page();
        }
        if (want_snapshot) {
            want_snapshot = 0;
            write_snapshot();
        }
        uint32_t wait = lv_timer_handler();
        if (wait > 50) wait = 50;
        usleep(wait * 1000);
    }
}
