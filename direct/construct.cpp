// Explicit Erdos--Szekeres construction, independent of stochastic search.
// Based on Duque, Fabila-Monroy, Hidalgo-Toscano, arXiv:1602.03075,
// Sections 2.1 and 2.3. We choose translations by exact inequalities instead
// of the paper's conservative closed-form separations.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using I=__int128_t;
struct P { int64_t x,y; int group=0; };
using Set=std::vector<P>;
I det(P a,P b,P c) {
    return (I(b.x)-a.x)*(I(c.y)-a.y)-(I(b.y)-a.y)*(I(c.x)-a.x);
}
I floor_div(I a,I b) { I q=a/b,r=a%b; return q-(r<0); }
int64_t checked(I v) {
    if(v < -1000000000000000000LL || v > 1000000000000000000LL)
        throw std::runtime_error("construction exceeds supported coordinate range");
    return static_cast<int64_t>(v);
}
Set cups_caps(int k,int l,bool compact_last=false) {
    if(k<=2 || l<=2) return {{0,0}};
    Set a=cups_caps(k-1,l), b=cups_caps(k,l-1);
    int64_t dx=std::max(a.back().x+1, int64_t(std::ceil((1+std::sqrt(3.0))*(a.back().x+b.back().x)/2)));
    if(compact_last) dx=a.back().x+1;
    I dy=1;
    // Every point in B is above every line through two A points.
    for(std::size_t i=0;i<a.size();++i) for(std::size_t j=i+1;j<a.size();++j)
        for(auto p:b) {
            p.x=checked(I(p.x)+dx);
            dy=std::max(dy,floor_div(-det(a[i],a[j],p),I(a[j].x)-a[i].x)+1);
        }
    // Every point in A is below every line through two B points.
    for(std::size_t i=0;i<b.size();++i) for(std::size_t j=i+1;j<b.size();++j)
        for(auto p:a) {
            auto q=b[i],r=b[j]; q.x=checked(I(q.x)+dx); r.x=checked(I(r.x)+dx);
            dy=std::max(dy,floor_div(det(q,r,p),I(r.x)-q.x)+1);
        }
    for(auto p:b) { p.x=checked(I(p.x)+dx); p.y=checked(I(p.y)+dy); a.push_back(p); }
    return a;
}
Set append(const Set& a,Set b,int gap) {
    const int64_t dx=checked(I(a.back().x)+gap);
    int64_t old_miny=a.front().y,new_maxy=b.front().y;
    for(auto p:a) old_miny=std::min(old_miny,p.y);
    for(auto p:b) new_maxy=std::max(new_maxy,p.y);
    I dy=I(old_miny)-new_maxy-1;
    // Three points belonging to three different blocks must make a right turn.
    for(std::size_t i=0;i<a.size();++i) for(std::size_t j=i+1;j<a.size();++j) {
        if(a[i].group==a[j].group) continue;
        for(auto p:b) {
            p.x=checked(I(p.x)+dx);
            dy=std::min(dy,floor_div(-det(a[i],a[j],p)-1,I(a[j].x)-a[i].x));
        }
    }
    Set out=a;
    for(auto p:b) { p.x=checked(I(p.x)+dx); p.y=checked(I(p.y)+dy); out.push_back(p); }
    return out;
}
I area(const Set& p) {
    int64_t miny=p.front().y,maxy=miny;
    for(auto q:p) { miny=std::min(miny,q.y); maxy=std::max(maxy,q.y); }
    return (I(p.back().x)-p.front().x)*(I(maxy)-miny);
}
Set shear(Set p) {
    // Integer shears preserve x order, all determinant signs, and caps.
    auto height=[&](int64_t m) {
        I low=I(p[0].y)+I(m)*p[0].x,high=low;
        for(auto q:p) { I y=I(q.y)+I(m)*q.x; low=std::min(low,y);high=std::max(high,y); }
        return high-low;
    };
    int64_t lo=-1000000000,hi=1000000000;
    while(lo<hi) {
        int64_t mid=lo+(hi-lo)/2;
        if(height(mid)<=height(mid+1)) hi=mid; else lo=mid+1;
    }
    for(auto& q:p) q.y=checked(I(q.y)+I(lo)*q.x);
    return p;
}
int main(int argc,char** argv) try {
    int gon=7,cap=0,gap=0; std::string output="constructed.pts";
    for(int i=1;i<argc;++i) {
        std::string a=argv[i];
        if(a=="--help") {
            std::cout << "Usage: construct [--gon 7] [--cap 0] [--gap 0] --output FILE\n"
                         "Builds 2^(gon-2) points with no convex gon. --cap C keeps the\n"
                         "first C-1 blocks, also forbidding C-caps; gon7 cap5 gives26.\n"
                         "--gap 0 optimizes a uniform gap and integer shear for small area.\n"; return 0;
        }
        if(i+1>=argc) throw std::runtime_error("missing option value");
        if(a=="--gon") gon=std::stoi(argv[++i]);
        else if(a=="--cap") cap=std::stoi(argv[++i]);
        else if(a=="--gap") gap=std::stoi(argv[++i]);
        else if(a=="--output") output=argv[++i];
        else throw std::runtime_error("unknown option "+a);
    }
    if(gon<3||gon>9||(cap!=0&&(cap<3||cap>gon))||gap<0||gap>1000000)
        throw std::runtime_error("supported: gon3..9, cap0 or3..gon, gap0..1000000");
    const auto start=std::chrono::steady_clock::now();
    const int blocks=cap==0?gon-1:std::min(gon-1,cap-1);
    std::vector<Set> parts;
    for(int i=0;i<blocks;++i) {
        Set block=cups_caps(gon-i,i+2,true);
        for(auto& p:block) p.group=i;
        parts.push_back(std::move(block));
    }
    auto build=[&](int d) {
        Set p=parts.front();
        for(int i=1;i<blocks;++i) p=append(p,parts[i],d);
        return shear(std::move(p));
    };
    Set result=build(gap?gap:1);
    if(!gap) for(int d=2;d<=1000;++d) {
        Set candidate=build(d);
        if(area(candidate)<area(result)) result=std::move(candidate);
    }
    int64_t miny=result.front().y,maxy=miny;
    for(auto p:result) { miny=std::min(miny,p.y); maxy=std::max(maxy,p.y); }
    for(auto& p:result) p.y=checked(I(p.y)-miny);
    std::ofstream file(output); if(!file) throw std::runtime_error("cannot open "+output);
    file << result.size() << '\n'; for(auto p:result) file << p.x << ' ' << p.y << '\n';
    if(!file) throw std::runtime_error("failed writing coordinates");
    double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    std::cout << "{\"method\":\"erdos_szekeres_construction\",\"n\":" << result.size()
              << ",\"gon\":" << gon << ",\"cap\":" << cap << ",\"bbox_width\":" << result.back().x
              << ",\"bbox_height\":" << checked(I(maxy)-miny) << ",\"seconds\":" << seconds << "}\n";
    return 0;
} catch(const std::exception& e) { std::cerr << "construct: " << e.what() << '\n'; return 2; }
