// Independent, exhaustive exact-arithmetic validator. No search-oracle code is shared.
// Build: c++ -O3 -std=c++17 direct/verify.cpp -o direct/verify
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using I = __int128_t;
struct Point { long long x, y; };
I cross(const Point& a, const Point& b, const Point& c) {
    return (I(b.x)-a.x)*(I(c.y)-a.y) - (I(b.y)-a.y)*(I(c.x)-a.x);
}
I abs128(I a) { return a < 0 ? -a : a; }
std::string decimal(I a) {
    if (a == 0) return "0";
    bool neg = a < 0; if (neg) a = -a;
    std::string s;
    while (a) { s.push_back(char('0' + a % 10)); a /= 10; }
    if (neg) s.push_back('-');
    std::reverse(s.begin(), s.end()); return s;
}
// Input indices must be sorted by increasing (x,y,index).
std::vector<int> hull(const std::vector<Point>& p, const std::vector<int>& ids) {
    if (ids.empty()) return {};
    if (ids.size() == 1) return {ids.front()};
    std::vector<int> h; h.reserve(ids.size()*2);
    for (int i : ids) {
        while (h.size() >= 2 && cross(p[h[h.size()-2]],p[h.back()],p[i]) <= 0) h.pop_back();
        h.push_back(i);
    }
    const std::size_t lower = h.size();
    for (int q = int(ids.size())-2; q >= 0; --q) {
        const int i=ids[q];
        while (h.size() > lower && cross(p[h[h.size()-2]],p[h.back()],p[i]) <= 0) h.pop_back();
        h.push_back(i);
    }
    h.pop_back(); return h;
}
struct Counts { uint64_t subsets=0, convex=0, empty=0; std::vector<int> first_convex, first_empty; };
Counts count_subsets(const std::vector<Point>& p, const std::vector<int>& sorted, int k, bool emptiness) {
    Counts out;
    if (k == 0 || k > int(p.size())) return out;
    std::vector<int> ids; ids.reserve(k);
    std::function<void(int)> dfs = [&](int start) {
        if (int(ids.size()) == k) {
            ++out.subsets;
            auto h = hull(p, ids);
            if (int(h.size()) != k) return;
            ++out.convex;
            if (out.first_convex.empty()) out.first_convex = h;
            if (!emptiness) return;
            for (int i=0; i<int(p.size()); ++i) {
                if (std::find(ids.begin(),ids.end(),i) != ids.end()) continue;
                bool inside=true;
                for (int j=0;j<k;++j) {
                    if (cross(p[h[j]],p[h[(j+1)%k]],p[i]) <= 0) { inside=false; break; }
                }
                if (inside) return;
            }
            ++out.empty;
            if (out.first_empty.empty()) out.first_empty=h;
            return;
        }
        const int needed=k-int(ids.size());
        for (int j=start; j<=int(p.size())-needed; ++j) {
            ids.push_back(sorted[j]); dfs(j+1); ids.pop_back();
        }
    };
    dfs(0); return out;
}
Counts count_caps(const std::vector<Point>& p, const std::vector<int>& sorted, int k) {
    Counts out;
    if(k==0 || k>int(p.size())) return out;
    std::vector<int> ids;
    std::function<void(int)> dfs=[&](int start) {
        if(int(ids.size())==k) {
            ++out.subsets;
            for(int j=1;j<k;++j) if(p[ids[j-1]].x>=p[ids[j]].x) return;
            for(int j=2;j<k;++j) if(cross(p[ids[j-2]],p[ids[j-1]],p[ids[j]])>=0) return;
            ++out.convex;
            if(out.first_convex.empty()) out.first_convex=ids;
            return;
        }
        for(int j=start;j<=int(p.size())-(k-int(ids.size()));++j) {
            ids.push_back(sorted[j]); dfs(j+1); ids.pop_back();
        }
    };
    dfs(0); return out;
}
void array(std::ostream& out, const std::vector<int>& v, int offset=0) {
    out << '[';
    for (std::size_t i=0;i<v.size();++i) { if(i) out << ','; out << v[i]+offset; }
    out << ']';
}
std::vector<int> sort_ids(const std::vector<Point>& p) {
    std::vector<int> ids(p.size()); std::iota(ids.begin(),ids.end(),0);
    std::sort(ids.begin(),ids.end(),[&](int a,int b) {
        if(p[a].x!=p[b].x) return p[a].x<p[b].x;
        if(p[a].y!=p[b].y) return p[a].y<p[b].y;
        return a<b;
    }); return ids;
}
void self_test() {
    const std::vector<Point> square={{0,0},{8,0},{8,8},{0,8}};
    auto a=count_subsets(square,sort_ids(square),4,true);
    if(a.subsets!=1 || a.convex!=1 || a.empty!=1) throw std::runtime_error("square self-test failed");
    auto interior=square; interior.push_back({3,4});
    auto b=count_subsets(interior,sort_ids(interior),4,true);
    if(b.subsets!=5 || b.convex!=3 || b.empty!=2) throw std::runtime_error("interior-point self-test failed");
    std::vector<Point> parabola;
    for(int i=0;i<8;++i) parabola.push_back({i,i*i});
    auto c=count_subsets(parabola,sort_ids(parabola),6,true);
    if(c.subsets!=28 || c.convex!=28 || c.empty!=28) throw std::runtime_error("convex-eight self-test failed");
    for (auto& p:parabola) { const auto x=p.x,y=p.y; p.x=-2*x+3*y+13; p.y=x-2*y-23; }
    std::reverse(parabola.begin(),parabola.end());
    auto d=count_subsets(parabola,sort_ids(parabola),6,true);
    if(d.convex!=c.convex || d.empty!=c.empty) throw std::runtime_error("affine-invariance self-test failed");
    std::cout << "{\"self_test\":\"passed\",\"cases\":4}\n";
}
}
int main(int argc,char** argv) {
    try {
        std::string input; int gon=7,hole=6,cap=0;
        for(int i=1;i<argc;++i) {
            const std::string arg=argv[i];
            if(arg=="--self-test") { self_test(); return 0; }
            if(arg=="--help") {
                std::cout << "Usage: verify --input FILE [--gon 7] [--hole 6] [--cap 0]\n"
                             "FILE: n followed by n integer x y pairs; '-' reads stdin.\n"
                             "Use 0 to disable a condition. JSON witnesses use 1-based input indices.\n"
                             "Exit 0: valid; 1: violations; 2: invalid invocation/input.\n"; return 0;
            }
            if(i+1>=argc) throw std::runtime_error("missing value for "+arg);
            if(arg=="--input") input=argv[++i];
            else if(arg=="--gon") gon=std::stoi(argv[++i]);
            else if(arg=="--hole") hole=std::stoi(argv[++i]);
            else if(arg=="--cap") cap=std::stoi(argv[++i]);
            else throw std::runtime_error("unknown option "+arg);
        }
        if(input.empty()) throw std::runtime_error("--input is required");
        if((gon!=0 && gon<3)||(hole!=0 && hole<3)||(cap!=0 && cap<3)) throw std::runtime_error("polygon sizes must be 0 or >=3");
        std::ifstream file;
        if(input!="-") { file.open(input); if(!file) throw std::runtime_error("cannot open "+input); }
        std::istream& in=input=="-" ? std::cin : file;
        int n; if(!(in>>n)||n<1||n>64) throw std::runtime_error("n must be in [1,64]");
        std::vector<Point> p(n);
        constexpr long long coord_limit=1000000000000000000LL;
        for(auto& q:p) {
            if(!(in>>q.x>>q.y)) throw std::runtime_error("missing or invalid coordinates");
            if(q.x < -coord_limit || q.x > coord_limit || q.y < -coord_limit || q.y > coord_limit)
                throw std::runtime_error("coordinates must have absolute value <=10^18 for exact __int128 arithmetic");
        }
        std::string extra; if(in>>extra) throw std::runtime_error("unexpected data after coordinates");
        const auto start=std::chrono::steady_clock::now();
        auto sorted=sort_ids(p);
        uint64_t collinear=0,duplicate=0;
        I min_det=-1,max_det=0,min_d2=-1;
        long long min_x=p[0].x,max_x=p[0].x,min_y=p[0].y,max_y=p[0].y;
        for(int i=0;i<n;++i) {
            min_x=std::min(min_x,p[i].x); max_x=std::max(max_x,p[i].x);
            min_y=std::min(min_y,p[i].y); max_y=std::max(max_y,p[i].y);
            for(int j=i+1;j<n;++j) {
                I dx=I(p[i].x)-p[j].x,dy=I(p[i].y)-p[j].y,d2=dx*dx+dy*dy;
                if(min_d2<0||d2<min_d2) min_d2=d2;
                if(d2==0) ++duplicate;
                for(int k=j+1;k<n;++k) {
                    I d=abs128(cross(p[i],p[j],p[k]));
                    if(d==0) ++collinear;
                    if(min_det<0||d<min_det) min_det=d;
                    max_det=std::max(max_det,d);
                }
            }
        }
        auto g=count_subsets(p,sorted,gon,false);
        auto h=count_subsets(p,sorted,hole,true);
        auto c=count_caps(p,sorted,cap);
        std::vector<int> layers,remaining=sorted;
        while(!remaining.empty()) {
            auto boundary=hull(p,remaining); layers.push_back(int(boundary.size()));
            remaining.erase(std::remove_if(remaining.begin(),remaining.end(),[&](int i) {
                return std::find(boundary.begin(),boundary.end(),i)!=boundary.end();
            }),remaining.end());
        }
        bool valid=collinear==0 && duplicate==0 && g.convex==0 && h.empty==0 && c.convex==0;
        double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        std::cout << "{\"n\":" << n << ",\"gon\":" << gon << ",\"hole\":" << hole << ",\"cap\":" << cap
                  << ",\"valid\":" << (valid?"true":"false")
                  << ",\"collinear_triples\":" << collinear << ",\"duplicate_pairs\":" << duplicate
                  << ",\"convex_gons\":" << g.convex << ",\"empty_holes\":" << h.empty
                  << ",\"convex_caps\":" << c.convex << ",\"cap_subsets_checked\":" << c.subsets
                  << ",\"gon_subsets_checked\":" << g.subsets << ",\"hole_subsets_checked\":" << h.subsets
                  << ",\"convex_hole_size_subsets\":" << h.convex << ",\"hull_layers\":";
        array(std::cout,layers);
        std::cout << ",\"bbox\":[" << min_x << ',' << min_y << ',' << max_x << ',' << max_y << ']'
                  << ",\"bbox_width\":" << decimal(I(max_x)-min_x)
                  << ",\"bbox_height\":" << decimal(I(max_y)-min_y)
                  << ",\"bbox_area\":" << decimal((I(max_x)-min_x)*(I(max_y)-min_y))
                  << ",\"min_determinant\":" << (min_det<0?"null":decimal(min_det))
                  << ",\"max_determinant\":" << decimal(max_det)
                  << ",\"min_squared_distance\":" << (min_d2<0?"null":decimal(min_d2))
                  << ",\"first_gon\":";
        array(std::cout,g.first_convex,1); std::cout << ",\"first_hole\":"; array(std::cout,h.first_empty,1);
        std::cout << ",\"first_cap\":"; array(std::cout,c.first_convex,1);
        std::cout << ",\"seconds\":" << seconds << "}\n";
        return valid?0:1;
    } catch(const std::exception& e) { std::cerr << "verify: " << e.what() << '\n'; return 2; }
}
