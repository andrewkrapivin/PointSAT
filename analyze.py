import os
import json
import sys
import matplotlib.pyplot as plt
from collections import Counter


if __name__ == "__main__":
    output_folder = "out" if len(sys.argv) < 2 else sys.argv[1]

    violations = []
    out_file = os.path.join(output_folder, "raw_results.jsonl")
    num_sat = 0
    num_tried_to_sat = 0
    violation_counts = {}
    with open(out_file, 'r') as f:
        for line in f:
            obj = json.loads(line.strip())
            if ('violations' in obj) and (obj['meta'] == 'initial_try'):
                violations.append((obj['violations'], obj['case'], obj))
                if obj['violations'] in violation_counts:
                    violation_counts[obj['violations']] += 1
                else:
                    violation_counts[obj['violations']] = 1
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

    print("--- bad ones ---")
    for v, c, o in violations[-20:]:
        print(v, o['original_id'])
        print(c)

    print("proportion sat: ", num_sat / num_tried_to_sat, num_tried_to_sat)

    sorted_keys = sorted(violation_counts.keys())
    sorted_counts = [violation_counts[k] for k in sorted_keys]
    sum_counts = sum(sorted_counts[:40])
    sorted_counts = [c / sum_counts for c in sorted_counts]
    print("Sorted violation counts:", dict(zip(sorted_keys, sorted_counts)))
    print(sum_counts)

    plt.figure(figsize=(10, 6))

    # We use a bar chart because the data is already 'binned' into counts
    # width=1.0 makes the bars touch, looking like a traditional histogram
    plt.bar(sorted_keys[:40], sorted_counts[:40], color='skyblue', edgecolor='black', width=0.8)

    plt.xlabel('# Violations')
    plt.ylabel('% Solutions')
    plt.title('Distribution of #Violations')
    plt.xticks(sorted_keys[:40]) # Ensure every integer key is labeled
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    plt.savefig(os.path.join(output_folder, 'violation_counts_histogram.png'), dpi=300, bbox_inches='tight')