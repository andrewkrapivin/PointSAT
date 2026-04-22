import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
from pathlib import Path
import os

def analyze_time_taken(output_folder, num_bins = 50):
    """
    Reads a JSONL file, extracts 'time_taken' and 'satisfiable'.
    Plots:
      1. Histogram of Satisfiable instances (Log10 scale).
      2. Histogram of Unsatisfiable instances (Log10 scale).
      3. 'Effective Time' curve with readable Y-axis ticks.
         Also prints the Optimal Timeout to the console.
    """
    out_file = os.path.join(output_folder, "raw_results.jsonl")
    input_path = Path(out_file)
    
    if not input_path.exists():
        print(f"Error: The file '{jsonl_path}' was not found.")
        return

    # Store RAW values
    total_time = 0
    sat_raw = []
    unsat_raw = []

    print(f"Reading {input_path.name}...")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "time_taken" in data and "satisfiable" in data and data['type'] == "SAT":
                        val = float(data["time_taken"])
                        is_sat = data["satisfiable"]
                        
                        if val > 0:
                            total_time += val
                            if is_sat:
                                sat_raw.append(val)
                            else:
                                unsat_raw.append(val)
                                
                except (json.JSONDecodeError, ValueError):
                    pass

    except Exception as e:
        print(f"An error occurred reading the file: {e}")
        return

    print("total time for satttingg", total_time)

    if not sat_raw and not unsat_raw:
        print("No valid positive data found.")
        return

    # --- Global Binning Strategy ---
    all_raw = sat_raw + unsat_raw
    all_log = np.log10(all_raw)
    
    global_min = np.min(all_log)
    global_max = np.max(all_log)
    
    # Create 50 bins spanning the entire range of data
    common_bins = np.linspace(global_min, global_max, num_bins)

    # --- Stats for Satisfiable ---
    sat_arr = np.array(sat_raw)
    if len(sat_arr) > 0:
        sat_mean = np.mean(sat_arr)
    else:
        sat_mean = 0

    # --- Helper to plot Effectiveness Ratio ---
    def plot_effectiveness(ax, sat_data, bins, num_unsat, total_unsat_time):
        if not sat_data:
            ax.text(0.5, 0.5, "No Satisfiable Data", ha='center', transform=ax.transAxes)
            return

        sat_arr = np.array(sat_data)
        n_sat = len(sat_arr)
        
        # Determine Thresholds (T) from the bins
        log_thresholds = bins 
        time_thresholds = 10**log_thresholds
        
        effectiveness_values = []
        valid_log_thresholds = []
        valid_time_thresholds = []

        # Loop through each threshold T to calculate the specific metric
        for i, T in enumerate(time_thresholds):
            # 1. Numerator: Average time, clipped at T
            clipped_times = np.minimum(sat_arr, T)
            #technically this has a bug: should also clip the unsat times, but here I just assume unsat always takes more than T time, which is true only assuming that the only reason for unsat is timeout. Not the case with subcubes, ofc
            avg_clipped_time = (np.mean(clipped_times) * n_sat + num_unsat * T) / (n_sat + num_unsat)
            
            # 2. Denominator: Fraction actually solved (< T)
            count_solved = np.sum(sat_arr <= T)
            fraction_solved = count_solved / (n_sat + num_unsat)
            
            if fraction_solved > 0:
                # 3. Metric: (Avg Time Clipped) / Fraction
                metric = avg_clipped_time / fraction_solved
                effectiveness_values.append(metric)
                print(i, T, avg_clipped_time, count_solved, fraction_solved, metric)
                valid_log_thresholds.append(log_thresholds[i])
                valid_time_thresholds.append(T)
        
        # --- Find Optimal Timeout ---
        if effectiveness_values:
            min_idx = np.argmin(effectiveness_values)
            best_time = valid_time_thresholds[min_idx]
            best_metric = effectiveness_values[min_idx]
            print(f"-"*40)
            print(f"OPTIMAL TIMEOUT ANALYSIS:")
            print(f"Optimal Timeout Threshold: {best_time:.4f}s")
            print(f"Resulting Effective Time:  {best_metric:.4f}s per solve")
            print(f"-"*40)

            # Mark the optimal point on the graph
            ax.plot(valid_log_thresholds[min_idx], best_metric, 'ro', label=f'Optimal: {best_time:.1f}s')

        # Plot Metric vs Log10(Time)
        ax.plot(valid_log_thresholds, effectiveness_values, color='purple', linewidth=2, label='Effective Time Curve')
        
        # Add Reference Line for Average Time (Satisfiable)
        ax.axhline(sat_mean * (num_unsat + n_sat) / n_sat, color='blue', linestyle='-.', linewidth=1.5, label=f'Actual Sat Avg: {sat_mean:.2f}s')

        # Formatting
        ax.set_title("Effective Time = (Avg Time Clipped at T) / (Fraction Solved at T)")
        ax.set_ylabel("Effective Time (s)")
        ax.set_xlabel("Log10(Time Taken)")
        ax.grid(True, linestyle=':', alpha=0.6, which="both")
        
        # --- Fix Y-Axis Ticks ---
        # 1. Use Log Scale
        ax.set_yscale('log')
        
        # 2. Use ScalarFormatter to force plain numbers (300, 400) instead of 3x10^2
        formatter = ScalarFormatter()
        formatter.set_scientific(False) 
        ax.yaxis.set_major_formatter(formatter)
        ax.yaxis.set_minor_formatter(formatter)
        
        ax.legend(loc='upper right', fontsize='small')
        return valid_log_thresholds, effectiveness_values

    # --- Helper to plot Histograms ---
    def plot_subset(ax, raw_data, color, title, bins, n):
        if not raw_data:
            ax.text(0.5, 0.5, "No Data", ha='center', transform=ax.transAxes)
            ax.set_title(title)
            return

        raw_arr = np.array(raw_data)
        log_data = np.log10(raw_arr)
        
        # Calculate Stats
        log_mean = np.mean(log_data)          # Geometric Mean location
        geo_mean_val = 10**log_mean
        
        arith_mean_val = np.mean(raw_arr)     # Arithmetic Mean value
        log_arith_mean = np.log10(arith_mean_val) # Location on log axis

        weights = np.ones_like(log_data) / n

        # Plot Histogram using COMMON BINS
        # ax.hist(log_data, bins=bins, color=color, alpha=0.6, edgecolor='black')
        frequencies, _, _ = ax.hist(log_data, bins=bins, color=color, alpha=0.6, edgecolor='black', weights=weights)

        # Add Vertical Lines
        ax.axvline(log_mean, color='black', linestyle='--', linewidth=1.5, 
                   label=f'Geo. Mean: {geo_mean_val:.2f}')
        ax.axvline(log_arith_mean, color='blue', linestyle='-', linewidth=1.5, 
                   label=f'Arith. Mean: {arith_mean_val:.2f}')

        ax.set_title(title)
        ax.set_ylabel('Frequency')
        ax.grid(axis='y', linestyle=':', alpha=0.5)
        ax.legend(loc='upper right', fontsize='small')
        return frequencies

    # --- Setup Figure ---
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15), sharex=True)
    print(len(all_log), len(sat_raw), len(unsat_raw))
    print("max", global_max)

    valid_bins, effectiveness_values = plot_effectiveness(ax3, sat_raw, common_bins, len(unsat_raw), sum(unsat_raw))
    n = len(sat_raw) + len(unsat_raw)
    sat_bin_frequencies = plot_subset(ax1, sat_raw, 'green', 'Satisfiable = True (Log10 Scale)', valid_bins, n)
    unsat_bin_frequencies = plot_subset(ax2, unsat_raw, 'red', 'Satisfiable = False (Log10 Scale)', valid_bins, n)
    
    plt.tight_layout()

    # Save output
    output_filename = "time_taken_histogram_optimized.png"
    output_path = input_path.parent / output_filename
    
    plt.savefig(output_path)
    plt.close('all')
    
    print(f"Chart saved to: {output_path}")

    return valid_bins, effectiveness_values, sat_bin_frequencies, unsat_bin_frequencies

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plot_histogram_shared.py <output_folder>")
    else:
        analyze_time_taken(sys.argv[1])