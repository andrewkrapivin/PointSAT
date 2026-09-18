CC ?= cc
PYTHON ?= python3
CFLAGS ?= -O3 -Wall -Wextra -std=gnu11 -pthread
LDFLAGS ?=
LDLIBS = -lm -pthread
SOURCES = $(wildcard src/*.c)
V6_SOURCES = $(wildcard baseline/v6/*.c)
UPSTREAM_SOURCES = $(wildcard baseline/upstream/*.c)

.PHONY: all baseline upstream variants test test-variants sanitize clean
all: build/localizer
baseline: build/localizer_v6
upstream: build/localizer_upstream
variants: build/localizer_sampling build/localizer_atomic build/localizer_both

build:
	mkdir -p build

build/localizer: $(SOURCES) | build
	$(CC) $(CFLAGS) src/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/localizer_v6: $(V6_SOURCES) | build
	$(CC) $(CFLAGS) baseline/v6/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/localizer_upstream: $(UPSTREAM_SOURCES) | build
	$(CC) $(CFLAGS) baseline/upstream/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/localizer_sampling: $(SOURCES) | build
	$(CC) $(CFLAGS) -DLOCALIZER_WEIGHT_SUM_FAST=1 -DLOCALIZER_ATOMIC_STOP=0 src/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/localizer_atomic: $(SOURCES) | build
	$(CC) $(CFLAGS) -DLOCALIZER_WEIGHT_SUM_FAST=0 -DLOCALIZER_ATOMIC_STOP=1 src/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/localizer_both: $(SOURCES) | build
	$(CC) $(CFLAGS) -DLOCALIZER_WEIGHT_SUM_FAST=1 -DLOCALIZER_ATOMIC_STOP=1 src/main.c $(LDFLAGS) -o $@ $(LDLIBS)

build/test_solver: $(SOURCES) | build
	$(CC) $(CFLAGS) src/test_solver.c $(LDFLAGS) -o $@ $(LDLIBS)

build/test_native: tests/native_tests.c $(SOURCES) | build
	$(CC) $(CFLAGS) tests/native_tests.c $(LDFLAGS) -o $@ $(LDLIBS)

test: all build/test_solver build/test_native
	./build/test_solver
	./build/test_native
	$(PYTHON) tests/test_cli.py --binary build/localizer

test-variants: all baseline variants
	$(PYTHON) tests/test_equivalence.py
	$(PYTHON) tests/test_cli.py --binary build/localizer_both

sanitize: | build
	$(CC) -O1 -g -std=gnu11 -pthread -fsanitize=address,undefined -fno-omit-frame-pointer tests/native_tests.c -o build/test_native_sanitize $(LDLIBS)
	ASAN_OPTIONS=detect_leaks=0 ./build/test_native_sanitize

clean:
	rm -f build/localizer build/localizer_v6 build/localizer_upstream build/localizer_sampling build/localizer_atomic build/localizer_both build/test_solver build/test_native build/test_native_sanitize
