# ASMR
Automated satisfiability modulo realization


## Running ASMR
- clone and build localizer:
```
git clone https://github.com/bsubercaseaux/localizer/
cd localizer/src
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