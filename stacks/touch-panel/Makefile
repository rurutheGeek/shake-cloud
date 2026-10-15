# タッチパネルの表示アプリ。LVGL は配備のときに LVGL_DIR へ展開したものを使う。
LVGL_DIR ?= lvgl
BUILD ?= build

CC ?= cc
CFLAGS ?= -O2 -g0
CFLAGS += -Wall -Wextra -Wno-unused-parameter -std=gnu11 -DLV_CONF_INCLUDE_SIMPLE -I. -I$(LVGL_DIR) -Isrc \
          $(shell pkg-config --cflags libdrm libcurl libcjson zlib)
LDLIBS += $(shell pkg-config --libs libdrm libcurl libcjson zlib) -lpthread -lm

LVGL_SRC := $(shell find $(LVGL_DIR)/src -name '*.c' \
              -not -path '*/thorvg/*' -not -path '*/libs/ffmpeg/*' -not -path '*/drivers/sdl/*' \
              -not -path '*/drivers/wayland/*' -not -path '*/drivers/glfw/*' -not -path '*/drivers/x11/*' \
              -not -path '*/drivers/nuttx/*' -not -path '*/drivers/libinput/*' -not -path '*/drivers/opengles/*' \
              -not -path '*/draw/nxp/*' -not -path '*/draw/renesas/*' -not -path '*/draw/espressif/*' \
              -not -path '*/draw/vg_lite/*' -not -path '*/draw/opengles/*' -not -path '*/draw/eve/*' \
              -not -path '*/draw/dma2d/*' -not -path '*/draw/sdl/*')
APP_SRC := $(wildcard src/*.c)
OBJ := $(patsubst %.c,$(BUILD)/%.o,$(APP_SRC)) $(patsubst $(LVGL_DIR)/%.c,$(BUILD)/lvgl/%.o,$(LVGL_SRC))

all: $(BUILD)/touch-panel

$(BUILD)/touch-panel: $(OBJ)
	$(CC) -o $@ $^ $(LDLIBS)

$(BUILD)/src/%.o: src/%.c src/*.h lv_conf.h
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD)/lvgl/%.o: $(LVGL_DIR)/%.c lv_conf.h
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -rf $(BUILD)

.PHONY: all clean
