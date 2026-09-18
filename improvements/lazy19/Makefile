CXX ?= g++
CXXFLAGS ?= -O3 -march=native -std=c++17 -Wall -Wextra
all: audit gradient
audit: audit.cpp
	$(CXX) $(CXXFLAGS) $< -o $@
gradient: gradient.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

.PHONY: clean
clean:
	$(RM) audit gradient
