from multiprocessing import Process, Queue, cpu_count
from pathlib import Path
import subprocess
import time
import os
import sys
import json
import shutil
import signal
import random
from sat_orient_conversion import get_orientations, validate, split_line, get_sat_model
from flippable2 import check_flippable
import argparse

TIMEOUT_SECONDS = 10

def process_sat_str(data):
    lines = [line.strip() for line in data.splitlines() if line.strip()]

    # Find the satisfiability line
    sat_status = None
    for line in lines:
        if line.startswith("s "):
            if "UNSATISFIABLE" in line:
                sat_status = "UNSATISFIABLE"
                return ""

    # Filter out the 's' line
    v_lines = [line for line in lines if not line.startswith("s ")]

    nums = []
    for line in v_lines:
        parts = line.split()
        if parts[0] == "v":
            parts = parts[1:]  # remove the leading 'v'
        nums.extend(map(int, parts))

    # Step 5: Filter out numbers > 1771
    nums = [n for n in nums if abs(n) <= 1771]
    if len(nums) == 0:
        print("gamer", data)
        return ""

    # Step 6: Build the output string, keeping the first 'v'
    result = "v " + " ".join(map(str, nums))
    return result

def run_external(task, program_params, timeout=None, kill_with_interrupt = False):
    """
    Run an external program with piped input and optional timeout.
    Returns (success: bool, stdout, stderr).
    """
    start = time.perf_counter()
    try:
        process = subprocess.Popen(
            program_params,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=task, timeout=timeout)
        elapsed = time.perf_counter() - start
        if process.returncode >= 0:
            return True, stdout.strip(), stderr.strip(), elapsed
        else:
            return False, stdout.strip(), stderr.strip(), elapsed
    except subprocess.TimeoutExpired:
        if kill_with_interrupt:
            os.kill(process.pid, signal.SIGINT)
        else:
            process.kill()
        process.wait()
        elapsed = time.perf_counter() - start
        return False, None, f"Timeout after {timeout}s", elapsed
    except Exception as e:
        print ("AFAFAFAF", str(e))
        elapsed = time.perf_counter() - start
        return False, None, str(e), elapsed


def server(results_queue, work_queue, base_formula, settings, n = 23):
    subcases = settings["cubes_file"]
    out_folder = settings["output_folder"]
    os.makedirs(out_folder, exist_ok=True)
    out_file = os.path.join(out_folder, "raw_results.jsonl")
    scratch_folder = os.path.join(out_folder, "scratch")
    os.makedirs(scratch_folder, exist_ok=True)
    realizations_folder = os.path.join(out_folder, "realizations")
    os.makedirs(realizations_folder, exist_ok=True)

    cur_job_id = 1
    jobs_left = 0
    finished_jobs = {}
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as file:
            for line in file:
                finished_job = json.loads(line)
                finished_jobs[int(finished_job["id"])] = finished_job
    def add_job(job, old_job = {}):
        nonlocal cur_job_id, jobs_left, finished_jobs
        new_job = {}
        for k, v in old_job.items():
            # print(k, v)
            new_job[k] = v
        for k, v in job.items():
            # print(k, v)
            new_job[k] = v
        new_job["id"] = cur_job_id
        if cur_job_id in finished_jobs:
            results_queue.put(finished_jobs[cur_job_id])
        else:
            work_queue.put(new_job)
        jobs_left += 1
        cur_job_id += 1
    # work_left = {}
    
    with open(subcases, "r", encoding="utf-8") as file:
        for line in file:
            job = {
                "type": "SAT",
                "remove_flippable": settings['remove_flippable'],
                "case": line,
                "meta": "initial_cube",
            }
            add_job(job)

    localizer_attempt_names = {
        "initial_try": 1,
        "second_try": 2,
        "third_try": 3,
        "fourth_try": 4,
    }
    localizer_attempt_inverse = {
        1: "second_try",
        2: "third_try",
        3: "fourth_try"
    }
    with open(out_file, "w", encoding="utf-8") as file:
        while True:
            if jobs_left == 0:
                break
            
            print(jobs_left, flush=True)
            result = results_queue.get()
            jobs_left -= 1
            print(json.dumps(result), file=file, flush=True)
            if result['type'] == "SAT" and result['meta'] == "initial_cube" and result['satisfiable']:
                if settings['localizer_attempt_levels'] > 0:
                    # print(settings['localizer_attempt_levels'])
                    orientations_file = os.path.join(scratch_folder, str(result['id']) +  ".or")
                    realization_file = os.path.join(scratch_folder, str(result['id']) + "_" + str(cur_job_id) + ".real")
                    with open(orientations_file, "w") as f:
                        f.write(get_orientations(split_line(result['solution']), n))
                    job = {
                        "type": "Realize",
                        "check_sat": True,
                        "orientations_file": orientations_file,
                        "realization_file": realization_file,
                        "meta": "initial_try",
                        "timeout": 15,
                        "original_id": result['id'],
                        "seed": 1,
                        "threads": settings["worker_max_threads"]
                    }
                    add_job(job, result)
            if result['type'] == "Realize":
                orientations_file = os.path.join(scratch_folder, str(result['original_id']) + ".or")
                old_realization_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result['id']) + ".real")
                if result["realized"] == True:
                    results_realization_file = os.path.join(realizations_folder, str(result['original_id']) + "_" + str(result['id']) + ".real")
                    results_orientation_file = os.path.join(realizations_folder, str(result['original_id']) + ".or")
                    shutil.copy(old_realization_file, results_realization_file)
                    shutil.copy(orientations_file, results_orientation_file)
                    # shutil.copy(old_realization_file+".png", results_realization_file+".png")
                else:
                    if ("check_sat" not in result) or (not result["check_sat"]):
                        add_job({
                            "type": "SAT_perturb",
                            "real_id": result["id"],
                        }, 
                        result)
                if result["meta"] in localizer_attempt_names and ((not result['realized']) or settings['continue_if_realized']):
                    ati = localizer_attempt_names[result['meta']]
                    if settings['localizer_attempt_levels'] > ati and (result['violations'] <= settings["localizer_attempt_thresholds"][ati-1] or settings['continue_if_realized']):
                        for i in range(settings['localizer_attempt_branches'][ati-1]):
                            add_job({
                                    "realization_file": os.path.join(scratch_folder, 
                                    str(result['original_id']) + "_" + str(cur_job_id) + ".real"), 
                                    "meta": localizer_next_attempt[ati],
                                    "timeout": settings['localizer_attempt_timeouts'][ati],
                                    "seed": random.getrandbits(32),
                                    "threads": settings["worker_max_threads"],
                                    "sat_is_realized": True,
                                }, 
                                result)
            # if result['type'] == "SAT_perturb" and result['satisfiable']:
            #     orientations_file = os.path.join(scratch_folder, str(result['original_id']) + ".or")
            #     old_realization_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".real")
            #     results_realization_file = os.path.join(realizations_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".real")
            #     results_orientation_file = os.path.join(realizations_folder, str(result['original_id']) + ".or")
            #     shutil.copy(old_realization_file, results_realization_file)
            #     shutil.copy(orientations_file, results_orientation_file)
            #     perturbed_orientations_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".or")
            #     with open(perturbed_orientations_file, "w") as f:
            #         f.write(get_orientations(split_line(result['solution']), n))
                

        # when done tell workers to stop
        for _ in range(settings["workers"]):
            work_queue.put(None)

def check_sat_case(base_formula, assumptions, settings):
    lines = base_formula.splitlines()
    first_line = lines[0].split()
    first_line[3] = str(int(first_line[3]) + len(assumptions))
    lines[0] = " ".join(first_line)
    for var in assumptions:
        lines.append(f"{var} 0")
    formula = "\n".join(lines)

    success, out, err, elapsed = run_external(formula, ["./"+settings['cadical_loc'], "--quiet"], timeout=None)
    out_p = process_sat_str(out)
    return success,out,err,elapsed,out_p

def worker(work_queue, result_queue, base_formula, out_file, settings):
    with open(out_file, "w", encoding="utf-8") as file:
        while True:
            job = work_queue.get()
            # print("hello", case)
            if job is None:
                break

            # print(job)
            if job["type"] == "SAT" or job["type"] == "SAT_perturb":
                if job["type"] == "SAT":
                    # print("Hello", job['case'])
                    job_case = job["case"].split()
                if job["type"] == "SAT_perturb":
                    job_case = job['solution'].split()
                    for i in job["bad_vars"]:
                        # print(job_case[i], i)
                        job_case[i] = -int(job_case[i])

                # lines = base_formula.splitlines()
                # first_line = lines[0].split()
                # first_line[3] = str(int(first_line[3]) + len(job_case) - 2)
                # lines[0] = " ".join(first_line)
                # for var in job_case[1:-1]:
                #     lines.append(f"{var} 0")
                # formula = "\n".join(lines)
                # # print(formula, file = file)
                # # input()

                # success, out, err, elapsed = run_external(formula, ["cadical", "--quiet"], timeout=None)
                # out_p = process_sat_str(out)
                success,out,err,elapsed,out_p = check_sat_case(base_formula, job_case[1:-1], settings)
                # print(success, out_p)
                if success and (out_p != ""):
                    job['satisfiable'] = True
                    job['solution'] = out_p
                    if job['remove_flippable']:
                        flippable, non_flippable = check_flippable(base_formula, job['solution'])
                        job['original_solution'] = job['solution']
                        job['flippable'] = list(flippable)
                        job['solution'] = "v " + " ".join([str(i) for i in non_flippable]) + " 0"
                    # if job["type"] == "SAT": 
                    #     print("satisfied", job['case'])
                    print(job['solution'], file = file, flush=True)
                else:
                    job['satisfiable'] = False
                result_queue.put(job)
            elif job["type"] == "Realize":
                seed = 42
                if "seed" in job:
                    seed = job["seed"]
                commands = ["./"+settings['localizer_loc'], job["orientations_file"], "-t", str(job['threads']), "-i", "10", "-r", "30000", "-s", str(seed), "-o", job["realization_file"]]
                success, out, err, elapsed = run_external("", commands, timeout=job["timeout"], kill_with_interrupt=True)
                valid, bad_vars = validate(job["orientations_file"], job["realization_file"])
                if job['check_sat']:
                    sat_model = get_sat_model(job["realization_file"])
                    success,out,err,elapsed,out_p = check_sat_case(base_formula, sat_model, settings)
                    if success and (out_p != ""):
                        job['realized'] = True
                    else:
                        job['realized'] = False
                else:
                    job['realized'] = valid
                job['violations'] = len(bad_vars)
                job['bad_vars'] = bad_vars
                result_queue.put(job)
    
    # tell workers to stop when done
    for _ in range(num_workers):
            work_queue.put(None)

def signal_handler(sig, frame):
    print(f"Received signal {sig}, exiting")
    sys.exit(1)


parser = argparse.ArgumentParser(
    description='A script to automatically try to find realizations for a given combinatorial encoding of sat formula. Tries over all cubes given.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument('settings_file', help='Settings filename. Additional arguments are to override the settings file.')
parser.add_argument('--base', help="The base CNF file to parse")
parser.add_argument('--cubes', help="The filename that stores all the cubes to test.")
parser.add_argument('--out', help='Output folder.')
parser.add_argument('--workers', type=int, help='Number of threads.')
parser.add_argument('--worker_max_threads', type=int, help='Max threads per worker.')
parser.add_argument('-n', type=int, help='Number of points in the encoding (NOT YET WORKING; FIXED AT 23 FOR NOW). Note that orientations are assumed to be given as in orient.c in the 7gon stuff')

if __name__ == "__main__":
    # os.setsid() 
    # if len(sys.argv) > 1:
    args = parser.parse_args()
    with open(args.settings_file, "r") as file:
        settings = json.load(file)
    
    default_settings = {
        "output_folder": "out",
        "workers": 1,
        "remove_flippable": True,
        "worker_max_threads": 1,
        "localizer_attempt_levels": 4,
        "localizer_attempt_timeouts": [15, 75, 300, 1500],
        "localizer_attempt_branches": [1, 1, 1, 1],
        "localizer_attempt_thresholds": [10, 7, 4],
        "n": 23,
        "localizer_loc": "localizer/src/localizer",
        "cadical_loc": "cadical/debug/cadical",
        'continue_if_realized': True
        # need to figure out best way to do this setting. Something like check to make sure the settings in the output folder are the same as the settings here.
        # "continue_existing": True
    }
    for k, v in default_settings.items():
        if k not in settings:
            settings[k] = v
    if args.base is not None:
        settings['base_file'] = args.base
    if args.cubes is not None:
        settings['cubes_file'] = args.cubes
    if args.out is not None:
        settings['output_folder'] = args.out
    if args.workers is not None:
        settings['workers'] = args.workers
    if args.worker_max_threads is not None:
        settings['worker_max_threads'] = args.worker_max_threads
   
    Path(settings["output_folder"]).mkdir(parents=True, exist_ok=True)
    num_workers = settings["workers"]

    result_queue = Queue()
    work_queue = Queue()

    base_file = settings["base_file"]
    output_folder = settings["output_folder"]
    with open(os.path.join(output_folder, "settings.json"), "w") as settings_file:
        json.dump(settings, settings_file)

    with open(base_file, "r", encoding="utf-8") as file:
        base_formula = file.read()
    
    server_proc = Process(target=server, args=(result_queue, work_queue, base_formula, settings))
    server_proc.start()

    worker_procs = []
    for i in range(num_workers):
        p = Process(target=worker, args=(work_queue, result_queue, base_formula, os.path.join(output_folder, "worker_" + str(i) + ".jsonl"), settings))
        p.start()
        worker_procs.append(p)


    server_proc.join()

    for p in worker_procs:
        p.join()

    print("✅ All tasks completed.")
