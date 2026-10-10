# Opengrep perf scripts

## `bench.py`

Run a quick comparison of performance between two commits or a commit and the current state of the world (current commit + uncommitted changes). Usage:

```
bench <sha1> <sha2>  # compare two commits
bench <sha1>         # compare a commit with the current state of the world
```

E.g.

```
./bench.py 3f4f1459c6caa1dea105207a49f8784f9deeeefd 
```

The script will checkout the shas in the current repo.

When comparing two shas:

1. The uncommited changes are stashed

2. `sha1` is checked out, compiled, and benchmarked

3. `sha2 `is checked out, compiled, and benchmarked

4. The original branch is checked out, changes are popped from the stash

When comparing a sha with the current state of the world

1. The uncommited changes are stashed

2. `sha1` is checked out, compiled, and benchmarked

3. The original branch is checked out, changes are popped from the stash

4. We compile and benchmark

So, the script leaves the world in the original state without having to commit changes or run `make setup` in a fresh clone, which takes forever. However, if script fails for some reason, we need to manually checkout the original branch, **pop the stash** and recompile.

Results printed to std out and are stored in `opengrep/perf/opengrep-scripts/results` as a csv file.
