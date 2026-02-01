import os
import json
import sys
import matplotlib.pyplot as plt
import math
from collections import Counter
import statistics

def analyze_violations(output_folder):
    violations = []
    out_file = os.path.join(output_folder, "raw_results.jsonl")
    num_sat = 0
    num_tried_to_sat = 0
    violation_counts_raw = []
    violation_counts = {}
    violation_counts_realized = {}
    with open(out_file, 'r') as f:
        for line in f:
            obj = json.loads(line.strip())
            if ('violations' in obj) and (obj['meta'] == 'initial_try'):
                if 'case' in obj:
                    violations.append((obj['violations'], obj['case'], obj))
                elif 'scranfilize_seed' in obj:
                    violations.append((obj['violations'], obj['scranfilize_seed'], obj))
                violation_counts_raw.append(obj['violations'])
                if obj['violations'] in violation_counts:
                    violation_counts[obj['violations']] += 1
                else:
                    violation_counts[obj['violations']] = 1
                if obj['realized']:
                    if obj['violations'] in violation_counts_realized:
                        violation_counts_realized[obj['violations']] += 1
                    else:
                        violation_counts_realized[obj['violations']] = 1
            if obj['type'] == "SAT":
                num_tried_to_sat += 1
                if obj['satisfiable']:
                    num_sat += 1
    
    # violations.sort()
    violations = sorted(violations, key=lambda x: x[0])

    # print("--- good ones ---")
    # for v, c, o in violations[:40]:
    #     print(v, o['original_id'])
    #     print(c)

    # print("--- bad ones ---")
    # for v, c, o in violations[-20:]:
    #     print(v, o['original_id'])
    #     print(c)

    print("proportion sat: ", num_sat / num_tried_to_sat, num_sat, num_tried_to_sat)

    sorted_keys = sorted(violation_counts.keys())
    sorted_counts = [violation_counts[k] for k in sorted_keys]
    sorted_realized_counts = [violation_counts_realized[k] if k in violation_counts_realized else 0 for k in sorted_keys]
    sorted_ratios = [sorted_realized_counts[i] / sorted_counts[i] for i in range(len(sorted_counts))]
    # print("Sorted violation counts:", dict(zip(sorted_keys, sorted_counts)))
    sum_counts = sum(sorted_counts[:50])
    sorted_counts = [c / sum_counts for c in sorted_counts]
    # print("Sorted violation proportions:", dict(zip(sorted_keys, sorted_counts)))
    # print(sum_counts)

    total_samples = sum(sorted_counts)
    cumulative_sum = 0
    cutoff_index = len(sorted_keys) - 1 

    # Find where we cross 99% of total samples
    for i, count in enumerate(sorted_counts):
        cumulative_sum += count
        if (cumulative_sum / total_samples) >= 0.99:
            cutoff_index = i
            break
            
    # Slice the data
    display_keys = sorted_keys[:cutoff_index + 1]
    display_counts = sorted_counts[:cutoff_index + 1]
    
    # Calculate Ratios on sliced data
    display_realized_counts = [violation_counts_realized.get(k, 0) for k in display_keys]
    display_ratios = [r / c if c > 0 else 0 for r, c in zip(display_realized_counts, display_counts)]

    # Normalize proportions (so the graph adds up to 1 for the displayed range)
    sum_display_counts = sum(display_counts)
    display_proportions = [c / sum_display_counts for c in display_counts]

    # --- NEW: Dynamic Step Size ---
    # Target roughly 25 labels on the x-axis
    step_size = max(1, math.ceil(len(display_keys) / 25))

    def plt_figure(output_file, keys, values, xaxis, yaxis, title, step_size=1, logy=False):
        plt.figure(figsize=(10, 6))

        # We use a bar chart because the data is already 'binned' into counts
        # width=1.0 makes the bars touch, looking like a traditional histogram
        # plt.bar(sorted_keys[:50], sorted_counts[:50], color='skyblue', edgecolor='black', width=0.8)
        plt.bar(keys, values, color='skyblue', edgecolor='black', width=0.8)
        if logy:
            plt.yscale('log')

        plt.xlabel('# Violations')
        plt.ylabel('% Solutions')
        plt.title('Distribution of #Violations')
        # plt.xticks(sorted_keys[:50:2]) # Ensure every integer key is labeled
        plt.xticks(keys[::step_size])
        plt.grid(axis='y', linestyle='--', alpha=0.7)

        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close('all')
    
    plt_figure(os.path.join(output_folder, 'violation_counts_histogram.png'), display_keys, display_proportions, '# Violations', '% Solutions', 'Distribution of #Violations', step_size)
    
    sorted_ratio_nonzero_indices = [i for i in range(len(sorted_keys)) if sorted_ratios [i] > 0]
    sorted_ratio_keys = [sorted_keys[i] for i in sorted_ratio_nonzero_indices]
    sorted_ratios = [sorted_ratios[k] for k in sorted_ratio_nonzero_indices]
    sorted_realized_counts = [sorted_realized_counts[k] for k in sorted_ratio_nonzero_indices]
    sorted_realized_violation_frequencies = [v / sum(sorted_realized_counts) for v in sorted_realized_counts]

    plt_figure(os.path.join(output_folder, 'violation_counts_histogram_ratios.png'), sorted_ratio_keys, sorted_ratios, '# Violations', '% Solutions Realized', '% Solutions Realized for each # Violations', logy=True)
    plt_figure(os.path.join(output_folder, 'violation_counts_histogram_realized.png'), sorted_ratio_keys, sorted_realized_violation_frequencies, '# Violations', '% Realized Solutions', 'Distribution of # Violations', logy=False)

    print("Num realizations", sum(sorted_realized_counts))
    print("Num realizations with 0 violations:", sorted_realized_counts[0] if sorted_keys[0] == 0 else 0)

    print("Mean", statistics.mean(violation_counts_raw))
    print("Std", statistics.stdev(violation_counts_raw))

    return sorted_keys, sorted_counts, display_keys, display_proportions, sorted_ratio_keys, sorted_ratios, sorted_realized_violation_frequencies


if __name__ == "__main__":
    output_folder = "out" if len(sys.argv) < 2 else sys.argv[1]
    analyze_violations(output_folder)