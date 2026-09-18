// Direct integer-coordinate search. No SAT solver or realizability oracle.
// Convex polygons are counted by angular fan dynamic programming, each once,
// at their lexicographically leftmost vertex. Empty fans use bitset triangle
// emptiness. All orientation predicates are exact for the bounded input domain.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
struct Point { int64_t x,y; };
using Points=vector<Point>;
static __int128 cross(Point a,Point b,Point c) {
    return (__int128(b.x)-a.x)*(__int128(c.y)-a.y)-(__int128(b.y)-a.y)*(__int128(c.x)-a.x);
}
static bool lessxy(Point a,Point b) {return a.x<b.x || (a.x==b.x && a.y<b.y);}
static Points read_points(const string& fn) {
    ifstream f(fn); int n; if(!(f>>n)||n<3||n>40) throw runtime_error("input: expected n in [3,40]");
    Points p(n); for(auto& a:p) if(!(f>>a.x>>a.y)||a.x < -1000000000LL||a.x > 1000000000LL||a.y < -1000000000LL||a.y > 1000000000LL) throw runtime_error("invalid coordinate (limit 1e9)");
    return p;
}
static void save(const string& fn,const Points& p) {
    ofstream f(fn); if(!f)throw runtime_error("cannot write "+fn);
    f<<p.size()<<'\n';for(auto a:p)f<<a.x<<' '<<a.y<<'\n';
}
struct Score {uint64_t gon=0,hole=0,cap=0;int collinear=0;uint64_t total()const{return gon+hole+cap+uint64_t(collinear)*1000000;}};
struct Geometry {
    int n=0; uint64_t left[40][40]{};
    bool build(const Points& p) {
        n=p.size();fill(&left[0][0],&left[0][0]+1600,0);bool gp=true;
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++) {
            auto d=cross(p[i],p[j],p[k]);if(!d){gp=false;continue;}
            if(d>0){left[i][j]|=1ULL<<k;left[j][k]|=1ULL<<i;left[k][i]|=1ULL<<j;}
            else{left[j][i]|=1ULL<<k;left[k][j]|=1ULL<<i;left[i][k]|=1ULL<<j;}
        }return gp;
    }
    bool same(const Geometry& g)const {
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)if(left[i][j]!=g.left[i][j])return false;
        return true;
    }
    Score count(const Points& p,int gon,int hole,vector<int>* witness=nullptr,int offset=0,uint64_t cutoff=numeric_limits<uint64_t>::max())const {
        Score s; const int maxk=max(gon,hole);
        if(witness)witness->clear();
        for(int pp=0;pp<n;pp++) {
            int pivot=(pp+offset)%n;
            int order[40],m=0;for(int j=0;j<n;j++)if(lessxy(p[pivot],p[j]))order[m++]=j;
            if(m+1<min(gon?gon:99,hole?hole:99))continue;
            sort(order,order+m,[&](int a,int b){return (left[pivot][a]>>b)&1;});
            // dp[length][previous][last]. Separate convex/empty chain counts.
            uint64_t dg[10][40][40]{},dh[10][40][40]{};
            for(int j=0;j<m;j++)for(int k=j+1;k<m;k++) {
                int b=order[j],c=order[k];bool empty=!(left[pivot][b]&left[b][c]&left[c][pivot]);
                if(gon)dg[3][j][k]=1;
                if(hole&&empty)dh[3][j][k]=1;
                for(int i=0;i<j;i++)if((left[order[i]][b]>>c)&1) {
                    for(int len=4;len<=maxk;len++) {
                        if(gon&&len<=gon)dg[len][j][k]+=dg[len-1][i][j];
                        if(hole&&empty&&len<=hole)dh[len][j][k]+=dh[len-1][i][j];
                    }
                }
                if(gon)s.gon+=dg[gon][j][k];
                if(hole)s.hole+=dh[hole][j][k];
                if(witness && witness->empty() && ((gon&&dg[gon][j][k])||(hole&&dh[hole][j][k]))) {
                    bool usehole=hole&&dh[hole][j][k];int len=usehole?hole:gon;
                    auto&dp=usehole?dh:dg;int u=j,v=k;*witness={pivot,order[u],order[v]};
                    while(len>3){int i=0;for(;i<u;i++)if(((left[order[i]][order[u]]>>order[v])&1)&&dp[len-1][i][u])break;if(i==u)throw runtime_error("DP witness failure");witness->push_back(order[i]);v=u;u=i;len--;}
                }
            }
            if(s.total()>cutoff)return s;
        }return s;
    }
    uint64_t caps(const Points&p,int k)const {
        if(!k)return 0;
        int order[40];iota(order,order+n,0);sort(order,order+n,[&](int a,int b){return lessxy(p[a],p[b]);});
        uint64_t dp[10][40][40]{},total=0;
        for(int j=0;j<n;j++)for(int q=j+1;q<n;q++) {
            if(p[order[j]].x==p[order[q]].x)continue;
            dp[2][j][q]=1;
            for(int i=0;i<j;i++)if((left[order[q]][order[j]]>>order[i])&1)for(int len=3;len<=k;len++)dp[len][j][q]+=dp[len-1][i][j];
            total+=dp[k][j][q];
        }return total;
    }
};
static Points random_points(int n,int64_t grid,mt19937_64& rng,bool layered=false) {
    Points p;Geometry g;uniform_int_distribution<int64_t> u(0,grid);
    for(int i=0;i<n;i++) {int tries=0;do {
        Point a{u(rng),u(rng)};
        if(layered){double angle=(rng()%10000000)*6.283185307179586/10000000.;double radius=grid*.48*pow(.55,i/6);a={int64_t(grid/2+cos(angle)*radius),int64_t(grid/2+sin(angle)*radius)};}
        if(p.size()>size_t(i))p.back()=a;else p.push_back(a);
        if(++tries>100000)throw runtime_error("grid too small");
    }while(!g.build(p));}return p;
}
static double elapsed(Clock::time_point t){return chrono::duration<double>(Clock::now()-t).count();}
#ifndef POINTSAT_GEOMETRY_ONLY
int main(int argc,char**argv)try {
    int n=23,gon=7,hole=6,cap=0;uint64_t seed=1;double seconds=60,temp=2.;int64_t grid=1000000;
    string mode="anneal",input,output="best.pts";bool count_only=false,stop=false;
    for(int i=1;i<argc;i++) {string a=argv[i];auto value=[&](){if(++i>=argc)throw runtime_error("missing "+a);return string(argv[i]);};
        if(a=="--n")n=stoi(value());else if(a=="--gon")gon=stoi(value());else if(a=="--hole")hole=stoi(value());else if(a=="--cap")cap=stoi(value());
        else if(a=="--seed")seed=stoull(value());else if(a=="--seconds")seconds=stod(value());else if(a=="--grid")grid=stoll(value());
        else if(a=="--temperature")temp=stod(value());else if(a=="--mode")mode=value();else if(a=="--input")input=value();else if(a=="--output")output=value();
        else if(a=="--count")count_only=true;else if(a=="--stop-on-solution")stop=true;
        else throw runtime_error("unknown option "+a);
    }
    if(n<3||n>40||gon<0||gon>9||hole<0||hole>9||cap<0||cap>9||(gon&&gon<3)||(hole&&hole<3)||(cap&&cap<3)||(!gon&&!hole&&!cap)||grid<10||grid>1000000000||seconds<0||temp<=0)throw runtime_error("invalid parameters");
    if(mode!="anneal"&&mode!="late"&&mode!="repair")throw runtime_error("mode must be anneal, late or repair");
    mt19937_64 rng(seed);Points p=input.empty()?random_points(n,grid,rng):read_points(input);n=p.size();Geometry geom;
    if(!geom.build(p))throw runtime_error("input not in general position");
    Score score=geom.count(p,gon,hole);score.cap=geom.caps(p,cap);
    if(count_only){cout<<"{\"n\":"<<n<<",\"gons\":"<<score.gon<<",\"holes\":"<<score.hole<<",\"caps\":"<<score.cap<<",\"general_position\":true}\n";return 0;}
    if(!input.empty()) {
        int64_t minx=p[0].x,miny=p[0].y,maxx=minx,maxy=miny;
        for(auto a:p){minx=min(minx,a.x);miny=min(miny,a.y);maxx=max(maxx,a.x);maxy=max(maxy,a.y);}
        for(auto&a:p){a.x=llround(double(a.x-minx)*grid/max<int64_t>(1,maxx-minx));a.y=llround(double(a.y-miny)*grid/max<int64_t>(1,maxy-miny));}
        // Rounding to a requested small grid can introduce collinear triples.
        // Jitter them before optimization; this is a new scored starting set,
        // not an assertion that the seed's order type survived rescaling.
        for(int attempt=0;!geom.build(p);attempt++) {
            if(attempt==100000)throw runtime_error("could not obtain GP after scaling seed");
            bool found=false;
            for(int i=0;i<n&&!found;i++)for(int j=i+1;j<n&&!found;j++)for(int k=j+1;k<n&&!found;k++)if(!cross(p[i],p[j],p[k])) {
                int v=array<int,3>{i,j,k}[rng()%3];p[v].x=clamp<int64_t>(p[v].x+int(rng()%3)-1,0,grid);p[v].y=clamp<int64_t>(p[v].y+int(rng()%3)-1,0,grid);found=true;
            }
        }
    }
    vector<int>witness;score=geom.count(p,gon,hole,mode=="repair"?&witness:nullptr);score.cap=geom.caps(p,cap);
    auto start=Clock::now();Points best=p;Score bs=score;uint64_t proposals=0,evaluations=1,accepted=0,restarts=0,neutral=0,last_improve=0;
    array<uint64_t,512> history;history.fill(score.total());double next_log=0;uniform_real_distribution<double> unit(0,1);
    auto log=[&](const char* event){cout<<"{\"event\":\""<<event<<"\",\"mode\":\""<<mode<<"\",\"seed\":"<<seed<<",\"n\":"<<n<<",\"gon\":"<<gon<<",\"hole\":"<<hole<<",\"cap\":"<<cap<<",\"elapsed\":"<<elapsed(start)<<",\"proposals\":"<<proposals<<",\"evaluations\":"<<evaluations<<",\"accepted\":"<<accepted<<",\"neutral\":"<<neutral<<",\"restarts\":"<<restarts<<",\"gons\":"<<score.gon<<",\"holes\":"<<score.hole<<",\"caps\":"<<score.cap<<",\"best_gons\":"<<bs.gon<<",\"best_holes\":"<<bs.hole<<",\"best_caps\":"<<bs.cap<<",\"best_score\":"<<bs.total()<<"}"<<endl;};
    save(output,best);log("start");
    while(elapsed(start)<seconds && !(stop&&bs.total()==0)) {
        proposals++;int v=rng()%n;if(mode=="repair"&&!witness.empty()&&rng()%3)v=witness[rng()%witness.size()];Points trial=p;double scale=pow(10.,-1.-4.*unit(rng));
        if(mode=="repair" && rng()%2) {
            // Cross the nearest line through two other points along a random
            // ray: an order-type cell move. Floating point proposes only;
            // all acceptance and validity decisions use exact predicates.
            double angle=unit(rng)*6.283185307179586,dx=cos(angle),dy=sin(angle),distance=2.*grid;
            for(int j=0;j<n;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v) {
                double d=double(cross(p[v],p[j],p[k]));double derivative=dx*double(p[j].y-p[k].y)+dy*double(p[k].x-p[j].x);
                if(derivative!=0){double t=-d/derivative;if(t>0)distance=min(distance,t);}
            }
            distance=distance*(1.+pow(10.,-3.*unit(rng)))+2.;
            trial[v].x=clamp<int64_t>(p[v].x+llround(dx*distance),0,grid);trial[v].y=clamp<int64_t>(p[v].y+llround(dy*distance),0,grid);
        }
        else if(rng()%20==0){trial[v]={int64_t(rng()%(grid+1)),int64_t(rng()%(grid+1))};}
        else {normal_distribution<double> normal(0,max(1.,grid*scale));trial[v].x=clamp<int64_t>(trial[v].x+llround(normal(rng)),0,grid);trial[v].y=clamp<int64_t>(trial[v].y+llround(normal(rng)),0,grid);}
        Geometry ng;if(!ng.build(trial))continue;
        if(!cap&&ng.same(geom)){neutral++;p.swap(trial);continue;}
        vector<int> nw;Score ns=ng.count(trial,gon,hole,mode=="repair"?&nw:nullptr,int(rng()%n));ns.cap=ng.caps(trial,cap);evaluations++;int64_t delta=int64_t(ns.total())-int64_t(score.total());
        double temperature=temp*(.1+.9*exp(-double(evaluations%20000)/4000.));bool take=delta<=0;
        if(mode=="anneal")take=take||unit(rng)<exp(-double(delta)/temperature);
        if(mode=="late")take=take||ns.total()<=history[evaluations%history.size()];
        if(mode=="repair")take=take||unit(rng)<exp(-double(delta)/temperature);
        if(take){p.swap(trial);geom=ng;score=ns;witness.swap(nw);accepted++;}history[evaluations%history.size()]=score.total();
        if(score.total()<bs.total()){bs=score;best=p;last_improve=evaluations;save(output,best);log("best");}
        if(evaluations-last_improve>25000) {
            restarts++;last_improve=evaluations;
            if(restarts%5==0&&input.empty())p=random_points(n,grid,rng,restarts%10==0);else p=best;
            geom.build(p);score=geom.count(p,gon,hole);score.cap=geom.caps(p,cap);history.fill(score.total());
            // Kick several coordinates; subsequent search repairs the violations.
            if(restarts%5!=0)for(int j=0;j<2;j++){int k=rng()%n;p[k].x=clamp<int64_t>(p[k].x+int64_t(rng()%(grid/10+1))-grid/20,0,grid);p[k].y=clamp<int64_t>(p[k].y+int64_t(rng()%(grid/10+1))-grid/20,0,grid);}
            if(!geom.build(p)){p=best;geom.build(p);}score=geom.count(p,gon,hole,mode=="repair"?&witness:nullptr);score.cap=geom.caps(p,cap);evaluations++;
        }
        if(elapsed(start)>=next_log){log("progress");next_log=elapsed(start)+10.;}
    }
    save(output,best);log("done");return 0;
}catch(const exception&e){cerr<<e.what()<<'\n';return 2;}
#endif
