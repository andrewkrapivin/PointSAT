CXX ?= g++
CXXFLAGS ?= -O3 -march=native -std=c++17 -Wall -Wextra
PROGRAMS = search verify overmars compact construct triangle subset pool
BIG_CPPFLAGS = $(if $(wildcard vendor/boost/usr/include/boost/multiprecision/cpp_int.hpp),-Ivendor/boost/usr/include,)

.PHONY: all exact test
all: $(PROGRAMS)

triangle: triangle.cpp search.cpp
	$(CXX) $(CXXFLAGS) triangle.cpp -o $@

pool: pool.cpp subset.cpp
	$(CXX) $(CXXFLAGS) pool.cpp -o $@

exact: arrangement verify_big coupled

arrangement: arrangement.cpp overmars.cpp
	$(CXX) $(CXXFLAGS) $(BIG_CPPFLAGS) arrangement.cpp -o $@

verify_big: verify_big.cpp
	$(CXX) $(CXXFLAGS) $(BIG_CPPFLAGS) verify_big.cpp -o $@

coupled: coupled.cpp arrangement.cpp overmars.cpp
	$(CXX) $(CXXFLAGS) $(BIG_CPPFLAGS) coupled.cpp -o $@

%: %.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

test: all
	./verify --self-test
	python3 test_oracles.py --verify ./verify --search ./search --overmars ./overmars
	python3 test_verify.py --verify ./verify
