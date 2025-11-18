#!/bin/bash

CUBES=$1
DIR="$PROJECT/realizations23no6holeno7gon/${1%.*}"
echo $DIR

python run_parallel2.py settings.json --cubes $CUBES --out $DIR
