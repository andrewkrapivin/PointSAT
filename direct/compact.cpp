// Exact order-type-preserving integer coordinate compression.
// Each coordinate update samples its feasible integer interval, obtained by
// intersecting all strict linear orientation inequalities involving that point.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Wide=__int128;
struct P {int64_t x,y;};
static Wide det(P a,P b,P c){return (Wide(b.x)-a.x)*(Wide(c.y)-a.y)-(Wide(b.y)-a.y)*(Wide(c.x)-a.x);}
static Wide floor_div(Wide a,Wide b){if(b<0){a=-a;b=-b;}Wide q=a/b,r=a%b;return q-(r<0);}
static Wide ceil_div(Wide a,Wide b){return -floor_div(-a,b);}
static pair<int64_t,int64_t> normalize(vector<P>&p){int64_t x=p[0].x,y=p[0].y,w=x,h=y;for(auto a:p){x=min(x,a.x);y=min(y,a.y);w=max(w,a.x);h=max(h,a.y);}for(auto&a:p){a.x-=x;a.y-=y;}return {w-x,h-y};}
static uint64_t objective(pair<int64_t,int64_t>b){return uint64_t(b.first)*b.second;}
static void save(const string&fn,const vector<P>&p){ofstream f(fn);if(!f)throw runtime_error("cannot write output");f<<p.size()<<'\n';for(auto a:p)f<<a.x<<' '<<a.y<<'\n';}
int main(int argc,char**argv)try{
    string input,output="compact.pts";double seconds=60;uint64_t seed=1;bool preserve_x_order=false;
    for(int i=1;i<argc;i++){string a=argv[i];if(a=="--preserve-x-order"){preserve_x_order=true;continue;}if(i+1>=argc)throw runtime_error("missing option value");string v=argv[++i];if(a=="--input")input=v;else if(a=="--output")output=v;else if(a=="--seconds")seconds=stod(v);else if(a=="--seed")seed=stoull(v);else throw runtime_error("unknown "+a);}
    if(seconds<0)throw runtime_error("negative duration");
    ifstream f(input);int n;if(!(f>>n)||n<3||n>40)throw runtime_error("expected n in [3,40]");vector<P> p(n);for(auto&a:p)if(!(f>>a.x>>a.y)||a.x < -1000000000LL||a.x > 1000000000LL||a.y < -1000000000LL||a.y > 1000000000LL)throw runtime_error("invalid coordinate");
    vector<int>x_order(n),x_rank(n);iota(x_order.begin(),x_order.end(),0);
    sort(x_order.begin(),x_order.end(),[&](int a,int b){return p[a].x<p[b].x;});
    for(int i=0;i<n;i++){x_rank[x_order[i]]=i;if(preserve_x_order&&i&&p[x_order[i-1]].x==p[x_order[i]].x)throw runtime_error("--preserve-x-order requires distinct initial x coordinates");}
    int sign[40][40][40]{};for(int i=0;i<n;i++)for(int j=0;j<n;j++)for(int k=0;k<n;k++)if(i!=j&&i!=k&&j!=k){auto d=det(p[i],p[j],p[k]);if(!d)throw runtime_error("input not in general position");sign[i][j][k]=d>0?1:-1;}
    auto bounds=normalize(p);auto bestbounds=bounds;vector<P>best=p;mt19937_64 rng(seed);auto start=chrono::steady_clock::now();uint64_t moves=0,updates=0,improvements=0;
    auto elapsed=[&](){return chrono::duration<double>(chrono::steady_clock::now()-start).count();};
    auto log=[&](const char*event){cout<<"{\"event\":\""<<event<<"\",\"seed\":"<<seed<<",\"preserve_x_order\":"<<(preserve_x_order?"true":"false")<<",\"elapsed\":"<<elapsed()<<",\"moves\":"<<moves<<",\"updates\":"<<updates<<",\"width\":"<<bestbounds.first<<",\"height\":"<<bestbounds.second<<",\"area\":"<<objective(bestbounds)<<",\"improvements\":"<<improvements<<"}"<<endl;};
    save(output,best);log("start");double nextlog=10;
    while(elapsed()<seconds){
        moves++;int v=rng()%n,axis=rng()%2;int64_t old=axis?p[v].y:p[v].x;
        Wide lo=0,hi=axis?bounds.second:bounds.first;P zero=p[v],one=p[v];if(axis){zero.y=0;one.y=1;}else{zero.x=0;one.x=1;}
        if(preserve_x_order&&!axis){int rank=x_rank[v];if(rank>0)lo=max(lo,Wide(p[x_order[rank-1]].x)+1);if(rank+1<n)hi=min(hi,Wide(p[x_order[rank+1]].x)-1);}
        for(int j=0;j<n;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v){Wide b=det(zero,p[j],p[k])*sign[v][j][k];Wide a=(det(one,p[j],p[k])-det(zero,p[j],p[k]))*sign[v][j][k];if(a>0)lo=max(lo,ceil_div(1-b,a));else if(a<0)hi=min(hi,floor_div(1-b,a));else if(b<1)throw runtime_error("invalid invariant");}
        if(lo>hi||old<lo||old>hi)throw runtime_error("empty feasible interval");
        int64_t l=int64_t(lo),h=int64_t(hi),nv;
        // Half the steps spread uniformly, half bias extreme points inward.
        if(rng()%2 && old==0)nv=h;else if(rng()%2 && old==(axis?bounds.second:bounds.first))nv=l;else nv=l+int64_t(rng()%uint64_t(h-l+1));
        if(nv!=old){updates++;if(axis)p[v].y=nv;else p[v].x=nv;bounds=normalize(p);
            if(objective(bounds)<objective(bestbounds)){bestbounds=bounds;best=p;improvements++;save(output,best);if(improvements%100==0)log("best");}
        }
        // Occasionally apply a unimodular shear to escape an axis-dependent
        // feasible region, retaining it only if bounding area decreases.
        if(moves%1000==0){for(int ax=0;ax<2;ax++)for(int s:{-1,1}){if(preserve_x_order&&!ax)continue;auto trial=p;for(auto&a:trial){if(ax)a.y+=s*a.x;else a.x+=s*a.y;}auto tb=normalize(trial);if(objective(tb)<objective(bounds)){p.swap(trial);bounds=tb;if(objective(tb)<objective(bestbounds)){best=p;bestbounds=tb;improvements++;save(output,best);}}}}
        if(elapsed()>=nextlog){log("progress");nextlog=elapsed()+10;}
    }
    for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++)if(det(best[i],best[j],best[k])*sign[i][j][k]<=0)throw runtime_error("final order type mismatch");
    if(preserve_x_order)for(int i=1;i<n;i++)if(best[x_order[i-1]].x>=best[x_order[i]].x)throw runtime_error("final x order mismatch");
    save(output,best);log("done");
}catch(const exception&e){cerr<<e.what()<<'\n';return 2;}
