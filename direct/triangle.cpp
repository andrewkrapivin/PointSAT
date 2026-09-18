// Search only configurations with a triangular hull. For n=23 avoiding
// 7-gons and 6-holes this loses no real solutions: the hull must be a triangle
// (PointSAT Theorem 5.1), and an affine map fixes its three corners.
// Shared exact counting oracle; independent verifier remains separate.
#define POINTSAT_GEOMETRY_ONLY
#include "search.cpp"

static vector<int> convex_hull(const Points&p) {
    vector<int>a(p.size()),h;iota(a.begin(),a.end(),0);sort(a.begin(),a.end(),[&](int i,int j){return lessxy(p[i],p[j]);});
    for(int i:a){while(h.size()>1&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}
    size_t low=h.size();for(int k=int(a.size())-2;k>=0;k--){int i=a[k];while(h.size()>low&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}if(h.size()>1)h.pop_back();return h;
}
static bool update(Geometry&g,const Points&p,int v) {
    for(int i=0;i<g.n;i++)if(i!=v)for(int j=i+1;j<g.n;j++)if(j!=v) {
        auto d=cross(p[v],p[i],p[j]);if(!d)return false;
        g.left[v][i]&=~(1ULL<<j);g.left[i][v]&=~(1ULL<<j);
        g.left[v][j]&=~(1ULL<<i);g.left[j][v]&=~(1ULL<<i);
        g.left[i][j]&=~(1ULL<<v);g.left[j][i]&=~(1ULL<<v);
        if(d>0){g.left[v][i]|=1ULL<<j;g.left[i][j]|=1ULL<<v;g.left[j][v]|=1ULL<<i;}
        else{g.left[i][v]|=1ULL<<j;g.left[j][i]|=1ULL<<v;g.left[v][j]|=1ULL<<i;}
    }return true;
}
int main(int argc,char**argv)try{
    int n=23;int64_t grid=100000000;double seconds=600,temp=.5;uint64_t seed=1,iterations=numeric_limits<uint64_t>::max();bool cutoff=true,archive=true;string input,output="triangle.pts",mode="anneal";
    for(int i=1;i<argc;i++){string a=argv[i];if(i+1==argc)throw runtime_error("missing value "+a);string v=argv[++i];if(a=="--n")n=stoi(v);else if(a=="--grid")grid=stoll(v);else if(a=="--seconds")seconds=stod(v);else if(a=="--seed")seed=stoull(v);else if(a=="--temperature")temp=stod(v);else if(a=="--input")input=v;else if(a=="--output")output=v;else if(a=="--mode")mode=v;else if(a=="--cutoff")cutoff=stoi(v);else if(a=="--iterations")iterations=stoull(v);else if(a=="--archive")archive=stoi(v);else throw runtime_error("unknown option "+a);}
    if(n<7||n>40||grid<100||grid>1000000000||seconds<0||temp<=0||(mode!="anneal"&&mode!="late"))throw runtime_error("invalid arguments");
    mt19937_64 rng(seed);uniform_real_distribution<double>unif(0,1);Geometry g;
    auto random_inside=[&](){Point a;do{a={int64_t(1+rng()%(grid-1)),int64_t(1+rng()%(grid-1))};}while(a.x+a.y>=grid);return a;};
    auto interior=[&](Point a){return a.x>0&&a.y>0&&a.x+a.y<grid;};
    auto initial=[&](){Points p={{0,0},{grid,0},{0,grid}};while(int(p.size())<n){p.push_back(random_inside());if(!g.build(p))p.pop_back();}return p;};
    Points p;
    if(input.empty())p=initial();
    else {
        auto old=read_points(input);auto h=convex_hull(old);if(h.size()!=3||int(old.size())>n)throw runtime_error("seed must have triangular hull and at most n points");
        Point a=old[h[0]],b=old[h[1]],c=old[h[2]];long double d=cross(a,b,c);p={{0,0},{grid,0},{0,grid}};
        for(int i=0;i<int(old.size());i++)if(find(h.begin(),h.end(),i)==h.end())p.push_back({llround(grid*(long double)cross(a,old[i],c)/d),llround(grid*(long double)cross(a,b,old[i])/d)});
        for(int attempts=0;!g.build(p);attempts++){if(attempts>10000)throw runtime_error("seed rounding could not recover GP");int v=3+rng()%(p.size()-3);p[v].x+=int(rng()%3)-1;p[v].y+=int(rng()%3)-1;if(!interior(p[v]))p[v]=random_inside();}
        while(int(p.size())<n){p.push_back(random_inside());if(!g.build(p))p.pop_back();}
    }
    g.build(p);vector<int>witness;Score score=g.count(p,7,6,&witness);Points best=p;Score bs=score;auto start=Clock::now();
    uint64_t proposals=0,evaluations=1,accepts=0,neutral=0,last_improve=0,restarts=0;double nextlog=10;
    array<uint64_t,1024>history;history.fill(score.total());
    vector<Points>elite{p};
    auto log=[&](const char*event){cout<<"{\"event\":\""<<event<<"\",\"method\":\"triangle_"<<mode<<"\",\"seed\":"<<seed<<",\"n\":"<<n<<",\"elapsed\":"<<elapsed(start)<<",\"proposals\":"<<proposals<<",\"evaluations\":"<<evaluations<<",\"accepted\":"<<accepts<<",\"neutral\":"<<neutral<<",\"restarts\":"<<restarts<<",\"best_gons\":"<<bs.gon<<",\"best_holes\":"<<bs.hole<<",\"best_score\":"<<bs.total()<<"}"<<endl;};
    save(output,best);log("start");
    while(elapsed(start)<seconds&&bs.total()>0&&proposals<iterations){
        proposals++;int v=3+rng()%(n-3);if(!witness.empty()&&rng()%3){int q=witness[rng()%witness.size()];if(q>=3)v=q;}
        Points trial=p;
        if(rng()%25==0)trial[v]=random_inside();
        else if(rng()%2){double angle=unif(rng)*6.283185307179586,dx=cos(angle),dy=sin(angle),distance=2.*grid;
            for(int j=0;j<n;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v){double d=double(cross(p[v],p[j],p[k]));double slope=dx*double(p[j].y-p[k].y)+dy*double(p[k].x-p[j].x);if(slope){double t=-d/slope;if(t>0)distance=min(distance,t);}}
            distance=distance*(1+pow(10.,-3*unif(rng)))+2;trial[v]={p[v].x+llround(dx*distance),p[v].y+llround(dy*distance)};
        }else{normal_distribution<double>normal(0,max(1.,grid*pow(10.,-1-5*unif(rng))));trial[v]={p[v].x+llround(normal(rng)),p[v].y+llround(normal(rng))};}
        if(!interior(trial[v]))continue;
        Geometry ng=g;if(!update(ng,trial,v))continue;
        if(ng.same(g)){neutral++;p.swap(trial);continue;}
        evaluations++;double t=temp*(.15+.85*exp(-double(evaluations%50000)/10000));
        // Sample the Metropolis acceptance threshold before counting. A partial
        // count beyond that threshold proves rejection, so stop immediately.
        uint64_t limit=mode=="late"?max(score.total(),history[evaluations%history.size()]):score.total()+uint64_t(-t*std::log(max(1e-300,unif(rng))));
        vector<int>nw;Score ns=ng.count(trial,7,6,&nw,rng()%n,cutoff?limit:numeric_limits<uint64_t>::max());
        bool take=ns.total()<=limit;
        if(take){p.swap(trial);g=ng;score=ns;witness.swap(nw);accepts++;}history[evaluations%history.size()]=score.total();
        if(score.total()<bs.total()){bs=score;best=p;elite={p};save(output,best);last_improve=evaluations;log("best");}
        else if(archive&&take&&score.total()==bs.total()&&evaluations%31==0){if(elite.size()<64)elite.push_back(p);else elite[rng()%elite.size()]=p;}
        if(evaluations-last_improve>100000){restarts++;last_improve=evaluations;
            if(restarts%5==0&&input.empty())p=initial();else{p=archive?elite[rng()%elite.size()]:best;for(int z=0;z<2;z++){int q=3+rng()%(n-3);p[q]=random_inside();}}
            if(!g.build(p)){p=best;g.build(p);}score=g.count(p,7,6,&witness);evaluations++;history.fill(score.total());
        }
        if(elapsed(start)>nextlog){log("progress");nextlog=elapsed(start)+10;}
    }
    Geometry check;if(!check.build(best)||check.count(best,7,6).total()!=bs.total())throw runtime_error("final exact score mismatch");
    save(output,best);log("done");return 0;
}catch(const exception&e){cerr<<e.what()<<'\n';return 2;}
