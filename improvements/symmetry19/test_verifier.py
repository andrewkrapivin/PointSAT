"""Compare native exact hexagon histograms to an independent Python oracle."""
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def reference(points):
    # Directed supporting edges avoid sharing the C++ monotone-chain code.
    histogram=[0]*(len(points)-5)
    for subset in itertools.combinations(range(len(points)),6):
        edges=[(i,j) for i in subset for j in subset if i!=j and
               all(cross(points[i],points[j],points[k])>0 for k in subset if k not in (i,j))]
        if len(edges)!=6:continue
        count=sum(all(cross(points[i],points[j],points[k])>0 for i,j in edges)
                  for k in range(len(points)) if k not in subset)
        histogram[count]+=1
    return histogram


def main():
    rng=random.Random(191907)
    count=0
    with tempfile.TemporaryDirectory(prefix='pointsat-hex-verifier-') as folder:
        file=Path(folder)/'input.pts'
        for n in (6,7,8,9,10,11,12,13,15,19):
            points=[]
            while len(points)<n:
                p=(rng.randrange(-10000,10000),rng.randrange(-10000,10000))
                if p not in points and all(cross(a,b,p)!=0 for a,b in itertools.combinations(points,2)):points.append(p)
            expected=reference(points)
            for scale in (1,10**80):
                file.write_text(str(n)+'\n'+''.join(f'{x*scale} {y*scale}\n' for x,y in points))
                r=subprocess.run(['improvements/symmetry19/verify_hexagons',str(file)],capture_output=True,text=True,check=False)
                assert r.returncode in (0,1),(r.stdout,r.stderr)
                actual=json.loads(r.stdout)
                assert actual['interior_histogram']==expected,(n,scale,expected,actual)
                assert actual['six_subsets_checked']==len(list(itertools.combinations(range(n),6)))
                count+=1
    print(json.dumps({'status':'passed','exact_histogram_comparisons':count}))


if __name__=='__main__':main()
