// Direct coordinate search inspired by Overmars, UU-CS-2001-07 (2001).
// Build: c++ -O3 -std=c++17 -DNDEBUG direct/overmars.cpp -o direct/overmars
// Exact integer predicates; no floating-point geometric decisions.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using I = int64_t;
using U = uint64_t;
struct P { I x, y; };
static int turn(P a, P b, P c) {
    __int128 v = (__int128(b.x)-a.x)*(__int128(c.y)-a.y)
               - (__int128(b.y)-a.y)*(__int128(c.x)-a.x);
    return (v > 0) - (v < 0);
}
constexpr int M = 63;
constexpr int D = 2*M;
using Points = std::vector<P>;
// Optional exact arrangement enumerator supplied by an including executable.
// On false it leaves p unchanged; on true it appends one verified point,
// possibly after an exact common integer dilation of the baseline.
using ExtensionSearch = bool (*)(Points &,int,int,double);
static ExtensionSearch extension_search=nullptr;
static bool quadratic_oracle=true;
static bool crosscheck_oracle=false;
// All stored byte values are <=63, allowing lane-wise maximum without SIMD.
static U byte_max(U x,U y) {
    const U hi=0x8080808080808080ULL;
    U select=((x|hi)-y)&hi;
    select |= select-(select>>7);
    return (x&select)|(y&~select);
}

// One baseline can test many insertions. A polygon through q is an angularly
// ordered convex chain spanning < pi, with q as its remaining vertex. For a
// hole, every fan triangle must be empty. The DP stores the latest possible
// start of each chain length for each final edge; earlier starts are dominated.
// Radial orders are cached for the old set. Merging incoming and outgoing
// edges at each vertex gives O(n^2) per insertion, as in Overmars's method.
// Bit masks give O(1) fan visibility tests for n<=63. --oracle cubic keeps
// an independent cubic recurrence for differential testing and benchmarking.
struct Oracle {
    Points p;
    signed char s[M][M][M]{};
    U left[M][M]{};
    // Every predecessor read is written earlier in the current sweep; old
    // query contents are never used. Avoid clearing these large work arrays.
    U gon_dp[D][D];
    U hole_dp[D][D];
    int around[M][M]{};
    int gon, hole;
    bool last_degenerate=false;
    explicit Oracle(const Points &points, int g, int h): p(points), gon(g), hole(h) {
        if (p.size() > M) throw std::runtime_error("At most 63 baseline points supported");
        int n = int(p.size());
        for (int i=0;i<n;i++) for (int j=i+1;j<n;j++) for (int k=j+1;k<n;k++) {
            int t=turn(p[i],p[j],p[k]);
            s[i][j][k]=s[j][k][i]=s[k][i][j]=t;
            s[j][i][k]=s[k][j][i]=s[i][k][j]=-t;
        }
        for(int i=0;i<n;i++) for(int j=0;j<n;j++) for(int k=0;k<n;k++)
            if(s[i][j][k]>0) left[i][j] |= U(1)<<k;
        for(int i=0;i<n;i++) {
            int z=0;for(int j=0;j<n;j++) if(j!=i) around[i][z++]=j;
            auto upper=[&](int j) { return p[j].y>p[i].y || (p[j].y==p[i].y && p[j].x>p[i].x); };
            std::sort(around[i],around[i]+z,[&](int a,int b) {
                bool x=upper(a),y=upper(b);return x!=y ? x>y : s[i][a][b]>0;
            });
        }
    }
    bool general_position() const {
        for(size_t i=0;i<p.size();i++) for(size_t j=i+1;j<p.size();j++) {
            if(p[i].x==p[j].x && p[i].y==p[j].y) return false;
            for(size_t k=j+1;k<p.size();k++) if(!s[i][j][k]) return false;
        }
        return true;
    }
    bool insertion_ok(P q,int skip=-1) {
        bool result=insertion_impl(q,skip);
        if(crosscheck_oracle) {
            quadratic_oracle=!quadratic_oracle;
            bool other=insertion_impl(q,skip);
            quadratic_oracle=!quadratic_oracle;
            if(result!=other) throw std::runtime_error("Quadratic/cubic oracle disagreement");
        }
        return result;
    }
    // Exact symbolic arrangement-cell queries can supply the same oriented
    // ray data without first rounding a rational point to integer coordinates.
    bool insertion_signs(const signed char qs[M][M],const bool upper[M]) {
        bool result=insertion_impl(P{0,0},-1,qs,upper);
        if(crosscheck_oracle) {
            quadratic_oracle=!quadratic_oracle;
            bool other=insertion_impl(P{0,0},-1,qs,upper);
            quadratic_oracle=!quadratic_oracle;
            if(result!=other) throw std::runtime_error("Quadratic/cubic symbolic oracle disagreement");
        }
        return result;
    }
    bool insertion_impl(P q,int skip,const signed char (*given_qs)[M]=nullptr,const bool *given_upper=nullptr) {
        last_degenerate=false;
        int nbase=int(p.size()),n=nbase-(skip>=0);
        signed char qs[M][M]{};
        U qleft[M]{};
        int ord[D];
        for(int i=0;i<nbase;i++) {
            if(i==skip) continue;
            if(!given_qs && q.x==p[i].x && q.y==p[i].y) {last_degenerate=true;return false;}
            for(int j=0;j<i;j++) {
                if(j==skip) continue;
                int t=given_qs ? given_qs[i][j] : skip>=0 ? s[skip][i][j] : turn(q,p[i],p[j]);
                if(!t) {last_degenerate=true;return false;}
                qs[i][j]=t; qs[j][i]=-t;
                if(t>0) qleft[i]|=U(1)<<j;
                else qleft[j]|=U(1)<<i;
            }
        }
        if((!gon || n+1<gon) && (!hole || n+1<hole)) return true;
        for(int i=0,z=0;i<nbase;i++) if(i!=skip) ord[z++]=i;
        auto upper=[&](int i) { return given_upper ? given_upper[i] : p[i].y>q.y || (p[i].y==q.y && p[i].x>q.x); };
        std::sort(ord,ord+n,[&](int a,int b) {
            bool x=upper(a),y=upper(b);
            return x!=y ? x>y : qs[a][b]>0;
        });
        for(int i=0;i<n;i++) ord[n+i]=ord[i];
        const int gl=gon ? gon-1 : 0, hl=hole ? hole-1 : 0;
        auto found=[&](U dp,int len,int j,int b) {
            if(!len) return false;
            int start=int((dp>>(8*(len-2)))&255)-1;
            return start>=0 && j-start<n && qs[ord[start]][b]>0;
        };
        if(quadratic_oracle) {
            int pos[M];for(int i=0;i<n;i++) pos[ord[i]]=i;
            for(int i=0;i<2*n-2;i++) {
                int a=ord[i],incoming[M],outgoing[M],ni=0,no=0,mini=0,mino=0;
                for(int z=0;z<nbase-1;z++) {
                    int b=around[a][z];if(b==skip) continue;
                    if(qs[a][b]>0) {
                        int j=i+(pos[b]-i%n+n)%n;
                        if(j>=2*n-1) continue;
                        outgoing[no]=j;
                        if(no && s[a][b][ord[outgoing[mino]]]>0) mino=no;
                        no++;
                    } else {
                        int h=i-(i%n-pos[b]+n)%n;
                        if(h<0) continue;
                        incoming[ni]=h;
                        if(ni && s[a][b][ord[incoming[mini]]]>0) mini=ni;
                        ni++;
                    }
                }
                U bestg=0,besth=0;int hpos=0;
                for(int z=0;z<no;z++) {
                    int j=outgoing[(mino+z)%no],b=ord[j];
                    while(hpos<ni) {
                        int h=incoming[(mini+hpos)%ni],c=ord[h];
                        if(s[c][a][b]<=0) break;
                        if(gon) bestg=byte_max(bestg,gon_dp[h][i]);
                        if(hole) besth=byte_max(besth,hole_dp[h][i]);
                        ++hpos;
                    }
                    U base=i<n ? U(i+1) : 0;
                    U gd=gon ? (bestg<<8)|base : 0;
                    bool empty=hole && !(qleft[a]&left[a][b]&~qleft[b]);
                    U hd=empty ? (besth<<8)|base : 0;
                    gon_dp[i][j]=gd;hole_dp[i][j]=hd;
                    if(found(gd,gl,j,b) || found(hd,hl,j,b)) return false;
                }
            }
            return true;
        }
        for(int j=1;j<2*n-1;j++) {
            const int b=ord[j];
            for(int i=j-1;i>=0 && j-i<n;i--) {
                const int a=ord[i];
                if(qs[a][b]<=0) break; // angular width of edge >= pi
                U gd=(gon && i<n) ? U(i+1) : 0;
                bool empty=hole && !(qleft[a] & left[a][b] & ~qleft[b]);
                U hd=(empty && i<n) ? U(i+1) : 0;
                for(int h=i-1;h>=0 && i-h<n;h--) {
                    const int c=ord[h];
                    if(qs[c][a]<=0) break;
                    if(s[c][a][b]<=0) continue;
                    U gp=gon_dp[h][i], hp=hole_dp[h][i];
                    if(gon) for(int k=3;k<=gl;k++) {
                        unsigned v=unsigned((gp>>(8*(k-3)))&255);
                        unsigned old=unsigned((gd>>(8*(k-2)))&255);
                        if(v>old) gd=(gd & ~(U(255)<<(8*(k-2)))) | (U(v)<<(8*(k-2)));
                    }
                    if(empty) for(int k=3;k<=hl;k++) {
                        unsigned v=unsigned((hp>>(8*(k-3)))&255);
                        unsigned old=unsigned((hd>>(8*(k-2)))&255);
                        if(v>old) hd=(hd & ~(U(255)<<(8*(k-2)))) | (U(v)<<(8*(k-2)));
                    }
                }
                gon_dp[i][j]=gd; hole_dp[i][j]=hd;
                if(found(gd,gl,j,b) || found(hd,hl,j,b)) return false;
            }
        }
        return true;
    }
};

// Check the final set at every pivot. Prefix rejection is unsound for holes:
// a later point can fill a hole that existed in a prefix.
static bool valid(const Points &p,int gon,int hole) {
    if(p.size()>M) throw std::runtime_error("At most 63 points supported");
    auto oracle=std::make_unique<Oracle>(p,gon,hole);
    if(!oracle->general_position()) return false;
    for(size_t i=0;i<p.size();i++) if(!oracle->insertion_ok(p[i],int(i))) return false;
    return true;
}

static std::vector<int> hull(const Points &p) {
    std::vector<int> a(p.size()),h;
    std::iota(a.begin(),a.end(),0);
    std::sort(a.begin(),a.end(),[&](int i,int j) {
        return p[i].x!=p[j].x ? p[i].x<p[j].x : p[i].y<p[j].y;
    });
    for(int i:a) { while(h.size()>1 && turn(p[h[h.size()-2]],p[h.back()],p[i])<=0) h.pop_back(); h.push_back(i); }
    size_t low=h.size();
    for(int k=int(a.size())-2;k>=0;k--) { int i=a[k]; while(h.size()>low && turn(p[h[h.size()-2]],p[h.back()],p[i])<=0) h.pop_back(); h.push_back(i); }
    if(h.size()>1) h.pop_back();
    return h;
}

static Points read_points(const std::string &file) {
    std::ifstream f(file);
    if(!f) throw std::runtime_error("Cannot open input: "+file);
    Points p; std::string line;int declared=-1,line_number=0;
    while(std::getline(f,line)) {
        ++line_number;
        auto hash=line.find('#'); if(hash!=std::string::npos) line.resize(hash);
        for(char &c:line) if(c==',' || c=='(' || c==')' || c=='[' || c==']') c=' ';
        std::istringstream stream(line);std::vector<std::string> tokens;std::string token;
        while(stream>>token) tokens.push_back(token);
        if(tokens.empty()) continue;
        auto parse=[&](const std::string &value) {
            size_t end=0;I x=std::stoll(value,&end);
            if(end!=value.size()) throw std::runtime_error("Expected integer coordinate on input line "+std::to_string(line_number));
            return x;
        };
        if(tokens.size()==1 && p.empty() && declared<0) {
            I n=parse(tokens[0]);if(n<0 || n>M) throw std::runtime_error("Invalid point count in input");
            declared=int(n);continue;
        }
        if(tokens.size()!=2) throw std::runtime_error("Expected x y on input line "+std::to_string(line_number));
        I x=parse(tokens[0]),y=parse(tokens[1]);
        constexpr I lim=I(1)<<50;
        if(x<=-lim || x>=lim || y<=-lim || y>=lim) throw std::runtime_error("Coordinates must have magnitude below 2^50");
        p.push_back({x,y});
    }
    if(declared>=0 && size_t(declared)!=p.size()) throw std::runtime_error("Declared point count does not match input");
    if(declared<0 && p.empty()) throw std::runtime_error("No coordinates in input file");
    return p;
}

struct Args {
    double seconds=60;
    U seed=1;
    int n=23,gon=7,hole=6,tries=1000,shake=150,backtrack=3,patience=4;
    std::string input,output="direct/overmars_best.txt";
    bool check=false,benchmark=false,intersections=false,boundary=false,deletable=false,triangle=false,exact=false;
};

int main(int argc,char **argv) try {
    Args a;
    for(int i=1;i<argc;i++) {
        std::string key=argv[i];
        if(key=="--check") { a.check=true; continue; }
        if(key=="--benchmark") { a.benchmark=true; continue; }
        if(key=="--crosscheck") { crosscheck_oracle=true;continue; }
        if(key=="--intersections") { a.intersections=true;continue; }
        if(key=="--boundary") { a.boundary=true;continue; }
        if(key=="--deletable") { a.deletable=true;continue; }
        if(key=="--triangle") { a.triangle=true;continue; }
        if(key=="--exact") { a.exact=true;continue; }
        if(key=="--help") {
            std::cout<<"overmars [--seconds S] [--seed N] [--n N] [--gon K|0] [--hole K|0]\n"
                "         [--input coordinates.txt] [--output best.txt] [--tries 1000]\n"
                "         [--shake 150] [--backtrack 3] [--patience 4] [--oracle quadratic|cubic]\n"
                "         [--check] [--benchmark] [--crosscheck] [--intersections] [--boundary]\n"
                "         [--triangle] [--deletable] [--exact (arrangement wrapper only)]\n"
                "gon/hole sizes 3..10, or 0 to disable; n<=63; input is integer x y per line.\n"
                "Progress is JSONL on stdout. --check verifies the supplied final set.\n";
            return 0;
        }
        if(i+1==argc) throw std::runtime_error("Missing value for "+key);
        std::string value=argv[++i];
        if(key=="--seconds") a.seconds=std::stod(value);
        else if(key=="--seed") a.seed=std::stoull(value);
        else if(key=="--n") a.n=std::stoi(value);
        else if(key=="--gon") a.gon=std::stoi(value);
        else if(key=="--hole") a.hole=std::stoi(value);
        else if(key=="--tries") a.tries=std::stoi(value);
        else if(key=="--shake") a.shake=std::stoi(value);
        else if(key=="--backtrack") a.backtrack=std::stoi(value);
        else if(key=="--patience") a.patience=std::stoi(value);
        else if(key=="--input") a.input=value;
        else if(key=="--output") a.output=value;
        else if(key=="--oracle") {
            if(value!="quadratic" && value!="cubic") throw std::runtime_error("Unknown oracle: "+value);
            quadratic_oracle=value=="quadratic";
        }
        else throw std::runtime_error("Unknown option: "+key);
    }
    if(a.n<1 || a.n>M || a.seconds<0 || !std::isfinite(a.seconds) || a.tries<1 || a.shake<0 || a.backtrack<1 || a.patience<1)
        throw std::runtime_error("Invalid n, seconds, tries, shake or backtrack");
    for(int k:{a.gon,a.hole}) if(k && (k<3 || k>10)) throw std::runtime_error("Polygon sizes must be 3..10 or 0");
    if(a.exact && !extension_search) throw std::runtime_error("--exact requires the arrangement search executable");
    Points p=a.input.empty() ? Points{} : read_points(a.input);
    if(a.deletable) {
        auto h=hull(p);std::cout<<"{\"n\":"<<p.size()<<",\"deletable\":[";bool comma=false;
        for(size_t i=0;i<p.size();i++) {
            Points base=p;base.erase(base.begin()+i);
            if(valid(base,a.gon,a.hole)) {
                if(comma) std::cout<<',';
                comma=true;
                std::cout<<"{\"index\":"<<i<<",\"hull\":"<<(std::find(h.begin(),h.end(),int(i))!=h.end()?"true":"false")<<'}';
            }
        }
        std::cout<<"]}\n";return 0;
    }
    if(a.check) {
        bool ok=valid(p,a.gon,a.hole);
        std::cout<<"{\"event\":\"check\",\"n\":"<<p.size()<<",\"gon\":"<<a.gon<<",\"hole\":"<<a.hole<<",\"valid\":"<<(ok?"true":"false")<<"}\n";
        return ok ? 0 : 2;
    }
    if(a.triangle) {
        if(p.empty()) p={{-1000000,-1000000},{1000000,-1000000},{0,1000000}};
        while(hull(p).size()>3) {auto h=hull(p);p.erase(p.begin()+h[0]);}
        auto h=hull(p);
        if(h.size()!=3) throw std::runtime_error("--triangle requires at least three noncollinear input points");
        Points ordered;for(int i:h) ordered.push_back(p[i]);
        for(int i=0;i<int(p.size());i++) if(std::find(h.begin(),h.end(),i)==h.end()) ordered.push_back(p[i]);
        p=std::move(ordered);
    }
    if(!valid(p,a.gon,a.hole)) throw std::runtime_error("Input is not a valid general-position point set");
    using Clock=std::chrono::steady_clock;
    auto start=Clock::now();
    std::clock_t cpu_start=std::clock();
    auto elapsed=[&]() { return std::chrono::duration<double>(Clock::now()-start).count(); };
    std::mt19937_64 rng(a.seed);
    auto unit=[&]() { return std::generate_canonical<double,53>(rng); };
    auto sym=[&]() { return 2*unit()-1; };
    Points best=p;
    std::vector<Points> bank;
    U bank_seen=0;
    std::ofstream log(a.output+".jsonl");
    if(!log) throw std::runtime_error("Cannot write log: "+a.output+".jsonl");
    U candidates=0,gp_candidates=0,accepted=0,moves=0,order_preserving_moves=0,backtracks=0,cycles=0,exact_calls=0,exact_extensions=0;
    int bestn=-1;
    auto report=[&](const char *event) {
        std::ostringstream line;
        double cpu_seconds=double(std::clock()-cpu_start)/CLOCKS_PER_SEC;
        line<<std::fixed<<std::setprecision(6)<<"{\"event\":\""<<event<<"\",\"seconds\":"<<elapsed()
            <<",\"cpu_seconds\":"<<cpu_seconds
            <<",\"seed\":"<<a.seed<<",\"gon\":"<<a.gon<<",\"hole\":"<<a.hole
            <<",\"triangle\":"<<(a.triangle?"true":"false")<<",\"intersections\":"<<(a.intersections?"true":"false")
            <<",\"boundary\":"<<(a.boundary?"true":"false")<<",\"oracle\":\""<<(quadratic_oracle?"quadratic":"cubic")<<"\""
            <<",\"exact_calls\":"<<exact_calls<<",\"exact_extensions\":"<<exact_extensions
            <<",\"n\":"<<p.size()<<",\"best_n\":"<<best.size()<<",\"candidates\":"<<candidates
            <<",\"candidates_per_second\":"<<(candidates/std::max(1e-9,elapsed()))
            <<",\"candidates_per_cpu_second\":"<<(candidates/std::max(1e-9,cpu_seconds))
            <<",\"general_position_candidates\":"<<gp_candidates
            <<",\"insertions\":"<<accepted<<",\"moves\":"<<moves
            <<",\"order_preserving_moves\":"<<order_preserving_moves<<",\"backtracks\":"<<backtracks<<"}";
        std::cout<<line.str()<<std::endl;
        log<<line.str()<<std::endl;
    };
    auto save=[&]() {
        if(p.size()>=best.size()) {
            if(p.size()>best.size()) { bank.clear();bank_seen=0; }
            ++bank_seen;
            if(bank.size()<64) bank.push_back(p);
            else { U slot=rng()%bank_seen;if(slot<bank.size()) bank[slot]=p; }
        }
        if(int(p.size())<=bestn) return;
        if(!valid(p,a.gon,a.hole)) throw std::runtime_error("Internal error: invalid best candidate");
        best=p; bestn=int(best.size());
        std::ofstream f(a.output); if(!f) throw std::runtime_error("Cannot write output: "+a.output);
        f<<best.size()<<'\n';
        for(P q:best) f<<q.x<<' '<<q.y<<'\n';
        report("best");
    };
    struct Box { double cx,cy,r; };
    auto box=[&](const Points &pts) {
        if(pts.empty()) return Box{0,0,1000000};
        I xmin=pts[0].x,xmax=xmin,ymin=pts[0].y,ymax=ymin;
        for(P q:pts) { xmin=std::min(xmin,q.x);xmax=std::max(xmax,q.x);ymin=std::min(ymin,q.y);ymax=std::max(ymax,q.y); }
        return Box{(xmin+xmax)*0.5,(ymin+ymax)*0.5,std::max(100.0,std::max(xmax-xmin,ymax-ymin)*0.55)};
    };
    Box core_box=box(p);
    Points core_points=p;
    auto inside_triangle=[&](P q) {
        return !a.triangle || (turn(p[0],p[1],q)>0 && turn(p[1],p[2],q)>0 && turn(p[2],p[0],q)>0);
    };
    auto candidate=[&](const Points &pts,Box b) {
        if(a.triangle && pts.size()>=10 && rng()%3==0) {
            if(core_points.size()>=3) {
                size_t i=rng()%core_points.size(),j,k;
                do {j=rng()%core_points.size();} while(j==i);
                do {k=rng()%core_points.size();} while(k==i || k==j);
                double u=unit(),v=unit();if(u+v>1) {u=1-u;v=1-v;}
                P q=core_points[i],r=core_points[j],s=core_points[k];
                return P{I(std::llround(q.x+u*(r.x-q.x)+v*(s.x-q.x))),I(std::llround(q.y+u*(r.y-q.y)+v*(s.y-q.y)))};
            }
            return P{I(std::llround(core_box.cx+sym()*core_box.r*0.75)),I(std::llround(core_box.cy+sym()*core_box.r*0.75))};
        }
        // Small feasible cells in the arrangement of point-pair lines are
        // difficult to hit by uniform sampling. Sample beside intersections
        // using a sector bisector and distance to the nearest third line.
        if(a.intersections && pts.size()>=4 && rng()%3==0) {
            int ids[4];
            for(int k=0;k<4;k++) {
                bool duplicate;
                do {ids[k]=int(rng()%pts.size());duplicate=false;for(int j=0;j<k;j++) duplicate|=ids[k]==ids[j];} while(duplicate);
            }
            P aa=pts[ids[0]],bb=pts[ids[1]],cc=pts[ids[2]],dd=pts[ids[3]];
            I dx=bb.x-aa.x,dy=bb.y-aa.y,ex=dd.x-cc.x,ey=dd.y-cc.y;
            __int128 den=__int128(dx)*ey-__int128(dy)*ex;
            if(den) {
                __int128 num=(__int128(cc.x)-aa.x)*ey-(__int128(cc.y)-aa.y)*ex;
                long double t=static_cast<long double>(num)/static_cast<long double>(den);
                long double x=aa.x+t*dx,y=aa.y+t*dy;
                if(std::abs(x-b.cx)<4*b.r && std::abs(y-b.cy)<4*b.r) {
                    long double margin=b.r;
                    for(int i=0;i<int(pts.size());i++) for(int j=0;j<i;j++) {
                        if((i==ids[0] && j==ids[1]) || (i==ids[1] && j==ids[0]) ||
                           (i==ids[2] && j==ids[3]) || (i==ids[3] && j==ids[2])) continue;
                        long double vx=pts[i].x-pts[j].x,vy=pts[i].y-pts[j].y;
                        long double d=std::abs(vx*(y-pts[j].y)-vy*(x-pts[j].x))/std::hypot(vx,vy);
                        margin=std::min(margin,d);
                    }
                    long double l1=std::hypot(static_cast<long double>(dx),static_cast<long double>(dy));
                    long double l2=std::hypot(static_cast<long double>(ex),static_cast<long double>(ey));
                    int sg=rng()%2 ? 1 : -1;
                    long double vx=dx/l1+sg*ex/l2,vy=dy/l1+sg*ey/l2,len=std::hypot(vx,vy);
                    if(len>0) {
                        long double step=std::max(2.0L,margin*(0.05+0.35*unit()))*(rng()%2 ? 1 : -1);
                        constexpr long double limit=static_cast<long double>(I(1)<<49);
                        return P{I(std::llround(std::clamp(x+step*vx/len,-limit,limit))),
                                 I(std::llround(std::clamp(y+step*vy/len,-limit,limit)))};
                    }
                }
            }
        }
        int mode=int(rng()%10);
        double x,y;
        if(mode<4 && a.triangle) {
            double u=unit(),v=unit();if(u+v>1) {u=1-u;v=1-v;}
            x=pts[0].x+u*(pts[1].x-pts[0].x)+v*(pts[2].x-pts[0].x);
            y=pts[0].y+u*(pts[1].y-pts[0].y)+v*(pts[2].y-pts[0].y);
        } else if(mode<4 || pts.size()<3) {
            double scale=(mode==0 ? 1.5 : mode==1 ? 0.5 : 1.0);
            x=b.cx+sym()*b.r*scale;y=b.cy+sym()*b.r*scale;
        } else if(mode<8) {
            P q=pts[rng()%pts.size()];
            double r=b.r*std::pow(10.0,-unit()*3.5);
            x=q.x+sym()*r;y=q.y+sym()*r;
        } else {
            P q=pts[rng()%pts.size()],r=pts[rng()%pts.size()],s=pts[rng()%pts.size()];
            double u=unit(),v=unit(); if(u+v>1) {u=1-u;v=1-v;}
            x=q.x+u*(r.x-q.x)+v*(s.x-q.x);y=q.y+u*(r.y-q.y)+v*(s.y-q.y);
        }
        constexpr double lim=double(I(1)<<49);
        return P{I(std::llround(std::clamp(x,-lim,lim))),I(std::llround(std::clamp(y,-lim,lim)))};
    };
    save();
    double next_report=10;
    if(a.benchmark) {
        auto oracle=std::make_unique<Oracle>(p,a.gon,a.hole); Box b=box(p);
        while(elapsed()<a.seconds) {
            candidates++; if(oracle->insertion_ok(candidate(p,b))) accepted++;
            if(!oracle->last_degenerate) gp_candidates++;
        }
        report("benchmark_done"); return 0;
    }
    int stalls=0;
    while(elapsed()<a.seconds && int(best.size())<a.n) {
        ++cycles;
        auto oracle=std::make_unique<Oracle>(p,a.gon,a.hole);
        Box b=box(p); bool grew=false;
        if(a.triangle) {
            Points core=p;
            while(core.size()>6) {
                auto h=hull(core);Points next;
                for(int i=0;i<int(core.size());i++) if(std::find(h.begin(),h.end(),i)==h.end()) next.push_back(core[i]);
                if(next.empty()) break;
                core=std::move(next);
            }
            core_box=box(core);
            core_points=std::move(core);
        }
        for(int t=0;t<a.tries && elapsed()<a.seconds;t++) {
            P q=candidate(p,b); ++candidates;
            if(!inside_triangle(q)) continue;
            bool ok=oracle->insertion_ok(q);
            if(!oracle->last_degenerate) gp_candidates++;
            if(ok) {
                p.push_back(q); ++accepted; save(); grew=true; stalls=0;break;
            }
        }
        if(grew) continue;
        if(a.exact && int(p.size())+1==a.n && elapsed()<a.seconds) {
            ++exact_calls;
            if(extension_search(p,a.gon,a.hole,a.seconds-elapsed())) {
                ++accepted;++exact_extensions;stalls=0;save();continue;
            }
        }
        // Brownian motion. Preserving every orientation preserves validity.
        // A changed order type needs a complete check: deleting the old
        // position of an interior point may expose an unrelated empty hole.
        for(int t=0;t<a.shake && p.size()>size_t(a.triangle?3:2) && elapsed()<a.seconds;t++) {
            int id=a.triangle ? 3+int(rng()%(p.size()-3)) : int(rng()%p.size()); P old=p[id];
            Points base=p; base.erase(base.begin()+id);
            double r=b.r*std::pow(10.0,-0.3-unit()*3.7);
            constexpr double lim=double(I(1)<<49);
            P q{I(std::llround(std::clamp(old.x+sym()*r,-lim,lim))),I(std::llround(std::clamp(old.y+sym()*r,-lim,lim)))};
            if(a.boundary && rng()%2==0) {
                long double vx=sym(),vy=sym(),len=std::hypot(vx,vy);
                if(len>0) {
                    vx/=len;vy/=len;
                    long double near=std::numeric_limits<long double>::infinity(),next=near;
                    for(size_t i=0;i<base.size();i++) for(size_t j=0;j<i;j++) {
                        long double dx=base[i].x-base[j].x,dy=base[i].y-base[j].y;
                        long double divisor=dx*vy-dy*vx;
                        if(!divisor) continue;
                        long double t=-(dx*(old.y-base[j].y)-dy*(old.x-base[j].x))/divisor;
                        if(t<=0) continue;
                        if(t<near) {next=near;near=t;} else next=std::min(next,t);
                    }
                    if(near<b.r) {
                        long double extra=std::max(2.0L,std::min((next-near)*0.2L,static_cast<long double>(b.r)*0.001L));
                        long double distance=near+extra;
                        q={I(std::llround(std::clamp(old.x+distance*vx,-static_cast<long double>(lim),static_cast<long double>(lim)))),
                           I(std::llround(std::clamp(old.y+distance*vy,-static_cast<long double>(lim),static_cast<long double>(lim))))};
                    }
                }
            }
            ++candidates;
            if(!inside_triangle(q)) continue;
            bool unchanged=true;
            for(size_t i=0;i<base.size() && unchanged;i++) for(size_t j=0;j<i;j++)
                if(turn(old,base[i],base[j])!=turn(q,base[i],base[j])) { unchanged=false;break; }
            if(unchanged) {p[id]=q;++moves;++order_preserving_moves;++gp_candidates;continue;}
            auto moving=std::make_unique<Oracle>(base,a.gon,a.hole);
            bool ok=moving->insertion_ok(q);
            if(!moving->last_degenerate) gp_candidates++;
            if(!ok) continue;
            base.push_back(q);
            if(valid(base,a.gon,a.hole)) { p=std::move(base); ++moves; }
        }
        if(p.size()==best.size()) save();
        if(elapsed()>=next_report) { report("progress"); next_report=elapsed()+10; }
        if(++stalls<a.patience) continue;
        stalls=0;
        // Keep exploring around the incumbent, but periodically make a
        // larger retreat. Hull deletions cannot expose empty polygons.
        if(rng()%4==0 && !bank.empty()) p=bank[rng()%bank.size()];
        int remove=1+int(rng()%a.backtrack);
        if(cycles%40==0) remove+=2;
        while(remove-- && p.size()>4) {
            if(a.triangle) {
                std::vector<int> ids(p.size()-3);std::iota(ids.begin(),ids.end(),3);std::shuffle(ids.begin(),ids.end(),rng);
                bool removed=false;
                for(int id:ids) {
                    Points base=p;base.erase(base.begin()+id);
                    if(valid(base,a.gon,a.hole)) {p=std::move(base);removed=true;break;}
                }
                if(!removed) break;
            } else {
                auto h=hull(p); int id=h[rng()%h.size()]; p.erase(p.begin()+id);
            }
        }
        // Repeated hull removal otherwise shrinks the cloud onto a coarse
        // integer grid. Exact translation and integer dilation preserve
        // the order type while restoring space for fine Brownian motion.
        if(!p.empty()) {
            auto b2=box(p);I factor=std::max<I>(1,I(std::ceil(500000.0/b2.r)));
            P origin=p[0];
            for(P &q:p) {q.x=(q.x-origin.x)*factor;q.y=(q.y-origin.y)*factor;}
        }
        ++backtracks;
        if(elapsed()>=next_report) { report("progress"); next_report=elapsed()+10; }
    }
    report("done");
    return 0;
} catch(const std::exception &e) { std::cerr<<"overmars: "<<e.what()<<'\n'; return 1; }
