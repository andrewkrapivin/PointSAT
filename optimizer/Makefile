CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wno-unused-function

all: compact compact_v2
# Keep the translation-unit basename identical to the frozen v1 build. This
# reproduces its ELF hash with the original compiler, not just its behavior.
compact: compact_v1.cpp ../direct/search.cpp
	@optimizer_build_dir=$$(mktemp -d /tmp/pointsat-optimizer-build.XXXXXX) || exit 1; \
	cp compact_v1.cpp "$$optimizer_build_dir/compact.cpp"; \
	$(CXX) $(CXXFLAGS) -iquote "$(CURDIR)" "$$optimizer_build_dir/compact.cpp" -o compact; \
	optimizer_build_status=$$?; \
	rm -- "$$optimizer_build_dir/compact.cpp"; rmdir -- "$$optimizer_build_dir"; \
	exit $$optimizer_build_status
compact_v2: compact.cpp ../direct/search.cpp
	$(CXX) $(CXXFLAGS) compact.cpp -o compact_v2
test: all
	python3 tests.py --binary ./compact
	python3 tests.py --binary ./compact_v2 --experimental
.PHONY: all test
