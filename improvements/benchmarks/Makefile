CXX ?= g++
CXXFLAGS ?= -O3 -march=native -std=c++17 -Wall -Wextra
BOOST_INCLUDE := ../../direct/vendor/boost/usr/include

.PHONY: all test
all: verify_c3

verify_c3: verify_c3.cpp
	$(CXX) $(CXXFLAGS) -I $(BOOST_INCLUDE) $< -o $@

test: verify_c3
	./verify_c3 --self-test
	python3 test_audit.py
	python3 test_cap_projection.py
	python3 test_c3.py
	python3 test_matched_stop.py
