import os
import json
import sys
import matplotlib.pyplot as plt
from collections import Counter

if __name__ == "__main__":
    output_folder = "out" if len(sys.argv) < 2 else sys.argv[1]

    flippable_counts = []
    out_file = os.path.join(output_folder, "raw_results.jsonl")
    num_sat = 0
    num_tried_to_sat = 0
    violation_counts = {}
    with open(out_file, 'r') as f:
        for line in f:
            obj = json.loads(line.strip())
            if obj['remove_flippable'] and obj['satisfiable']:
                flippable_counts.append(len(obj['flippable']))
    
    counts = dict(sorted(Counter(flippable_counts).items()))

    results = list(counts.keys())
    frequencies = list(counts.values())
    print(max(results))

    # Plot
    plt.bar(results, frequencies, color='skyblue')
    plt.xlabel('Result')
    plt.ylabel('Count')
    plt.title('Histogram of Flippable Counts')
    # plt.show()
    plt.savefig(os.path.join(output_folder, 'flippables_histogram.png'), dpi=300, bbox_inches='tight')

