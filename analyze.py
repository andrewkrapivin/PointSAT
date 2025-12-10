import os
import json
import sys
import matplotlib.pyplot as plt
import math
from collections import Counter
import statistics

if __name__ == "__main__":
    output_folder = "out" if len(sys.argv) < 2 else sys.argv[1]

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
                violations.append((obj['violations'], obj['case'], obj))
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

    print("--- good ones ---")
    for v, c, o in violations[:40]:
        print(v, o['original_id'])
        print(c)

    # print("--- bad ones ---")
    # for v, c, o in violations[-20:]:
    #     print(v, o['original_id'])
    #     print(c)

    print("proportion sat: ", num_sat / num_tried_to_sat, num_tried_to_sat)

    sorted_keys = sorted(violation_counts.keys())
    sorted_counts = [violation_counts[k] for k in sorted_keys]
    sorted_realized_counts = [violation_counts_realized[k] if k in violation_counts_realized else 0 for k in sorted_keys]
    sorted_ratios = [sorted_realized_counts[i] / sorted_counts[i] for i in range(len(sorted_counts))]
    print("Sorted violation counts:", dict(zip(sorted_keys, sorted_counts)))
    sum_counts = sum(sorted_counts[:30])
    sorted_counts = [c / sum_counts for c in sorted_counts]
    print("Sorted violation proportions:", dict(zip(sorted_keys, sorted_counts)))
    print(sum_counts)

    plt.figure(figsize=(10, 6))

    # We use a bar chart because the data is already 'binned' into counts
    # width=1.0 makes the bars touch, looking like a traditional histogram
    plt.bar(sorted_keys[:30], sorted_counts[:30], color='skyblue', edgecolor='black', width=0.8)

    plt.xlabel('# Violations')
    plt.ylabel('% Solutions')
    plt.title('Distribution of #Violations')
    plt.xticks(sorted_keys[:30]) # Ensure every integer key is labeled
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    plt.savefig(os.path.join(output_folder, 'violation_counts_histogram.png'), dpi=300, bbox_inches='tight')
    

    
    plt.figure(figsize=(10, 6))

    # We use a bar chart because the data is already 'binned' into counts
    # width=1.0 makes the bars touch, looking like a traditional histogram
    plt.bar(sorted_keys[:30], sorted_ratios[:30], color='skyblue', edgecolor='black', width=0.8)
    plt.yscale('log')

    plt.xlabel('# Violations')
    plt.ylabel('% Solutions Realized')
    plt.title('% Solutions Realized for each # Violations')
    plt.xticks(sorted_keys[:30]) # Ensure every integer key is labeled
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    print("Sorted ratios:", dict(zip(sorted_keys, sorted_ratios)))
    plt.savefig(os.path.join(output_folder, 'violation_counts_histogram_ratios.png'), dpi=300, bbox_inches='tight')

    print("Mean", statistics.mean(violation_counts_raw))
    print("Std", statistics.stdev(violation_counts_raw))