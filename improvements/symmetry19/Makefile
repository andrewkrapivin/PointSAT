CXX ?= g++
CXXFLAGS ?= -O3 -march=native -std=c++17 -Wall -Wextra
BOOST = $(if $(wildcard ../../direct/vendor/boost/usr/include/boost/multiprecision/cpp_int.hpp),-I../../direct/vendor/boost/usr/include,)
verify_hexagons: verify_hexagons.cpp
	$(CXX) $(CXXFLAGS) $(BOOST) $< -o $@
