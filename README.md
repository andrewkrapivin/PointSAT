# PointSAT
Problems complete for the existential theory of the reals arise throughout discrete geometry. We introduce *satisfiability modulo realizability*, a SAT-based approach for solving satisfiable instances of the existential theorem of the reals whose solutions correspond to realizable geometric configurations. Our method encodes an underapproximation of a geometric problem as a SAT instance over abstract order types. Since almost all abstract order types are unrealizable, naive search is infeasible. We guide the search toward realizable order types using diversity-driven sampling, partial realizability feedback, and a novel flippability heuristic that passes only limited information between components. We apply our method to discrete geometry problems and resolve an open problem by showing that the largest set of points avoiding empty convex hexagons and convex heptagons is of size 23.

## Installing/Building Dependencies
We assume you have python and some C and C++ compiler installed.
- first, install the required packages: ```pip install -r requirements.txt```
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

## Running PointSAT
To run PointSAT on a local machine, make sure you have installed dependencies
as above. Then simply run:
```
python PointSAT.py settings.json
```
By default, this generates 500 abstract solutions for the 23 point 6-hole
7-gon problem and runs the localizer for
15 seconds on 1 thread. The total number of threads working on this is set to 4.
However, all these settings can be modified in the settings.json file.
The most relevant settings in settings.json are:
- "n": number of points in the problem
- "base_file": this gives the constraints for your problem, which is used by
the SAT solver
- "n_solutions": number of abstract solutions
- "output_folder: the folder for the tool to use to log work and output realizations
- "workers": number of parallel workers. Note that this does not necessarily
equal the number of threads used by the program, as each worker may run localizer
on multiple threads.
- "worker_max_threads": number of threads to call localizer on. Note that the
SAT solver always uses one thread.
- "remove_flippable": whether or not to enable the heuristic to remove the flippable
variables

After PointSAT finishes, all realizations found (if any) will be found in the
realizations subdirectory of the specified output folder. The .or files correspond
to the orientation constraints, and the .real files correspond to the actual
realizations found.

## Additional Scripts
- analyze.py: ```python analyze.py [[output_folder]].``` This script analyzes the
results in the output folder of a PointSAT run. It generates in the same output
folder histograms for number of violations, number of flippable orientations,
probability of  being a solution versus number of violations, and the proportion
of solutions with a given number of violations. It also outputs the data used
to generate these graphs to a CSV.
