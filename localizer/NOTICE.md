# Attribution and source boundaries

Localizer was developed by Bernardo Subercaseaux and upstream contributors at
https://github.com/bsubercaseaux/localizer. The pinned upstream commit is
`5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb`.

`baseline/upstream/` preserves the upstream C sources byte for byte.
`UPSTREAM_README.md` preserves its documentation. No upstream license grant was
found; see `LICENSE` before redistribution.

`baseline/v6/` preserves the previously measured PointSAT native v6 revision.
`src/` begins from that revision and contains the separately measured local
improvements documented in this folder. These are local research changes, not
an upstream release or a claim of upstream endorsement.

The package deliberately includes no nested Git repository, old result trees,
external vendor directory, or prebuilt executable. It builds with a C11-capable
compiler, POSIX threads, and libm. Python 3 is needed only for tests/benchmarks.
