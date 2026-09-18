// Direct exact-coordinate search for 19 points with no 0-/3-interior hexagon.
// This optimizes the geometric property, not a fixed abstract order type.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using i64=std::int64_t;
using i128=__int128_t;
constexpr int M=19;
constexpr int INF=100000000;
static int hole_weight=1,three_weight=1;
struct Point { i64 x=0,y=0; bool operator==(const Point&o)const{return x==o.x&&y==o.y;} };
static bool lex(const Point&a,const Point&b){return a.x<b.x||(a.x==b.x&&a.y<b.y);}
static int turn(const Point&a,const Point&b,const Point&c){
    i128 d=i128(b.x-a.x)*(c.y-a.y)-i128(b.y-a.y)*(c.x-a.x);
    return (d>0)-(d<0);
}
static int pop(std::uint32_t a){return __builtin_popcount(a);}
struct BadPolygon { std::uint32_t vertices,inside; };
struct Score {
    int holes=0,three=0,collinear=0;
    std::array<int,M> weights{};
    std::vector<BadPolygon> bad;
    int raw()const{return collinear?INF+collinear:holes+three;}
    int value()const{return collinear?INF+collinear:hole_weight*holes+three_weight*three;}
};
struct Geometry {
    int n=0,collinear=0;
    std::array<Point,M> p{};
    std::array<std::int8_t,M*M*M> signs{};
    std::array<std::uint32_t,M*M> left{};
    int sign(int a,int b,int c)const{return signs[(a*M+b)*M+c];}
    void edge(int a,int b,int c,int s){
        std::uint32_t bit=std::uint32_t(1)<<c;
        left[a*M+b]=(left[a*M+b]&~bit)|(s>0?bit:0);
        left[b*M+a]=(left[b*M+a]&~bit)|(s<0?bit:0);
    }
    void triangle(int i,int j,int k){
        int old=sign(i,j,k),s=turn(p[i],p[j],p[k]);
        collinear+=(s==0)-(old==0);
        signs[(i*M+j)*M+k]=signs[(j*M+k)*M+i]=signs[(k*M+i)*M+j]=s;
        signs[(i*M+k)*M+j]=signs[(k*M+j)*M+i]=signs[(j*M+i)*M+k]=-s;
        edge(i,j,k,s);edge(j,k,i,s);edge(k,i,j,s);
    }
    void build(){
        signs.fill(0);left.fill(0);collinear=n*(n-1)*(n-2)/6;
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++)triangle(i,j,k);
    }
    void update(std::uint32_t changed){
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++)
            if(changed&((1u<<i)|(1u<<j)|(1u<<k)))triangle(i,j,k);
    }
    std::uint32_t interior(int a,int b,int c)const{
        return left[a*M+b]&left[b*M+c]&left[c*M+a];
    }
    Score score(int cutoff=INF,bool details=true)const{
        Score out;out.collinear=collinear;
        if(collinear)return out;
        if(details)out.bad.reserve(32);
        std::array<int,M> order{};
        std::iota(order.begin(),order.begin()+n,0);
        std::sort(order.begin(),order.begin()+n,[&](int a,int b){return lex(p[a],p[b]);});
        bool stop=false;
        // Each polygon is generated once, with its lexicographically leftmost
        // vertex as fan apex and all other vertices in increasing polar order.
        for(int ai=0;ai+5<n&&!stop;ai++){
            int a=order[ai],m=n-ai-1;
            std::array<int,M> q{};
            std::copy(order.begin()+ai+1,order.begin()+n,q.begin());
            std::sort(q.begin(),q.begin()+m,[&](int b,int c){return sign(a,b,c)>0;});
            auto dfs=[&](auto&&self,int depth,int last,int prevprev,int prev,
                         std::uint32_t inside,std::uint32_t vertices)->void{
                if(stop)return;
                if(depth==5){
                    int count=pop(inside);
                    if(count!=0&&count!=3)return;
                    if(count==0)out.holes++;else out.three++;
                    if(details){
                        out.bad.push_back({vertices,inside});
                        for(int v=0;v<n;v++){
                            int weight=count==0?hole_weight:three_weight;
                            if(vertices&(1u<<v))out.weights[v]+=weight;
                            if(inside&(1u<<v))out.weights[v]+=2*weight;
                        }
                    }
                    stop=out.value()>cutoff;
                    return;
                }
                for(int k=last+1;k<=m-5+depth&&!stop;k++){
                    int next=q[k];
                    if(sign(prevprev,prev,next)<=0)continue;
                    std::uint32_t mask=inside|interior(a,prev,next);
                    // Fan triangle interiors are disjoint; later additions
                    // cannot remove an interior point.
                    if(pop(mask)>3)continue;
                    self(self,depth+1,k,prev,next,mask,vertices|(1u<<next));
                }
            };
            for(int i=0;i+4<m&&!stop;i++)for(int j=i+1;j+3<m&&!stop;j++){
                std::uint32_t mask=interior(a,q[i],q[j]);
                if(pop(mask)>3)continue;
                dfs(dfs,2,j,q[i],q[j],mask,(1u<<a)|(1u<<q[i])|(1u<<q[j]));
            }
        }
        return out;
    }
};
static std::atomic<bool> interrupted{false};
static void stop_handler(int){interrupted.store(true,std::memory_order_relaxed);}
static void write_points(const std::string&path,const Geometry&g){
    std::string temporary=path+".tmp";
    std::ofstream out(temporary);
    if(!out)throw std::runtime_error("cannot write "+path);
    out<<g.n<<'\n';
    for(int i=0;i<g.n;i++)out<<g.p[i].x<<' '<<g.p[i].y<<'\n';
    if(!out)throw std::runtime_error("write failed "+path);
    out.close();
    if(std::rename(temporary.c_str(),path.c_str()))throw std::runtime_error("rename failed "+path);
}
static Point rotate120(Point p){return {-p.y,p.x-p.y};}
static Geometry read_points(const std::string&path,long double scale,bool symmetry){
    std::ifstream in(path);if(!in)throw std::runtime_error("cannot read "+path);
    std::vector<std::vector<long double>> rows;
    std::string line;
    while(std::getline(in,line)){
        if(line.empty()||line[0]=='#')continue;
        std::istringstream stream(line);std::vector<long double> row;
        long double v;while(stream>>v)row.push_back(v);
        if(!stream.eof()||row.empty())throw std::runtime_error("malformed coordinate row");
        rows.push_back(row);
    }
    Geometry g;
    bool indexed=!rows.empty()&&rows[0].size()==3;
    if(indexed)g.n=rows.size();
    else{
        if(rows.empty()||rows[0].size()!=1)throw std::runtime_error("expected n + pairs or indexed real rows");
        g.n=int(rows[0][0]);rows.erase(rows.begin());
    }
    if(g.n<6||g.n>M||int(rows.size())!=g.n)throw std::runtime_error("expected 6..19 points");
    if(symmetry&&g.n!=19)throw std::runtime_error("symmetry requires 19 points");
    std::array<long double,M>x{},y{};
    for(int i=0;i<g.n;i++){
        if(rows[i].size()!=std::size_t(indexed?3:2)||(indexed&&rows[i][0]!=i+1))
            throw std::runtime_error("invalid point index/row");
        x[i]=rows[i][indexed?1:0];y[i]=rows[i][indexed?2:1];
        if(!std::isfinite(x[i])||!std::isfinite(y[i]))throw std::runtime_error("nonfinite coordinate");
    }
    long double factor=indexed?scale:1;
    if(symmetry&&indexed){
        if(g.n!=19)throw std::runtime_error("symmetry requires 19 points");
        long double cx=x[18],cy=y[18];
        for(int i=0;i<19;i++){
            long double xx=x[i]-cx,yy=y[i]-cy;
            x[i]=xx+yy/std::sqrt(3.0L);y[i]=2*yy/std::sqrt(3.0L);
        }
    }
    for(int i=0;i<g.n;i++){
        long double xx=x[i]*factor,yy=y[i]*factor;
        if(std::fabs(xx)>1e15L||std::fabs(yy)>1e15L)throw std::runtime_error("coordinate too large; use smaller --scale");
        g.p[i]={i64(std::llround(xx)),i64(std::llround(yy))};
    }
    if(symmetry){
        for(int i=0;i<18;i+=3){g.p[i+1]=rotate120(g.p[i]);g.p[i+2]=rotate120(g.p[i+1]);}
        g.p[18]={0,0};
    }
    g.build();return g;
}
struct Search {
    std::mt19937_64 rng;
    bool symmetry;
    double temperature;
    double min_exponent=-8,max_exponent=-0.2;
    explicit Search(std::uint64_t seed,bool sym,double t):rng(seed),symmetry(sym),temperature(t){}
    double unit(){return (rng()>>11)*0x1.0p-53;}
    int index(int n){return int(rng()%n);}
    i64 integer(i64 radius){return i64(rng()%(std::uint64_t(2*radius)+1))-radius;}
    int choose(const Score&s,int n){
        int sum=0;for(int i=0;i<n;i++)sum+=1+4*s.weights[i];
        int r=index(sum);
        for(int i=0;i<n;i++){r-=1+4*s.weights[i];if(r<0)return i;}
        return n-1;
    }
    i64 span(const Geometry&g){
        i64 loX=g.p[0].x,hiX=loX,loY=g.p[0].y,hiY=loY;
        for(int i=1;i<g.n;i++){loX=std::min(loX,g.p[i].x);hiX=std::max(hiX,g.p[i].x);
            loY=std::min(loY,g.p[i].y);hiY=std::max(hiY,g.p[i].y);}
        return std::max<i64>(1,std::max(hiX-loX,hiY-loY));
    }
    std::uint32_t move(Geometry&g,int chosen,Point target){
        if(std::abs(target.x)>1000000000000000LL||std::abs(target.y)>1000000000000000LL)return 0;
        if(!symmetry){g.p[chosen]=target;return 1u<<chosen;}
        if(chosen==18)return 0;
        int leader=chosen-chosen%3,offset=chosen%3;
        for(int j=0;j<(3-offset)%3;j++)target=rotate120(target);
        Point second=rotate120(target),third=rotate120(second);
        for(Point p:{target,second,third})
            if(std::abs(p.x)>1000000000000000LL||std::abs(p.y)>1000000000000000LL)return 0;
        g.p[leader]=target;g.p[leader+1]=second;g.p[leader+2]=third;
        return 7u<<leader;
    }
    std::uint32_t propose(Geometry&g,const Score&s){
        int chosen=choose(s,g.n);if(symmetry&&chosen==18)chosen=index(18);
        i64 extent=span(g);
        i64 radius=std::max<i64>(1,i64(extent*std::pow(10.0,min_exponent+(max_exponent-min_exponent)*unit())));
        int mode=index(10);
        std::uint32_t changed=0;
        if(mode<2&&!s.bad.empty()){
            const auto&polygon=s.bad[index(s.bad.size())];
            if(polygon.inside==0){
                std::vector<int> outsiders;
                for(int i=0;i<g.n;i++)if(!(polygon.vertices&(1u<<i))&&(!symmetry||i!=18))outsiders.push_back(i);
                if(!outsiders.empty())chosen=outsiders[index(outsiders.size())];
                i128 sx=0,sy=0;
                for(int i=0;i<g.n;i++)if(polygon.vertices&(1u<<i)){sx+=g.p[i].x;sy+=g.p[i].y;}
                Point center{i64(sx/6),i64(sy/6)};
                radius=std::max<i64>(1,extent/1000);
                changed|=move(g,chosen,{center.x+integer(radius),center.y+integer(radius)});
            }else{
                std::vector<int> interior;
                for(int i=0;i<g.n;i++)if((polygon.inside&(1u<<i))&&(!symmetry||i!=18))interior.push_back(i);
                if(!interior.empty())chosen=interior[index(interior.size())];
                radius=std::max<i64>(1,extent/20);
                changed|=move(g,chosen,{g.p[chosen].x+integer(radius),g.p[chosen].y+integer(radius)});
            }
        }else{
            changed|=move(g,chosen,{g.p[chosen].x+integer(radius),g.p[chosen].y+integer(radius)});
            if(mode==2){
                int second=choose(s,g.n);
                if(!symmetry||second/3!=chosen/3)
                    changed|=move(g,second,{g.p[second].x+integer(radius),g.p[second].y+integer(radius)});
            }
        }
        return changed;
    }
};
int main(int argc,char**argv){
    try{
        std::string input,output;double seconds=60,temperature=1.0,checkpoint_seconds=60;long double scale=1e10;
        std::uint64_t seed=42;bool check=false,symmetry=false;long long iterations=0,check_every=0;
        long long restart_every=100000,cycle_iterations=0;
        double cycle_seconds=30,min_exponent=-8,max_exponent=-0.2;
        for(int i=1;i<argc;i++){
            std::string a=argv[i];
            auto value=[&](){if(i+1>=argc)throw std::runtime_error("missing argument");return std::string(argv[++i]);};
            if(a=="--input")input=value();else if(a=="--output")output=value();
            else if(a=="--seconds")seconds=std::stod(value());else if(a=="--seed")seed=std::stoull(value());
            else if(a=="--scale")scale=std::stold(value());else if(a=="--temperature")temperature=std::stod(value());
            else if(a=="--iterations")iterations=std::stoll(value());
            else if(a=="--check-every")check_every=std::stoll(value());
            else if(a=="--checkpoint-seconds")checkpoint_seconds=std::stod(value());
            else if(a=="--restart-every")restart_every=std::stoll(value());
            else if(a=="--cycle-iterations")cycle_iterations=std::stoll(value());
            else if(a=="--cycle-seconds")cycle_seconds=std::stod(value());
            else if(a=="--min-exponent")min_exponent=std::stod(value());
            else if(a=="--max-exponent")max_exponent=std::stod(value());
            else if(a=="--hole-weight")hole_weight=std::stoi(value());
            else if(a=="--three-weight")three_weight=std::stoi(value());
            else if(a=="--check")check=true;else if(a=="--symmetry")symmetry=true;
            else throw std::runtime_error("unknown option "+a);
        }
        if(input.empty()||!std::isfinite(seconds)||seconds<=0||!std::isfinite(temperature)||temperature<=0||
           !std::isfinite(scale)||scale<=0||iterations<0||check_every<0||
           !std::isfinite(checkpoint_seconds)||checkpoint_seconds<=0||restart_every<0||cycle_iterations<0||
           !std::isfinite(cycle_seconds)||cycle_seconds<=0||!std::isfinite(min_exponent)||!std::isfinite(max_exponent)||
           min_exponent>max_exponent||min_exponent< -30||max_exponent>0||hole_weight<1||hole_weight>100||
           three_weight<1||three_weight>100)throw std::runtime_error("invalid arguments");
        Geometry current=read_points(input,scale,symmetry);Score score=current.score();
        if(check){
            std::cout<<"{\"n\":"<<current.n<<",\"holes0\":"<<score.holes<<",\"holes3\":"<<score.three
                <<",\"collinear_triples\":"<<score.collinear<<",\"score\":"<<score.raw()
                <<",\"objective\":"<<score.value()<<",\"valid\":"<<(score.raw()==0?"true":"false")<<"}\n";return 0;
        }
        if(output.empty())throw std::runtime_error("--output is required");
        if(score.collinear)throw std::runtime_error("initial rounded point set is not in general position");
        std::signal(SIGINT,stop_handler);std::signal(SIGTERM,stop_handler);
        Geometry best=current;Score best_score=score;Search search(seed,symmetry,temperature);
        search.min_exponent=min_exponent;search.max_exponent=max_exponent;
        write_points(output,best);write_points(output+".initial.pts",best);
        auto start=std::chrono::steady_clock::now();
        auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
        std::uint64_t proposals=0,accepted=0,restarts=0;double next_report=0,next_checkpoint=checkpoint_seconds;
        std::vector<Geometry>pool{best};
        while(best_score.raw()>0&&!interrupted.load(std::memory_order_relaxed)){
            double t=elapsed();if(t>=seconds||(iterations&&proposals>=std::uint64_t(iterations)))break;
            double phase=cycle_iterations?double(proposals%std::uint64_t(cycle_iterations))/cycle_iterations:
                                          std::fmod(t,cycle_seconds)/cycle_seconds;
            double temp=temperature*std::pow(0.01/temperature,phase);
            int allowance=int(-temp*std::log(std::max(1e-15,search.unit())));
            int cutoff=std::min(INF-1,score.value()+allowance);
            Geometry trial=current;
            std::uint32_t changed=search.propose(trial,score);
            ++proposals;if(!changed)continue;
            trial.update(changed);
            if(check_every&&proposals%std::uint64_t(check_every)==0){
                Geometry full=trial;full.build();
                if(full.signs!=trial.signs||full.left!=trial.left||full.collinear!=trial.collinear)
                    throw std::runtime_error("incremental predicate mismatch");
            }
            Score candidate=trial.score(cutoff);
            if(candidate.value()<=cutoff){
                current=trial;score=std::move(candidate);++accepted;
                if(score.raw()<best_score.raw()){
                    best=current;best_score=score;write_points(output,best);
                    std::cout<<"{\"event\":\"best\",\"seconds\":"<<t<<",\"score\":"<<score.raw()
                        <<",\"objective\":"<<score.value()
                        <<",\"holes0\":"<<score.holes<<",\"holes3\":"<<score.three
                        <<",\"proposals\":"<<proposals<<"}\n"<<std::flush;
                    pool.clear();pool.push_back(best);
                }else if(score.raw()==best_score.raw()&&search.index(20)==0){
                    if(pool.size()<16)pool.push_back(current);else pool[1+search.index(15)]=current;
                }
            }
            if(restart_every&&proposals%std::uint64_t(restart_every)==0){
                current=pool[search.index(pool.size())];score=current.score();++restarts;
            }
            if(t>=next_report){
                std::cout<<"{\"event\":\"progress\",\"seconds\":"<<t<<",\"best\":"<<best_score.raw()
                    <<",\"current\":"<<score.raw()<<",\"objective\":"<<score.value()<<",\"temperature\":"<<temp<<",\"proposals\":"<<proposals
                    <<",\"accepted\":"<<accepted<<"}\n"<<std::flush;
                next_report=t+5;
            }
            if(t>=next_checkpoint){
                write_points(output+".current.pts",current);
                for(std::size_t i=0;i<pool.size();i++)
                    write_points(output+".pool-"+std::to_string(i)+".pts",pool[i]);
                next_checkpoint=t+checkpoint_seconds;
            }
        }
        write_points(output,best);write_points(output+".current.pts",current);
        Score checked=best.score();
        if(checked.raw()!=best_score.raw())throw std::runtime_error("internal objective mismatch");
        std::cout<<"{\"event\":\"final\",\"seconds\":"<<elapsed()<<",\"n\":"<<best.n<<",\"seed\":"<<seed
            <<",\"symmetry\":"<<(symmetry?"true":"false")<<",\"score\":"<<checked.raw()<<",\"objective\":"<<checked.value()
            <<",\"holes0\":"<<checked.holes<<",\"holes3\":"<<checked.three<<",\"collinear_triples\":"<<checked.collinear
            <<",\"proposals\":"<<proposals<<",\"accepted\":"<<accepted<<",\"restarts\":"<<restarts<<"}\n";
        return 0;
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
