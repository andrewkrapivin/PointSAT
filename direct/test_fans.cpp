#define main fixed_subset_cli_main
#include "subset.cpp"
#undef main

int main() {
    std::mt19937_64 rng(20260905);
    for(int trial=0;trial<120;++trial) {
        Search a,b;int n=6+trial%13;a.gon=3+rng()%6;a.hole=3+rng()%5;
        while(int(a.points.size())<n) {
            Point p{int64_t(rng()%2001)-1000,int64_t(rng()%2001)-1000};bool ok=true;
            for(auto q:a.points)if(q.x==p.x&&q.y==p.y)ok=false;
            for(int i=0;i<int(a.points.size());++i)for(int j=i+1;j<int(a.points.size());++j)if(!det(a.points[i],a.points[j],p))ok=false;
            if(ok)a.points.push_back(p);
        }
        a.full=(Mask(1)<<n)-1;a.sorted.resize(n);std::iota(a.sorted.begin(),a.sorted.end(),0);
        std::sort(a.sorted.begin(),a.sorted.end(),[&](int i,int j){return a.points[i].x<a.points[j].x||(a.points[i].x==a.points[j].x&&a.points[i].y<a.points[j].y);});
        for(int i=0;i<n;++i)for(int j=0;j<n;++j)for(int k=0;k<n;++k)if(det(a.points[i],a.points[j],a.points[k])>0)a.left[i][j]|=Mask(1)<<k;
        a.seconds=30;a.start=Clock::now();b.points=a.points;b.gon=a.gon;b.hole=a.hole;b.full=a.full;b.sorted=a.sorted;b.left=a.left;b.seconds=30;b.start=Clock::now();
        a.precompute_k(a.gon,false);if(!a.gon||a.gon>a.hole)a.precompute_k(a.hole,true);b.precompute_fans();
        auto compare=[](const Polygon& p,const Polygon& q){if(p.vertices!=q.vertices)return p.vertices<q.vertices;if(p.hole!=q.hole)return p.hole<q.hole;return p.interior<q.interior;};
        std::sort(a.polygons.begin(),a.polygons.end(),compare);std::sort(b.polygons.begin(),b.polygons.end(),compare);
        if(a.polygons.size()!=b.polygons.size())throw std::runtime_error("fan polygon count mismatch");
        for(std::size_t i=0;i<a.polygons.size();++i)if(a.polygons[i].vertices!=b.polygons[i].vertices||a.polygons[i].interior!=b.polygons[i].interior||a.polygons[i].hole!=b.polygons[i].hole)throw std::runtime_error("fan polygon/interior mismatch");
    }
    std::cout << "{\"status\":\"passed\",\"cases\":120,\"seed\":20260905}\n";
}
