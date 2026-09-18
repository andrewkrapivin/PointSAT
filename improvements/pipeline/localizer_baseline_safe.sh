#!/bin/sh
# Explicit empty fixed/symmetry files avoid uninitialized upstream CLI pointers.
exec ./improvements/localizer/localizer_baseline "$@" -f improvements/pipeline/empty.input -c improvements/pipeline/empty.input
