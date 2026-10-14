/* 画面の明るさ（/sys/class/backlight）。装置が無いときは何もしない。 */
#include <stdio.h>
#include <string.h>

#include "app.h"

static char dir[128];
static int max_brightness = -1;

static void write_int(const char *name, int v)
{
    char path[192];
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "%d\n", v);
    fclose(f);
}

void backlight_init(const char *path)
{
    snprintf(dir, sizeof dir, "%s", path);
    char p[192];
    snprintf(p, sizeof p, "%s/max_brightness", dir);
    FILE *f = fopen(p, "r");
    if (!f) return;
    if (fscanf(f, "%d", &max_brightness) != 1) max_brightness = -1;
    fclose(f);
}

void backlight_set(int percent)
{
    if (max_brightness <= 0) return;
    if (percent <= 0) {
        write_int("bl_power", 4);
        return;
    }
    int v = (max_brightness * percent + 99) / 100;
    write_int("brightness", v);
    write_int("bl_power", 0);
}
