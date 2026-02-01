# ASMR
Automated satisfiability modulo realization


## Running ASMR
- clone and build localizer. Before running make in the makefile in localizer/src modify line 2 of the makefile from `CFLAGS = -Wall -Wextra -O3` to `CFLAGS = -Wall -Wextra -O3 -pthread` (the following does exactly that, so you do not need to do it yourself):
```
git clone https://github.com/bsubercaseaux/localizer/
cd localizer/src
sed -i '2c\CFLAGS = -Wall -Wextra -O3 -pthread' makefile
make
cd ../..
```
- clone and build scranfilize
```
git clone https://github.com/arminbiere/scranfilize
cd scranfilize
./configure && make
cd ..
```
- clone and build kissat (or cadical or whatever sat solver you choose)
```
git clone https://github.com/arminbiere/kissat
cd kissat
./configure && make
cd ..
```