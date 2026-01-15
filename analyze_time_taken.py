import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

def create_shared_axis_histogram(jsonl_path):
    """
    Reads a JSONL file, extracts 'time_taken' and 'satisfiable'.
    Plots histograms on a Log10 scale with a SHARED X-AXIS.
    Displays vertical lines for both Geometric and Arithmetic Means.
    """
    input_path = Path(jsonl_path)
    
    if not input_path.exists():
        print(f"Error: The file '{jsonl_path}' was not found.")
        return

    # Store RAW values
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
                    if "time_taken" in data and "satisfiable" in data:
                        val = float(data["time_taken"])
                        is_sat = data["satisfiable"]
                        
                        if val > 0:
                            if is_sat:
                                sat_raw.append(val)
                            else:
                                unsat_raw.append(val)
                                
                except (json.JSONDecodeError, ValueError):
                    pass

    except Exception as e:
        print(f"An error occurred reading the file: {e}")
        return

    if not sat_raw and not unsat_raw:
        print("No valid positive data found.")
        return

    # --- Global Binning Strategy ---
    # To make the shared X-axis meaningful, we need common bins.
    all_raw = sat_raw + unsat_raw
    all_log = np.log10(all_raw)
    
    global_min = np.min(all_log)
    global_max = np.max(all_log)
    print(len(all_log), len(sat_raw), len(unsat_raw))
    print("max", global_max)
    
    # Create 50 bins spanning the entire range of data
    common_bins = np.linspace(global_min, global_max, 50)

    # --- Helper to plot ---
    def plot_subset(ax, raw_data, color, title):
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

        # Plot Histogram using COMMON BINS
        ax.hist(log_data, bins=common_bins, color=color, alpha=0.6, edgecolor='black')

        # Add Vertical Lines
        # Geometric Mean (Dashed)
        ax.axvline(log_mean, color='black', linestyle='--', linewidth=1.5, 
                   label=f'Geo. Mean: {geo_mean_val:.2f}')
        
        # Arithmetic Mean (Solid)
        ax.axvline(log_arith_mean, color='blue', linestyle='-', linewidth=1.5, 
                   label=f'Arith. Mean: {arith_mean_val:.2f}')

        ax.set_title(title)
        ax.set_ylabel('Frequency')
        ax.grid(axis='y', linestyle=':', alpha=0.5)
        ax.legend(loc='upper right', fontsize='small')

    # --- Setup Figure ---
    # sharex=True locks the x-axis for both plots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12), sharex=True)

    plot_subset(ax1, sat_raw, 'green', 'Satisfiable = True (Log10 Scale)')
    plot_subset(ax2, unsat_raw, 'red', 'Satisfiable = False (Log10 Scale)')
    
    ax2.set_xlabel('Log10(Time Taken)')
    
    plt.tight_layout()

    # Save output
    output_filename = "time_taken_histogram.png"
    output_path = input_path.parent / output_filename
    
    plt.savefig(output_path)
    plt.close()
    
    print(f"Histogram saved to: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plot_histogram_shared.py <path_to_jsonl_file>")
    else:
        create_shared_axis_histogram(sys.argv[1])