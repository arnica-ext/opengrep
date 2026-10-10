#!/usr/bin/env python3

import os
import subprocess
import sys
import time
import csv
from urllib.parse import urlparse
from datetime import datetime
import statistics
import resource

# SETUP

# TODO: make some of these cli options?

repeat_each_test_n_times = 3

semgrep_command = "semgrep"

opengrep_command = "opengrep"

repositories = [ ("https://github.com/golang/go","93e3d5dc5f2af317c874fd61cbd354409ea9fd33")
               , ("https://github.com/grafana/grafana", "afcb55156260fe1887c4731e6cc4c155cc8281a2")
               , ("https://github.com/rust-lang/rust","0f73f0f3941e6be6b19721548fab4e2bf919a525")
               , ("https://github.com/torvalds/linux","01f95500a162fca88cefab9ed64ceded5afabc12")
               , ("https://github.com/tensorflow/tensorflow","71691c769e76655e5b2b869f258572d1e8febe64")
               , ("https://github.com/nodejs/node","f275121b72916d0c0a8b017b7677ddd6e2573e46")
               , ("https://github.com/kubernetes/kubernetes","2ac0bdf360cf2529a3675c7012d0bf415e1051f3")
               ]

num_cpus = str(max(1, os.cpu_count() - 1))

def regular_cmd(cmd, repo):
    return [cmd, "scan",
            "-c", "rules",
            repo,
            "-j", num_cpus,
            "--timeout", "0",
            "--max-memory", "4000",
            "--metrics", "off",
            "--max-target-bytes", "200000",
            "--quiet"
            ]

# Implementation

ts = datetime.now().strftime('%Y%m%d-%H%M%S')

def log_to_file(msg):
    with open(f"results/log-{ts}.txt", 'a') as file:
        file.write(msg)

def show_num(n):
    return f"{n:.2f}"

def get_repo_name(repo_url):
    path = urlparse(repo_url).path
    repo_name = os.path.splitext(os.path.basename(path))[0]
    return repo_name

repos = [{"url": url, "sha": sha, "name": get_repo_name(url)}
         for (url, sha) in repositories]

def run(cmd, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    sys.stdout.flush()
    subprocess.run(cmd, cwd=cwd, check=True)

def run_command_with_stdout(command):
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    return result.stdout

def clone_specific_commit(repo_url, commit_hash, name):
    if os.path.exists(name):
        print(f"Repository '{name}' present.")

    else:
        print(f"Cloning {repo_url} into {name} (shallow)...")
        run(["git", "clone", "--no-checkout", "--depth", "1", repo_url, name])

        print(f"Fetching commit {commit_hash}...")
        run(["git", "fetch", "--depth", "1", "origin", commit_hash], cwd=name)

        print(f"Checking out commit {commit_hash}...")
        run(["git", "checkout", commit_hash], cwd=name)

        print(f"Done: {name} at commit {commit_hash}")

def setup():
    os.makedirs("results", exist_ok=True)

    clone_specific_commit("https://github.com/opengrep/opengrep-rules", "f1d2b562b414783763fd02a6ed2736eaed622efa", "rules")

    run(["rm", "-f", "stats/web_frameworks.yml"], cwd="rules")
    run(["rm", "-f", "stats/cwe_to_metacategory.yml"], cwd="rules")
    run(["rm", "-f", "stats/metacategory_to_support_tier.yml"], cwd="rules")
    run(["rm", "-f", ".github/stale.yml"], cwd="rules")
    run(["rm", "-f", ".github/workflows/semgrep-rule-lints.yaml"], cwd="rules")
    run(["rm", "-f", ".github/workflows/validate-registry-metadata.yaml"], cwd="rules")
    run(["rm", "-f", ".github/workflows/semgrep-rules-test.yml"], cwd="rules")
    run(["rm", "-f", ".github/workflows/pre-commit.yml"], cwd="rules")
    run(["rm", "-f", "template.yaml"], cwd="rules")
    run(["rm", "-f", ".pre-commit-config.yaml"], cwd="rules")

    for r in repos:
      clone_specific_commit(r["url"], r["sha"], "repos/" + r["name"])

def single_run(cmd, repo):
    # sleeping gives the os time to clean up after the prev run (makes a difference on linux)
    time.sleep(10)

    # record run time in a more robust fashion than simply measuring real clock seconds
    usage_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    run(regular_cmd(cmd, repo))
    usage_end = resource.getrusage(resource.RUSAGE_CHILDREN)

    time.sleep(10)
    user_time = usage_end.ru_utime - usage_start.ru_utime
    system_time = usage_end.ru_stime - usage_start.ru_stime
    total_cpu_time = user_time + system_time
    log_to_file(f"- run completed for {cmd} on {repo}. user: {show_num(user_time)}, system: {show_num(system_time)}, total: {show_num(total_cpu_time)}\n")
    return total_cpu_time

def run_opengrep(cmd1, cmd2, repo):
    durs = [(single_run(cmd1, repo), single_run(cmd2, repo))
             for x in range(0, repeat_each_test_n_times)]
    durs1 = [x for (x,_) in durs]
    durs2 = [y for (_,y) in durs]
    return (statistics.mean(durs1), statistics.mean(durs2))

def run_bench(cmd1, cmd2):
    res = [{"name": r["name"], "durations": run_opengrep(cmd1, cmd2, "repos/" + r["name"])} for r in repos]
    return [{"name": r["name"], cmd1: r["durations"][0], cmd2: r["durations"][1]} for r in res]

def report_results(cmd1, cmd2, res):
    with_stats = [{"name": r["name"],
                   cmd1: f"{r[cmd1]:.2f}",
                   cmd2: f"{r[cmd2]:.2f}",
                   "diff(s)": f"{(r[cmd2] - r[cmd1]):.2f}",
                   "diff(%)": f"{(100 * (r[cmd2] - r[cmd1]) / r[cmd1]):.2f}"}
                  for r in res]
    # print to screen
    print("\n--------- BENCHMARK RUN COMPLETED ---------\n")
    for e in with_stats:
        print(e)
    # save to csv
    print("\nsaving to csv...")
    with open(f"results/results-{ts}.csv", 'w', newline='') as csvfile:
        fieldnames = with_stats[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(with_stats)

def which_and_version(cmd):
    which = run_command_with_stdout(f"which {cmd}").rstrip()
    print(f"which {cmd}: {which}")
    log_to_file(f"which {cmd}: {which}")
    ver = run_command_with_stdout(f"{cmd} --version").rstrip()
    print(f"version {cmd}: {ver}")
    log_to_file(f"version {cmd}: {ver}")

def go():
    setup()
    log_to_file(f"OPENGREP vs SEMGREP TEST {ts}\n\n")

    which_and_version(semgrep_command)
    which_and_version(opengrep_command)

    res = run_bench(semgrep_command, opengrep_command)
    report_results(semgrep_command, opengrep_command, res)

go()
