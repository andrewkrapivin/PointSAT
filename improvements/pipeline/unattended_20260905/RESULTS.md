# Completed unattended PointSAT portfolio

The two-worker queue handled all120jobs from **06:16:20 to11:30:18UTC**, a
5h13m58s elapsed run. It produced **10 independently certified23-point
configurations and one exact threefold-symmetric19-point solution**.
The other compute queues were not changed or stopped.

The main result is [the exact19-point witness](../../success19/README.md): every
convex hexagon contains1,2,or4other points, never0or3. Its six orbit
representatives, algebraic coordinates, independent certificates, and original
2,311,196-clause CNF check are packaged there. It came from
`job013-symmetry19-target_margin`, sample4/job14; no new19-point audit was needed
for this summary.

## Denominators and logged work

"Samples" below means independently seeded SAT-generation requests. The valid
column includes failed/timed-out generation requests in its denominator, rather
than conditioning only on SAT models that were easy to obtain.

|Family|Jobs|Planned samples|SAT models|SAT timeouts|Native attempts|Valid samples|SAT worker s|Native worker s|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|23: no7-gon/no6-hole|40|240|240|0|315|10/240|1126.91|4620.18|
|19: exact C3 hexagon condition|20|80|12|67|35|1/80|6682.06|1031.17|
|32: no7-gon|20|120|120|0|121|0/120|107.58|1815.79|
|29: no6-hole|20|80|20|60|20|0/80|12743.19|300.12|
|26: no7-gon/no5-cap|20|120|120|0|465|0/120|51.10|6977.79|

There were640planned SAT requests:512SAT results,127timeouts, and one request
unstarted or unlogged when a job budget expired. There were956native attempts
and803feedback steps,445of which returned a SAT repair. Logged SAT and native
worker elapsed times total20710.84s and14745.05s. These are accumulated stage
wall times, **not CPU measurements**; parallel work overlaps in queue elapsed
time. Native-budget exhaustion ordinarily saves a PARTIAL checkpoint and is
not a wrapper timeout.

119jobs exited normally. The single600-second watchdog interrupted
`job097-symmetry19-target_margin` (exit130,600.477s); its process cleanup reported
no remaining tagged children. No logged pipeline errors or native-wrapper
timeouts occurred. All120post-job audits returned0, with11accepted certificates
and no rejected pipeline claims. Negative rows are bounded-search outcomes,
not nonexistence proofs.

## Search arms—not a fixed-work speed comparison

|23-point core-choice arm|Jobs|SAT samples|Native attempts|Valid samples|Native worker s|
|---|---:|---:|---:|---:|---:|
|Hash|13|78|122|6/78 (7.69%)|1746.41|
|Target-margin|27|162|193|4/162 (2.47%)|2873.77|

These arms use **different SAT seeds** and consume different amounts of feedback
and native work. Hash had the higher observed success fraction in this queue,
reversing the earlier small-pilot trend; this is not a matched experiment or
proof that one choice is superior. All other families used target-margin.

For29-point SAT generation, `--sat` produced5/28models, defaults4/28, and
`--plain`11/24; the remaining requests timed out. For19points, `--plain`
produced9/40models (30timeouts, one interrupted/unlogged request), versus
`--sat`3/40 (37timeouts). These also used different seeds.

The earlier fixed-work orchestration comparison remains separate: the same
eight SAT inputs and upstream native binary took91.945s before versus79.791s
after, with0/8successes in both versions. Its observed13.2%wall reduction is
not interchangeable with this queue's solve rates. See
[the earlier experiment report](../RESULTS_20260905.md).

## Ten exact23-point outputs and distinctness

Every row links an existing independent certificate and exact integer-scaled
coordinate file. All have general position, zero convex7-gons, zero empty
6-holes, and a full original519426-clause CNF extension checked clause by clause.

|Queue job / sample|Convex6-subsets|Exact coordinates|Independent certificate|
|---|---:|---|---|
|015 /2|645|[points](runs/job015-mixed23-hash/audit/sample2-job9/points.pts)|[certificate](runs/job015-mixed23-hash/audit/sample2-job9/certificate.json)|
|024 /6|617|[points](runs/job024-mixed23-hash/audit/sample6-job33/points.pts)|[certificate](runs/job024-mixed23-hash/audit/sample6-job33/certificate.json)|
|033 /2|620|[points](runs/job033-mixed23-hash/audit/sample2-job13/points.pts)|[certificate](runs/job033-mixed23-hash/audit/sample2-job13/certificate.json)|
|057 /6|546|[points](runs/job057-mixed23-target_margin/audit/sample6-job17/points.pts)|[certificate](runs/job057-mixed23-target_margin/audit/sample6-job17/certificate.json)|
|069 /2|647|[points](runs/job069-mixed23-hash/audit/sample2-job11/points.pts)|[certificate](runs/job069-mixed23-hash/audit/sample2-job11/certificate.json)|
|072 /2|801|[points](runs/job072-mixed23-target_margin/audit/sample2-job11/points.pts)|[certificate](runs/job072-mixed23-target_margin/audit/sample2-job11/certificate.json)|
|090 /6|496|[points](runs/job090-mixed23-target_margin/audit/sample6-job19/points.pts)|[certificate](runs/job090-mixed23-target_margin/audit/sample6-job19/certificate.json)|
|096 /1|662|[points](runs/job096-mixed23-hash/audit/sample1-job9/points.pts)|[certificate](runs/job096-mixed23-hash/audit/sample1-job9/certificate.json)|
|099 /1|577|[points](runs/job099-mixed23-target_margin/audit/sample1-job7/points.pts)|[certificate](runs/job099-mixed23-target_margin/audit/sample1-job7/certificate.json)|
|114 /6|708|[points](runs/job114-mixed23-hash/audit/sample6-job22/points.pts)|[certificate](runs/job114-mixed23-hash/audit/sample6-job22/certificate.json)|

An existing arbitrary-precision verifier enumerated all100947six-subsets for
each of these10and the earlier five23-point witnesses. It recorded the complete
histogram by number of interior points, not just convex6counts. The earlier
counts are772,591,642,606,and573. All15total counts are distinct, so the combined
collection has **at least15pairwise nonisomorphic order types**, even allowing
reflection. In particular, each overnight example differs from all five
earlier examples. Different histograms certify nonisomorphism; equal ones would
not prove isomorphism. No claim of novelty relative to the literature is made.

## Reproducibility

[aggregate.json](aggregate.json) contains every family/arm/SAT-mode denominator,
stage timing, accepted coordinate/certificate path and hash, all15exact
histograms, per-job totals, and watchdog metadata. The read-only aggregation
script is [aggregate_unattended.py](../aggregate_unattended.py); it runs the
existing exhaustive geometry checker for invariants, **no search or SAT solver**.
Original logs, frozen code, configurations, and proof cuts were left unchanged.
