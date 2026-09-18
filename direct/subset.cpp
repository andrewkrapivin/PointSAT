// Exact subset search on a FIXED set of integer coordinates. No realizability
// problem remains. Exhaustion proves a statement only about this supplied seed.
// A hole record stores all seed points in its interior: deleting the last such
// point can create a new hole, so emptiness is recomputed for every retained set.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

using Mask=uint64_t;
using Wide=__int128_t;
using Clock=std::chrono::steady_clock;
struct Point { int64_t x,y; };
struct Polygon { Mask vertices,interior; bool hole; };
Wide det(Point a,Point b,Point c) {
    return (Wide(b.x)-a.x)*(Wide(c.y)-a.y)-(Wide(b.y)-a.y)*(Wide(c.x)-a.x);
}
int size(Mask m) { return __builtin_popcountll(m); }
struct Search {
    std::vector<Point> points;
    std::vector<int> sorted;
    std::vector<Polygon> polygons;
    std::array<std::array<Mask,40>,40> left{};
    std::unordered_set<Mask> visited;
    std::mt19937_64 random{1};
    Clock::time_point start;
    double seconds=60,precompute_seconds=0;
    int gon=7,hole=6,target=23,best_n=0;
    Mask full=0,best=0;
    uint64_t nodes=0,subsets_checked=0,gon_records=0,hole_records=0,disjoint_prunes=0;
    uint64_t convex_prefixes=0;
    std::string output;
    bool timed_out=false,reached_target=false;
    bool quiet=false,write_best=true;
    double elapsed() const { return std::chrono::duration<double>(Clock::now()-start).count(); }
    bool timeout() { if(elapsed()>=seconds) timed_out=true; return timed_out; }
    bool active(const Polygon& p,Mask retained) const {
        return (p.vertices&retained)==p.vertices && (!p.hole || !(p.interior&retained));
    }
    void save() const {
        if(!write_best)return;
        std::ofstream f(output); if(!f)throw std::runtime_error("cannot write "+output);
        f << best_n << '\n';
        for(int i=0;i<int(points.size());++i)if(best&(Mask(1)<<i))f << points[i].x << ' ' << points[i].y << '\n';
    }
    void log(const char* event,const char* status) const {
        if(quiet)return;
        std::cout << "{\"event\":\"" << event << "\",\"method\":\"fixed_coordinate_subset\",\"status\":\"" << status
                  << "\",\"seed_n\":" << points.size() << ",\"target_n\":" << target << ",\"best_n\":" << best_n
                  << ",\"gon\":" << gon << ",\"hole\":" << hole << ",\"elapsed\":" << elapsed()
                  << ",\"precompute_seconds\":" << precompute_seconds << ",\"subsets_checked\":" << subsets_checked
                  << ",\"gon_records\":" << gon_records << ",\"hole_records\":" << hole_records
                  << ",\"nodes\":" << nodes << ",\"memoized_masks\":" << visited.size()
                  << ",\"disjoint_prunes\":" << disjoint_prunes << "}" << std::endl;
    }
    void improve(Mask mask) {
        int n=size(mask);
        if(n>best_n) { best=mask;best_n=n;save();log("best","searching"); }
        if(best_n>=target)reached_target=true;
    }
    void precompute_k(int k,bool hole_rule) {
        if(!k || k>int(points.size()))return;
        std::array<int,10> chosen{};
        auto recurse=[&](auto&& self,int position,int begin)->void {
            if(timed_out)return;
            if(position<k) {
                for(int i=begin;i<=int(points.size())-(k-position);++i) {
                    chosen[position]=sorted[i];self(self,position+1,i+1);
                    if(timed_out)return;
                }
                return;
            }
            if((++subsets_checked&4095)==0&&timeout())return;
            std::array<int,20> hull{};int h=0;
            for(int j=0;j<k;++j) {
                int i=chosen[j];
                while(h>=2&&det(points[hull[h-2]],points[hull[h-1]],points[i])<=0)--h;
                hull[h++]=i;
            }
            int lower=h;
            for(int j=k-2;j>=0;--j) {
                int i=chosen[j];
                while(h>lower&&det(points[hull[h-2]],points[hull[h-1]],points[i])<=0)--h;
                hull[h++]=i;
            }
            --h;if(h!=k)return;
            Mask vertices=0,interior=full;
            for(int j=0;j<k;++j)vertices|=Mask(1)<<chosen[j];
            if(hole_rule)for(int j=0;j<k;++j)interior&=left[hull[j]][hull[(j+1)%k]];
            else interior=0;
            polygons.push_back({vertices,interior,hole_rule});
            if(hole_rule)++hole_records;else ++gon_records;
        };
        recurse(recurse,0,0);
    }
    void precompute_fans() {
        // Enumerate convex angular chains directly; this avoids visiting the
        // many nonconvex k-subsets of a near-solution candidate pool.
        int hk=gon&&gon<=hole?0:hole;
        const int maximum=std::max(gon,hk);
        if(maximum<3)return;
        for(int pivot:sorted) {
            std::vector<int> order;
            for(int i:sorted)if(points[i].x>points[pivot].x||(points[i].x==points[pivot].x&&points[i].y>points[pivot].y))order.push_back(i);
            std::sort(order.begin(),order.end(),[&](int a,int b){return bool((left[pivot][a]>>b)&1);});
            auto recurse=[&](auto&& self,int previous,int last,int begin,int length,Mask vertices,Mask interior)->void {
                if(timed_out)return;
                if((++convex_prefixes&4095)==0&&timeout())return;
                if(length==gon){polygons.push_back({vertices,0,false});++gon_records;}
                if(length==hk){polygons.push_back({vertices,interior,true});++hole_records;}
                if(length==maximum)return;
                for(int j=begin;j<int(order.size());++j) {
                    int next=order[j];
                    if(length>2&&!((left[previous][last]>>next)&1))continue;
                    Mask next_interior=interior;
                    if(hk&&length<hk)next_interior|=left[pivot][last]&left[last][next]&left[next][pivot];
                    self(self,last,next,j+1,length+1,vertices|(Mask(1)<<next),next_interior);
                    if(timed_out)return;
                }
            };
            for(int j=0;j<int(order.size());++j)recurse(recurse,pivot,order[j],j+1,2,(Mask(1)<<pivot)|(Mask(1)<<order[j]),0);
            if(timed_out)return;
        }
    }
    // Return a violated polygon, ordered deletion candidates, and a valid
    // lower bound on required deletions from disjoint violated vertex sets.
    Mask choose(Mask retained,std::array<int,40>& frequency,int& disjoint) const {
        frequency.fill(0);Mask used=0,chosen=0;disjoint=0;
        for(const auto& p:polygons)if(active(p,retained)) {
            for(Mask m=p.vertices;m;m&=m-1)++frequency[__builtin_ctzll(m)];
            if(!(used&p.vertices)){used|=p.vertices;++disjoint;}
            if(!chosen || size(p.vertices)<size(chosen))chosen=p.vertices;
        }
        return chosen;
    }
    void greedy() {
        for(int trial=0;trial<64&&!timeout()&&!reached_target;++trial) {
            Mask retained=full;
            while(size(retained)>best_n) {
                std::array<int,40> frequency{};int disjoint;
                Mask violation=choose(retained,frequency,disjoint);
                if(!violation){improve(retained);break;}
                int selected=-1;uint64_t key=0;
                for(Mask m=violation;m;m&=m-1) {
                    int i=__builtin_ctzll(m);
                    uint64_t score=uint64_t(frequency[i])*1024+(trial?random()%4096:0);
                    if(selected<0||score>key){selected=i;key=score;}
                }
                retained&=~(Mask(1)<<selected);
            }
        }
    }
    void dfs(Mask retained) {
        if(timed_out||reached_target||size(retained)<=best_n)return;
        if((++nodes&255)==0&&timeout())return;
        if(visited.find(retained)!=visited.end())return;
        // Limiting the memo table only affects speed, not correctness.
        if(visited.size()<2000000)visited.insert(retained);
        std::array<int,40> frequency{};int disjoint;
        Mask violation=choose(retained,frequency,disjoint);
        if(!violation){improve(retained);return;}
        if(size(retained)-disjoint<=best_n){++disjoint_prunes;return;}
        std::vector<int> branches;
        for(Mask m=violation;m;m&=m-1)branches.push_back(__builtin_ctzll(m));
        std::sort(branches.begin(),branches.end(),[&](int a,int b) {
            if(frequency[a]!=frequency[b])return frequency[a]>frequency[b];
            return a<b;
        });
        // Every valid subset must delete a vertex of the violated polygon.
        // Deleted interior points cannot be added back deeper in this branch.
        for(int i:branches){dfs(retained&~(Mask(1)<<i));if(timed_out||reached_target)return;}
    }
};
int main(int argc,char** argv)try {
    Search s;std::string input;s.output="subset-best.pts";uint64_t seed=1;
    for(int i=1;i<argc;++i) {
        std::string a=argv[i];
        if(a=="--help") {std::cout << "Usage: subset --input FILE --gon 7 --hole 6 --n 23 --seconds 60 --output FILE [--seed 1]\n"
            "Searches subsets of the fixed input coordinates. An exhausted result applies only to that seed.\n";return 0;}
        if(i+1>=argc)throw std::runtime_error("missing option value");
        std::string value=argv[++i];
        if(a=="--input")input=value;else if(a=="--output")s.output=value;
        else if(a=="--gon")s.gon=std::stoi(value);else if(a=="--hole")s.hole=std::stoi(value);
        else if(a=="--n")s.target=std::stoi(value);else if(a=="--seconds")s.seconds=std::stod(value);
        else if(a=="--seed")seed=std::stoull(value);else throw std::runtime_error("unknown option "+a);
    }
    if(s.gon<0||s.gon>9||s.hole<0||s.hole>9||(s.gon&&s.gon<3)||(s.hole&&s.hole<3)||s.seconds<=0||!std::isfinite(s.seconds))
        throw std::runtime_error("polygon sizes must be 0 or3..9; seconds must be positive");
    std::ifstream in(input);int n;
    if(!(in>>n)||n<3||n>40||s.target<1||s.target>n)throw std::runtime_error("require input n3..40 and target1..n");
    s.points.resize(n);
    for(auto& p:s.points)if(!(in>>p.x>>p.y)||p.x < -1000000000LL||p.x>1000000000LL||p.y < -1000000000LL||p.y>1000000000LL)
        throw std::runtime_error("invalid coordinate, limit1e9");
    s.full=(Mask(1)<<n)-1;s.random.seed(seed);s.start=Clock::now();
    s.sorted.resize(n);std::iota(s.sorted.begin(),s.sorted.end(),0);
    std::sort(s.sorted.begin(),s.sorted.end(),[&](int a,int b) {
        if(s.points[a].x!=s.points[b].x)return s.points[a].x<s.points[b].x;
        return s.points[a].y<s.points[b].y;
    });
    for(int i=0;i<n;++i)for(int j=i+1;j<n;++j)for(int k=j+1;k<n;++k) {
        Wide d=det(s.points[i],s.points[j],s.points[k]);if(!d)throw std::runtime_error("input not in general position");
        if(d>0){s.left[i][j]|=Mask(1)<<k;s.left[j][k]|=Mask(1)<<i;s.left[k][i]|=Mask(1)<<j;}
        else{s.left[j][i]|=Mask(1)<<k;s.left[k][j]|=Mask(1)<<i;s.left[i][k]|=Mask(1)<<j;}
    }
    int small=std::min(s.gon?s.gon:100,s.hole?s.hole:100)-1;
    s.best_n=std::min(n,small);s.best=(Mask(1)<<s.best_n)-1;s.save();
    s.reached_target=s.best_n>=s.target;
    s.precompute_k(s.gon,false);
    if(!s.gon||s.gon>s.hole)s.precompute_k(s.hole,true);
    s.precompute_seconds=s.elapsed();s.log("precomputed",s.timed_out?"precompute_time_limit":"searching");
    if(!s.timed_out){s.greedy();s.dfs(s.full);}
    const char* status=s.reached_target?"target_found":s.timed_out?"time_limit":"exhausted_fixed_seed";
    s.save();s.log("done",status);return 0;
}catch(const std::exception& e){std::cerr << "subset: " << e.what() << '\n';return 2;}
