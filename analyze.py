import sys
import csv
import os
from analyze_violations import analyze_violations
from analyze_flippables import analyze_flippables
from analyze_time_taken import analyze_time_taken

def arrays_to_csv(filename, headers, *arrays):
    """
    Outputs several arrays as columns to a CSV file.
    """
    # Zip the arrays to transpose them from columns to rows
    rows = zip(*arrays)
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        # Write the header row
        writer.writerow(headers)
        # Write the transposed data
        writer.writerows(rows)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plot_histogram_shared.py <output_folder> <csv_output_folder(optional)>")
    else:
        if len(sys.argv) == 2:
            csv_output_folder = sys.argv[1]
        if len(sys.argv) == 3:
            csv_output_folder = sys.argv[2]
        print("----- analyzing violations -----")
        sorted_keys, sorted_counts, display_keys, display_proportions, sorted_ratio_keys, sorted_ratios, sorted_realized_violation_frequencies = analyze_violations(sys.argv[1])
        arrays_to_csv(os.path.join(csv_output_folder, "violation_counts.csv"), ["n_violations", "violation_frequency"], sorted_keys, sorted_counts)
        arrays_to_csv(os.path.join(csv_output_folder, "violation_counts_outliers_removed.csv"), ["n_violations", "violation_frequency"], display_keys, display_proportions)
        arrays_to_csv(os.path.join(csv_output_folder, "realized_fraction_against_violations.csv"), ["n_violations", "fraction_realized", "violation_frequency"], sorted_ratio_keys, sorted_ratios, sorted_realized_violation_frequencies)
        print("----- analyzing flippables -----")
        flippable_counts, norm_frequencies, frequencies = analyze_flippables(sys.argv[1])
        arrays_to_csv(os.path.join(csv_output_folder, "flippable_frequencies.csv"), ["n_flippables", "flippable_frequency"], flippable_counts, norm_frequencies)
        print("----- analyzing time taken -----")
        valid_bins, effectiveness_values, sat_bin_counts, unsat_bin_counts = analyze_time_taken(sys.argv[1])
        # print(valid_bins)
        # print("effff", effectiveness_values)
        # print("statat", sat_bin_counts)
        # print("unnstatat", unsat_bin_counts)
        if unsat_bin_counts is None:
            unsat_bin_counts = [0 for _ in valid_bins]
        arrays_to_csv(os.path.join(csv_output_folder, "time_taken_analysis.csv"), ["log10_time", "sat_frequency", "unsat_frequency", "thresholding_effective_time"], valid_bins, sat_bin_counts, unsat_bin_counts, effectiveness_values)