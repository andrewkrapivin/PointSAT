#!/bin/bash

# --- SBATCH Directives ---

# Job name
#SBATCH --job-name=sat_asmr
#SBATCH -A cis230065p
#SBATCH -N 1
#SBATCH -p RM

# Output and error files (optional, but good practice)
# %j will be replaced with the job ID
#SBATCH --output=my_job_%j.out
#SBATCH --error=my_job_%j.err

# **CRITICAL: Request exactly one node**
# This is the most important line to ensure you only use a single node.

# **CRITICAL: Request a single task (process) on that node**
# Your Python script is one task.
#SBATCH --ntasks-per-node=1

# **CRITICAL: Request multiple CPUs for that single task**
# This is how you allocate cores for your threads.
# Change '8' to the number of threads you want your script to use.
#SBATCH --cpus-per-task=128

# Request memory for the job (e.g., 8GB)
# Adjust this based on your script's needs.
#SBATCH --mem=128G

# Set a time limit for the job (e.g., 1 hour)
# Format: HH:MM:SS
#SBATCH --time=48:00:00

# --- End of SBATCH Directives ---

# --- Job Environment Setup ---

echo "Job started on $(hostname)"
echo "Running on a single node with $SLURM_CPUS_PER_TASK CPUs allocated."

# 1. Load any necessary modules (e.g., a specific Python version)
# (Uncomment and modify if needed by your cluster)
module load anaconda3
conda activate asmr

# 2. Activate your virtual environment (e.g., conda or venv)
# (Uncomment and modify if needed)
# source activate my_conda_env
# OR
# source /path/to/my_venv/bin/activate

# --- Run the Python Script ---

# Run your multithreaded Python script.
#
# IMPORTANT:
# Your Python script should be written to respect the number of CPUs
# allocated by Slurm. You can get this number from the
# 'SLURM_CPUS_PER_TASK' environment variable.
#
# Example in Python:
# import os
# # Get the number of CPUs from Slurm, default to 1 if not set
# num_threads = int(os.environ.get('SLURM_CPUS_PER_TASK', 1))
# print(f"Using {num_threads} threads.")
# # Now, use 'num_threads' to configure your thread pool
# # (e.g., in ThreadPoolExecutor, numpy, pandas, etc.)

CUBES=$1
[[ "$#" -ge 3 ]] && SETTINGS="$2" || SETTINGS="settings.json"
DIR="$PROJECT/realizations/${1%.*}"
echo $DIR

python SMR.py $SETTINGS --cubes $CUBES --out $DIR

echo "Job finished."