/* スマホから見るための小さな HTTP の口（127.0.0.1 だけで待つ）。
 *
 * 外からは tarakoserver の Caddy が Authentik のログイン（Forward Auth）を通して中継する。
 *   GET  /            画面を映すページ
 *   GET  /screen.png  今の画面
 *   POST /tap?x=&y=   その位置を押して離す（X-Panel ヘッダが必要。よそのページからは送れない）
 * 画面の写しは LVGL のスレッド（main のループ）が作るので、ここは頼んで待つ。
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <zlib.h>

#include "app.h"
#include "lvgl.h"

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t done = PTHREAD_COND_INITIALIZER;
static bool want_png;
static unsigned char *png;
static size_t png_len;

#define TAP_QUEUE 8
static int tap_x[TAP_QUEUE], tap_y[TAP_QUEUE], tap_head, tap_tail;

static const char PAGE[] =
    "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>監視パネル</title>"
    "<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%277%27 fill=%27%231c1f24%27/%3E%3Cpath d=%27M7 20a9 9 0 0 1 18 0%27 stroke=%27%23fff%27 stroke-width=%272.4%27 fill=%27none%27 stroke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3Cpath d=%27M16 20l5-6%27 stroke=%27%23fff%27 stroke-width=%272.4%27 fill=%27none%27 stroke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3Ccircle cx=%2716%27 cy=%2720%27 r=%271.8%27 fill=%27%2322c55e%27/%3E%3C/svg%3E\">"
    "<style>"
    "html,body{margin:0;background:#1c1f24;height:100%;overflow:hidden}#w{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}img{display:block;width:100%;max-width:800px;touch-action:manipulation;user-select:none;-webkit-user-select:none}body.big img{max-width:none;width:min(100vw,calc(100vh*800/480))}@media (orientation:portrait){body.big img{width:min(100vh,calc(100vw*800/480));transform:rotate(90deg)}}#b{position:fixed;right:8px;bottom:8px;width:44px;height:44px;border:0;border-radius:10px;background:#2a2e35;color:#e6e6e6;font-size:22px;opacity:.85}body.big #b{opacity:.35}"
    "</style></head><body><div id=\"w\"><img id=\"s\" src=\"screen.png\" alt=\"監視パネル\"></div>"
    "<button id=\"b\" aria-label=\"大きく表示\"></button>"
    "<script>"
    "const s=document.getElementById('s'),b=document.getElementById('b');let t;function load(){clearTimeout(t);if(document.hidden)return;const n=new Image();n.onload=()=>{s.src=n.src;t=setTimeout(load,1500)};n.onerror=()=>{t=setTimeout(load,5000)};n.src='screen.png?'+Date.now()}s.addEventListener('click',e=>{const r=s.getBoundingClientRect(),w=s.offsetWidth,h=s.offsetHeight;let dx=e.clientX-(r.left+r.width/2),dy=e.clientY-(r.top+r.height/2);if(getComputedStyle(s).transform!=='none'){const q=dx;dx=dy;dy=-q}const x=Math.round((dx+w/2)*800/w),y=Math.round((dy+h/2)*480/h);if(x<0||y<0||x>=800||y>=480)return;fetch('tap?x='+x+'&y='+y,{method:'POST',headers:{'X-Panel':'1'}}).then(()=>{clearTimeout(t);t=setTimeout(load,300)})});function big(on){document.body.classList.toggle('big',on);b.textContent=on?'\u2921':'\u2922';try{localStorage.setItem('big',on?'1':'')}catch(e){}}b.addEventListener('click',async()=>{const on=!document.body.classList.contains('big');big(on);try{if(on){await document.documentElement.requestFullscreen();await screen.orientation.lock('landscape')}else if(document.fullscreenElement){await document.exitFullscreen()}}catch(e){}});try{big(localStorage.getItem('big')==='1')}catch(e){big(false)}document.addEventListener('visibilitychange',load);s.onload=()=>{s.onload=null;t=setTimeout(load,1500)};"
    "</script></body></html>";

/* ---------- PNG（無圧縮のフィルタ＋zlib） ---------- */

static void put32(unsigned char *p, uint32_t v)
{
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}

static size_t chunk(unsigned char *out, const char *type, const unsigned char *data, uint32_t len)
{
    put32(out, len);
    memcpy(out + 4, type, 4);
    if (len) memcpy(out + 8, data, len);
    uLong crc = crc32(0, out + 4, len + 4);
    put32(out + 8 + len, (uint32_t)crc);
    return len + 12;
}

static void encode_png(void)
{
    lv_draw_buf_t *b = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_RGB888);
    if (!b) return;
    uint32_t w = b->header.w, h = b->header.h;
    size_t raw_len = (size_t)(w * 3 + 1) * h;
    unsigned char *raw = malloc(raw_len);
    uLongf z_len = compressBound(raw_len);
    unsigned char *z = malloc(z_len);
    unsigned char *out = malloc(z_len + 128);
    if (raw && z && out) {
        for (uint32_t y = 0; y < h; y++) {
            unsigned char *dst = raw + y * (w * 3 + 1);
            const uint8_t *src = b->data + y * b->header.stride;
            dst[0] = 0;
            for (uint32_t x = 0; x < w; x++) { /* LVGL の RGB888 は B,G,R の並び */
                dst[1 + x * 3] = src[x * 3 + 2];
                dst[2 + x * 3] = src[x * 3 + 1];
                dst[3 + x * 3] = src[x * 3];
            }
        }
        if (compress2(z, &z_len, raw, raw_len, 1) == Z_OK) {
            size_t n = 0;
            memcpy(out, "\x89PNG\r\n\x1a\n", 8);
            n += 8;
            unsigned char ihdr[13];
            put32(ihdr, w);
            put32(ihdr + 4, h);
            ihdr[8] = 8, ihdr[9] = 2, ihdr[10] = 0, ihdr[11] = 0, ihdr[12] = 0;
            n += chunk(out + n, "IHDR", ihdr, 13);
            n += chunk(out + n, "IDAT", z, (uint32_t)z_len);
            n += chunk(out + n, "IEND", NULL, 0);
            free(png);
            png = out;
            png_len = n;
            out = NULL;
        }
    }
    free(raw);
    free(z);
    free(out);
    lv_draw_buf_destroy(b);
}

/* main のループから呼ぶ。頼まれていれば画面の写しを作る。 */
void remote_poll(void)
{
    pthread_mutex_lock(&lock);
    bool want = want_png;
    pthread_mutex_unlock(&lock);
    if (!want) return;
    encode_png();
    pthread_mutex_lock(&lock);
    want_png = false;
    pthread_cond_broadcast(&done);
    pthread_mutex_unlock(&lock);
}

/* ---------- タップ（仮の入力装置） ---------- */

static void tap_read(lv_indev_t *indev, lv_indev_data_t *data)
{
    /* 1 回目の読み取りで押し、2 回目で離す。 */
    static int phase;
    static int32_t x, y;
    pthread_mutex_lock(&lock);
    if (phase == 0 && tap_head != tap_tail) {
        x = tap_x[tap_tail];
        y = tap_y[tap_tail];
        tap_tail = (tap_tail + 1) % TAP_QUEUE;
        phase = 1;
    }
    pthread_mutex_unlock(&lock);
    data->point.x = x;
    data->point.y = y;
    if (phase == 1) {
        data->state = LV_INDEV_STATE_PRESSED;
        phase = 2;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
        phase = 0;
    }
}

/* ---------- HTTP ---------- */

static void reply(int fd, const char *status, const char *type, const void *body, size_t len)
{
    char head[256];
    int n = snprintf(head, sizeof head,
                     "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
                     "Cache-Control: no-store\r\nConnection: close\r\n\r\n",
                     status, type, len);
    if (write(fd, head, (size_t)n) < 0) return;
    if (len && write(fd, body, len) < 0) return;
}

static void serve(int fd)
{
    char req[2048];
    ssize_t n = read(fd, req, sizeof req - 1);
    if (n <= 0) return;
    req[n] = '\0';
    char method[8], path[256];
    if (sscanf(req, "%7s %255s", method, path) != 2) return;

    if (strcmp(method, "GET") == 0 && strcmp(path, "/") == 0) {
        reply(fd, "200 OK", "text/html; charset=utf-8", PAGE, sizeof PAGE - 1);
    } else if (strcmp(method, "GET") == 0 && strncmp(path, "/screen.png", 11) == 0) {
        pthread_mutex_lock(&lock);
        want_png = true;
        while (want_png) pthread_cond_wait(&done, &lock);
        unsigned char *copy = png_len ? malloc(png_len) : NULL;
        size_t len = png_len;
        if (copy) memcpy(copy, png, len);
        pthread_mutex_unlock(&lock);
        if (copy) reply(fd, "200 OK", "image/png", copy, len);
        else reply(fd, "503 Service Unavailable", "text/plain", "", 0);
        free(copy);
    } else if (strcmp(method, "POST") == 0 && strncmp(path, "/tap?", 5) == 0) {
        int x = -1, y = -1;
        const char *px = strstr(path, "x="), *py = strstr(path, "y=");
        if (px) x = atoi(px + 2);
        if (py) y = atoi(py + 2);
        if (!strcasestr(req, "\r\nX-Panel:") || x < 0 || y < 0 || x >= 800 || y >= 480) {
            reply(fd, "400 Bad Request", "text/plain", "", 0);
            return;
        }
        pthread_mutex_lock(&lock);
        int next = (tap_head + 1) % TAP_QUEUE;
        if (next != tap_tail) {
            tap_x[tap_head] = x;
            tap_y[tap_head] = y;
            tap_head = next;
        }
        pthread_mutex_unlock(&lock);
        reply(fd, "204 No Content", "text/plain", "", 0);
    } else {
        reply(fd, "404 Not Found", "text/plain", "", 0);
    }
}

static void *server(void *arg)
{
    int port = (int)(intptr_t)arg;
    int s = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons((uint16_t)port)};
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(s, (struct sockaddr *)&addr, sizeof addr) != 0 || listen(s, 8) != 0) {
        fprintf(stderr, "スマホ用の口を開けない: 127.0.0.1:%d\n", port);
        close(s);
        return NULL;
    }
    for (;;) {
        int fd = accept4(s, NULL, NULL, SOCK_CLOEXEC);
        if (fd < 0) continue;
        struct timeval tv = {.tv_sec = 5};
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
        serve(fd);
        close(fd);
    }
    return NULL;
}

void remote_start(int port)
{
    if (port <= 0) return;
    lv_indev_t *indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, tap_read);
    pthread_t t;
    pthread_create(&t, NULL, server, (void *)(intptr_t)port);
    pthread_detach(t);
}
