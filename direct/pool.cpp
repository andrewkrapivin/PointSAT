// Geometric large-neighborhood search for 23 points: retain a valid 22-point
// configuration, add proposed integer-coordinate candidates, then solve the
// fixed-pool subset problem exactly (or up to a short deadline). Failed rounds
// may replace existing points while preserving a valid 22-point incumbent.
#define main fixed_subset_cli_main
#include "subset.cpp"
#undef main

using Points=std::vector<Point>;
std::vector<int> hull_ids(const Points& p) {
    std::vector<int> order(p.size()),h;std::iota(order.begin(),order.end(),0);
    std::sort(order.begin(),order.end(),[&](int a,int b){return p[a].x<p[b].x||(p[a].x==p[b].x&&p[a].y<p[b].y);});
    for(int i:order){while(h.size()>1&&det(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}
    auto lower=h.size();for(int j=int(order.size())-2;j>=0;--j){int i=order[j];while(h.size()>lower&&det(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}
    h.pop_back();return h;
}
void write_points(const std::string& path,const Points& p) {
    std::ofstream f(path);if(!f)throw std::runtime_error("cannot write "+path);
    f << p.size() << '\n';for(auto q:p)f << q.x << ' ' << q.y << '\n';
}
void prepare(Search& s,bool fans=true) {
    int n=s.points.size();s.full=(Mask(1)<<n)-1;
    s.sorted.resize(n);std::iota(s.sorted.begin(),s.sorted.end(),0);
    std::sort(s.sorted.begin(),s.sorted.end(),[&](int a,int b){return s.points[a].x<s.points[b].x||(s.points[a].x==s.points[b].x&&s.points[a].y<s.points[b].y);});
    for(int i=0;i<n;++i)for(int j=i+1;j<n;++j)for(int k=j+1;k<n;++k) {
        Wide d=det(s.points[i],s.points[j],s.points[k]);if(!d)throw std::runtime_error("pool not in general position");
        if(d>0){s.left[i][j]|=Mask(1)<<k;s.left[j][k]|=Mask(1)<<i;s.left[k][i]|=Mask(1)<<j;}
        else{s.left[j][i]|=Mask(1)<<k;s.left[k][j]|=Mask(1)<<i;s.left[i][k]|=Mask(1)<<j;}
    }
    if(fans)s.precompute_fans();else{s.precompute_k(7,false);s.precompute_k(6,true);}s.precompute_seconds=s.elapsed();
}
Points selected(const Search& s) {
    Points p;for(int i=0;i<int(s.points.size());++i)if(s.best&(Mask(1)<<i))p.push_back(s.points[i]);return p;
}
int main(int argc,char** argv)try {
    std::string input,output="pool-best.pts";int pool_size=28;double seconds=60,pool_seconds=1;uint64_t seed=1;
    for(int i=1;i<argc;++i) {
        std::string a=argv[i];if(i+1>=argc)throw std::runtime_error("missing value");std::string v=argv[++i];
        if(a=="--input")input=v;else if(a=="--output")output=v;else if(a=="--seconds")seconds=std::stod(v);
        else if(a=="--pool-seconds")pool_seconds=std::stod(v);else if(a=="--pool-size")pool_size=std::stoi(v);
        else if(a=="--seed")seed=std::stoull(v);else throw std::runtime_error("unknown option "+a);
    }
    if(seconds<=0||pool_seconds<=0||!std::isfinite(seconds)||!std::isfinite(pool_seconds)||pool_size<24||pool_size>34)
        throw std::runtime_error("require positive finite times and pool-size24..34");
    std::ifstream f(input);int n;if(!(f>>n)||n!=22)throw std::runtime_error("pool requires a valid22-point input");
    Points base(n);for(auto& p:base)if(!(f>>p.x>>p.y)||p.x < -1000000000LL||p.x>1000000000LL||p.y < -1000000000LL||p.y>1000000000LL)throw std::runtime_error("invalid coordinate,limit1e9");
    // Check the starting seed using the complete fixed-coordinate constraints.
    Search initial;initial.points=base;initial.start=Clock::now();initial.seconds=60;initial.quiet=true;initial.write_best=false;prepare(initial,false);
    for(auto p:initial.polygons)if(initial.active(p,initial.full))throw std::runtime_error("input violates7gon/6hole restriction");
    auto start=Clock::now();auto elapsed=[&](){return std::chrono::duration<double>(Clock::now()-start).count();};
    std::mt19937_64 random(seed);std::uniform_real_distribution<double> unit(0,1);
    uint64_t rounds=0,exhausted=0,changed=0,nodes=0,candidates=0;double next_log=0,precompute_total=0;
    write_points(output,base);
    auto log=[&](const char* event){std::cout << "{\"event\":\"" << event << "\",\"method\":\"geometric_candidate_pool\",\"seed\":" << seed
        << ",\"pool_size\":" << pool_size << ",\"elapsed\":" << elapsed() << ",\"rounds\":" << rounds << ",\"exhausted_pools\":" << exhausted
        << ",\"accepted_replacements\":" << changed << ",\"candidate_points\":" << candidates << ",\"subset_nodes\":" << nodes
        << ",\"precompute_seconds\":" << precompute_total << ",\"best_n\":" << base.size() << ",\"hull_size\":" << hull_ids(base).size() << "}" << std::endl;};
    log("start");
    while(elapsed()<seconds&&base.size()<23) {
        ++rounds;Search s;s.start=Clock::now();s.seconds=std::min(pool_seconds,seconds-elapsed());s.points=base;s.quiet=true;s.write_best=false;s.random.seed(random());
        int64_t minx=base[0].x,maxx=minx,miny=base[0].y,maxy=miny;
        for(auto p:base){minx=std::min(minx,p.x);maxx=std::max(maxx,p.x);miny=std::min(miny,p.y);maxy=std::max(maxy,p.y);}
        const double span=std::max(maxx-minx,maxy-miny);
        int attempts=0;
        while(int(s.points.size())<pool_size) {
            if(++attempts>100000)throw std::runtime_error("candidate generation stalled");
            Point p{};int mode=random()%4;
            if(mode==0){p.x=std::llround(minx+(maxx-minx)*(-.15+1.3*unit(random)));p.y=std::llround(miny+(maxy-miny)*(-.15+1.3*unit(random)));}
            else if(mode==1||mode==3) {
                p=base[random()%base.size()];double scale=span*std::pow(10.,-5.+4.*unit(random));
                std::normal_distribution<double> normal(0,std::max(2.,scale));p.x+=std::llround(normal(random));p.y+=std::llround(normal(random));
            }else{
                int a=random()%n,b=random()%n,c=random()%n,d=random()%n;
                if(a==b||a==c||a==d||b==c||b==d||c==d)continue;
                long double ux=base[b].x-base[a].x,uy=base[b].y-base[a].y,vx=base[d].x-base[c].x,vy=base[d].y-base[c].y;
                long double denominator=ux*vy-uy*vx;if(std::abs(denominator)<1)continue;
                long double t=((base[c].x-base[a].x)*vy-(base[c].y-base[a].y)*vx)/denominator;
                long double x=base[a].x+t*ux,y=base[a].y+t*uy;
                if(x<minx-span||x>maxx+span||y<miny-span||y>maxy+span)continue;
                double radius=std::max(2.,span*std::pow(10.,-7.+3.*unit(random)));
                std::normal_distribution<double> normal(0,radius);p.x=std::llround(x+normal(random));p.y=std::llround(y+normal(random));
            }
            if(p.x < -1000000000LL||p.x>1000000000LL||p.y < -1000000000LL||p.y>1000000000LL)continue;
            bool gp=true;for(int i=0;i<int(s.points.size())&&gp;++i)for(int j=i+1;j<int(s.points.size())&&gp;++j)if(!det(s.points[i],s.points[j],p))gp=false;
            if(gp){s.points.push_back(p);++candidates;}
        }
        prepare(s);precompute_total+=s.precompute_seconds;s.best_n=n;s.best=(Mask(1)<<n)-1;s.target=23;
        if(!s.timed_out){s.dfs(s.full);if(!s.timed_out&&!s.reached_target)++exhausted;}
        if(s.reached_target){base=selected(s);write_points(output,base);nodes+=s.nodes;log("solution");break;}
        if(!s.timed_out&&elapsed()<seconds) {
            // Search for an equal-size valid replacement after excluding one
            // old vertex. The threshold21 is used only to seek size>=22; no
            // size21 lower-bound claim or output is made by this auxiliary call.
            auto outer=hull_ids(base);int excluded=random()%3?outer[random()%outer.size()]:int(random()%n);
            s.visited.clear();s.best_n=n-1;s.best=0;s.target=n;s.reached_target=false;
            s.seconds=std::min(s.elapsed()+.04,seconds-std::chrono::duration<double>(s.start-start).count());
            s.dfs(s.full&~(Mask(1)<<excluded));
            if(s.reached_target){auto next=selected(s);if(next.size()>=23||hull_ids(next).size()<=outer.size()||random()%10==0){base=std::move(next);++changed;write_points(output,base);}}
        }
        nodes+=s.nodes;
        if(elapsed()>=next_log){log("progress");next_log=elapsed()+10;}
    }
    write_points(output,base);log("done");return 0;
}catch(const std::exception& e){std::cerr << "pool: " << e.what() << '\n';return 2;}
