from multiprocessing import Process, Queue, cpu_count
from pathlib import Path
import subprocess
import time
import os
import sys
import json
import shutil
import signal
from sat_orient_conversion import get_orientations, validate, split_line

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
    # print("Merged:", result)

# ["cadical", "--quiet"]
def run_external(task, program_params, timeout=None, kill_with_interrupt = False):
    """
    Run an external program with piped input and optional timeout.
    Returns (success: bool, stdout, stderr).
    """
    # print(timeout, kill_with_interrupt)
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
            # print("YAYAYAYAYAYAYAYAY")
            return True, stdout.strip(), stderr.strip(), elapsed
        else:
            return False, stdout.strip(), stderr.strip(), elapsed
    except subprocess.TimeoutExpired:
        # print("TIMEIMEIMTIEMTEIT")
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


def server(results_queue, work_queue, base_formula, subcases, num_workers, out_folder, n = 23):
    # maybe do something where can read out_file and have a fake worker temporarily so then you remove all the jobs already done
    
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
                "case": line,
                "meta": "initial_cube",
            }
            add_job(job)

    with open(out_file, "w", encoding="utf-8") as file:
        while True:
            if jobs_left == 0:
                break
            
            print(jobs_left, flush=True)
            result = results_queue.get()
            jobs_left -= 1
            print(json.dumps(result), file=file, flush=True)
            if result['type'] == "SAT" and result['meta'] == "initial_cube" and result['satisfiable']:
                orientations_file = os.path.join(scratch_folder, str(result['id']) +  ".or")
                realization_file = os.path.join(scratch_folder, str(result['id']) + "_" + str(cur_job_id) + ".real")
                with open(orientations_file, "w") as f:
                    f.write(get_orientations(split_line(result['solution']), n))
                job = {
                    "type": "Realize",
                    "orientations_file": orientations_file,
                    "realization_file": realization_file,
                    "meta": "initial_try",
                    "timeout": 15,
                    "original_id": result['id'],
                    "seed": 1,
                }
                add_job(job, result)
            if result['type'] == "Realize":
                orientations_file = os.path.join(scratch_folder, str(result['original_id']) + ".or")
                old_realization_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result['id']) + ".real")
                if result["realized"] == True:
                    results_realization_file = os.path.join(realizations_folder, str(result['original_id']) + "_" + str(result['id']) + ".real")
                    results_orientation_file = os.path.join(realizations_folder, str(result['original_id']) + ".or")
                    # shutil.move(old_realization_file, results_realization_file)
                    # shutil.move(orientations_file, results_orientation_file)
                    # shutil.move(old_realization_file+".png", results_realization_file+".png")
                    shutil.copy(old_realization_file, results_realization_file)
                    shutil.copy(orientations_file, results_orientation_file)
                    # shutil.copy(old_realization_file+".png", results_realization_file+".png")
                elif result["meta"] == "initial_try":
                    # os.remove(old_realization_file)
                    if result['violations'] <= 10:
                        add_job({
                                "realization_file": os.path.join(scratch_folder, 
                                str(result['original_id']) + "_" + str(cur_job_id) + ".real"), 
                                "meta": "second_try",
                                "timeout": 75,
                                "seed": 2,
                            }, 
                            result)
                    # else:
                    #     os.remove(orientations_file)
                elif result["meta"] == "second_try":
                    # os.remove(old_realization_file)
                    if result['violations'] <= 7:
                        add_job({
                                "realization_file": os.path.join(scratch_folder, 
                                str(result['original_id']) + "_" + str(cur_job_id) + ".real"), 
                                "meta": "third_try",
                                "timeout": 300,
                                "seed": 3
                            }, 
                            result)
                    # else:
                    #     os.remove(orientations_file)
                elif result["meta"] == "third_try":
                    if result['violations'] <= 4:
                        add_job({
                            "realization_file": os.path.join(scratch_folder, 
                            str(result['original_id']) + "_" + str(cur_job_id) + ".real"), 
                            "meta": "fourth_try",
                            "timeout": 1500,
                            "seed": 4
                        }, 
                        result)
                    # if result['violations'] <= 4:
                        # for s in range(2, 10):
                        #     add_job({
                        #         "realization_file": os.path.join(scratch_folder, 
                        #         str(result['original_id']) + "_" + str(cur_job_id) + ".real"), 
                        #         "meta": "fourth_try",
                        #         "timeout": 1500,
                        #         "seed": s
                        #     }, 
                        #     result)
                    add_job({
                        "type": "SAT_perturb",
                        "real_id": result["id"],
                    }, 
                    result)
                    # print(result)
                elif result["meta"] == "fourth_try":
                    add_job({
                            "type": "SAT_perturb",
                            "real_id": result["id"],
                        }, 
                        result)
            if result['type'] == "SAT_perturb" and result['satisfiable']:
                orientations_file = os.path.join(scratch_folder, str(result['original_id']) + ".or")
                old_realization_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".real")
                results_realization_file = os.path.join(realizations_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".real")
                results_orientation_file = os.path.join(realizations_folder, str(result['original_id']) + ".or")
                # shutil.move(old_realization_file, results_realization_file)
                # shutil.move(orientations_file, results_orientation_file)
                # shutil.move(old_realization_file+".png", results_realization_file+".png")
                shutil.copy(old_realization_file, results_realization_file)
                shutil.copy(orientations_file, results_orientation_file)
                perturbed_orientations_file = os.path.join(scratch_folder, str(result['original_id']) + "_" + str(result["real_id"]) + ".or")
                with open(perturbed_orientations_file, "w") as f:
                    f.write(get_orientations(split_line(result['solution']), n))
                # no image generated in this case so gotta check it manually with validator later
                # shutil.copy(old_realization_file+".png", results_realization_file+".png")
                

        # when done tell workers to stop
        for _ in range(num_workers):
            work_queue.put(None)

def worker(work_queue, result_queue, base_formula, out_file):
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

                lines = base_formula.splitlines()
                first_line = lines[0].split()
                first_line[3] = str(int(first_line[3]) + len(job_case) - 2)
                lines[0] = " ".join(first_line)
                for var in job_case[1:-1]:
                    lines.append(f"{var} 0")
                formula = "\n".join(lines)
                # print(formula, file = file)
                # input()

                success, out, err, elapsed = run_external(formula, ["cadical", "--quiet"], timeout=None)
                out_p = process_sat_str(out)
                # print(success, out_p)
                if success and (out_p != ""):
                    job['satisfiable'] = True
                    job['solution'] = out_p
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
                commands = ["./localizer", job["orientations_file"], "-t", "1", "-i", "10", "-r", "30000", "-s", str(job["seed"]), "-o", job["realization_file"]]
                success, out, err, elapsed = run_external("", commands, timeout=job["timeout"], kill_with_interrupt=True)
                valid, bad_vars = validate(job["orientations_file"], job["realization_file"])
                job['realized'] = valid
                job['violations'] = len(bad_vars)
                job['bad_vars'] = bad_vars
                result_queue.put(job)

def signal_handler(sig, frame):
    print(f"Received signal {sig}, exiting")
    sys.exit(1)


if __name__ == "__main__":
    # os.setsid() 
    base_file = sys.argv[1]
    subcases = sys.argv[2]
    num_threads = 4 if len(sys.argv) < 4 else int(sys.argv[3])
    output_folder = "out" if len(sys.argv) < 5 else sys.argv[4]
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    num_workers = max(num_threads - 1, 1)  # One core reserved for server. Prolly unecessary as server is light

    result_queue = Queue()
    work_queue = Queue()

    with open(base_file, "r", encoding="utf-8") as file:
        base_formula = file.read()
    
    server_proc = Process(target=server, args=(result_queue, work_queue, base_formula, subcases, num_workers, output_folder))
    server_proc.start()

    worker_procs = []
    for i in range(num_workers):
        p = Process(target=worker, args=(work_queue, result_queue, base_formula, os.path.join(output_folder, "worker_" + str(i) + ".jsonl")))
        p.start()
        worker_procs.append(p)


    server_proc.join()

    for p in worker_procs:
        p.join()

    print("✅ All tasks completed.")
