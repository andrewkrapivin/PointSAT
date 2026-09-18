// Integer-grid compaction portfolio. Reuses PointSAT's independently tested
// exact fan/cap kernel, but all proposal arithmetic is checked before acceptance.
#define POINTSAT_GEOMETRY_ONLY
#include "../direct/search.cpp"
#include <atomic>
#include <csignal>
#include <ctime>
#include <iomanip>
#include <set>
#include <tuple>

using Wide=__int128_t;
static volatile sig_atomic_t stopping=0;
static void stop_handler(int){stopping=1;}
constexpr int64_t LIMIT=1000000000000LL;
static Wide floor_div(Wide a,Wide b){if(b<0){a=-a;b=-b;}Wide q=a/b,r=a%b;return q-(r<0);}
static Wide ceil_div(Wide a,Wide b){return -floor_div(-a,b);}
static string decimal(Wide x){if(!x)return "0";string s;while(x){s+=char('0'+x%10);x/=10;}reverse(s.begin(),s.end());return s;}
struct Box {int64_t w,h;Wide area()const{return Wide(w)*h;}};
static Box normalize(Points&p,bool reduce=true){
    int64_t x=p[0].x,y=p[0].y,X=x,Y=y;
    for(auto q:p){x=min(x,q.x);y=min(y,q.y);X=max(X,q.x);Y=max(Y,q.y);}
    int64_t gx=0,gy=0;for(auto&q:p){q.x-=x;q.y-=y;gx=gcd(gx,q.x);gy=gcd(gy,q.y);}
    if(!reduce)gx=gy=1;
    gx=max<int64_t>(1,gx);gy=max<int64_t>(1,gy);
    for(auto&q:p){q.x/=gx;q.y/=gy;}return {(X-x)/gx,(Y-y)/gy};
}
static vector<int> layers(Points p){
    vector<int> out;
    while(!p.empty()){
        if(p.size()<3){out.push_back(p.size());break;}
        vector<int> ids(p.size()),h;iota(ids.begin(),ids.end(),0);
        sort(ids.begin(),ids.end(),[&](int a,int b){return lessxy(p[a],p[b]);});
        for(int i:ids){while(h.size()>1&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}
        size_t lower=h.size();for(int z=int(ids.size())-2;z>=0;--z){int i=ids[z];while(h.size()>lower&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}
        h.pop_back();out.push_back(h.size());Points next;
        for(int i=0;i<int(p.size());i++)if(find(h.begin(),h.end(),i)==h.end())next.push_back(p[i]);
        p.swap(next);
    }return out;
}
static string json_array(const vector<int>& a){string s="[";for(size_t i=0;i<a.size();i++){if(i)s+=',';s+=to_string(a[i]);}return s+"]";}
static Points load_input(const string&path){
    ifstream f(path);int n;if(!(f>>n)||n<3||n>40)throw runtime_error("expected point count in [3,40]");
    Points p(n);for(auto&q:p)if(!(f>>q.x>>q.y)||q.x < -LIMIT||q.x>LIMIT||q.y < -LIMIT||q.y>LIMIT)throw runtime_error("invalid integer coordinates; absolute limit is 10^12");
    string extra;if(f>>extra)throw runtime_error("unexpected trailing input");return p;
}
static void atomic_save(const string&path,const Points&p){
    string temp=path+".tmp";{ofstream f(temp);if(!f)throw runtime_error("cannot write output");f<<p.size()<<'\n';for(auto q:p)f<<q.x<<' '<<q.y<<'\n';f.close();if(!f)throw runtime_error("failed writing output");}
    if(rename(temp.c_str(),path.c_str()))throw runtime_error("cannot atomically replace output");
}
struct Optimizer {
    Points p,best,original;Geometry geom,original_geometry;
    Box box{},bestbox{},initialbox{};vector<int> original_layers;
    int gon=7,hole=6,cap=0;bool preserve=false,preserve_layers=false;
    mt19937_64 rng;double seconds=60;uint64_t iterations=~uint64_t(0),seed=1;
    uint64_t proposals=0,accepted=0,improvements=0,property_checks=0,type_changes=0,transforms=0,repairs=0;
    Clock::time_point start=Clock::now();clock_t cpu_start=clock();string output,family="mixed23";
    double last_save=-1,last_log=-1;bool dirty=false;
    double time()const{return elapsed(start);}
    double unit(){return (rng()>>11)*0x1.0p-53;}
    int sign(int i,int j,int k,const Geometry&g)const{return ((g.left[i][j]>>k)&1)?1:-1;}
    bool valid(Points&q,Geometry&g){
        if(!g.build(q))return false;
        if(preserve&&!g.same(original_geometry))return false;
        if(cap||!g.same(geom)){property_checks++;if(g.count(q,gon,hole,nullptr,0,0).total()||g.caps(q,cap))return false;}
        if(preserve_layers&&layers(q)!=original_layers)return false;
        return true;
    }
    void record(){
        if(best.empty()||box.area()<bestbox.area()||(box.area()==bestbox.area()&&max(box.w,box.h)<max(bestbox.w,bestbox.h))){best=p;bestbox=box;improvements++;dirty=true;}
    }
    void checkpoint(bool force=false){if(dirty&&(force||time()-last_save>=1)){atomic_save(output,best);dirty=false;last_save=time();}}
    bool take(Points q,bool expansion=false){
        for(auto a:q)if(a.x < -LIMIT||a.x>LIMIT||a.y < -LIMIT||a.y>LIMIT)return false;
        auto b=normalize(q);
        if(!b.w||!b.h||(!expansion&&b.area()>box.area()))return false;
        if((long double)b.area()>(long double)bestbox.area()*1.3L)return false;
        Geometry g;if(!valid(q,g))return false;
        if(!g.same(geom))type_changes++;
        p.swap(q);box=b;geom=g;accepted++;record();return true;
    }
    bool line_move(){
        int n=p.size(),v=rng()%n,dx=0,dy=0;
        if(rng()%3) {if(rng()%2)dx=1;else dy=1;}
        else {do{dx=int(rng()%7)-3;dy=int(rng()%7)-3;}while(!dx&&!dy);}
        // Coordinate extremes get extra attention: only their motion shrinks a box.
        if(rng()%2)for(int z=0;z<n;z++){int j=(v+z)%n;if(p[j].x==0||p[j].x==box.w||p[j].y==0||p[j].y==box.h){v=j;break;}}
        Wide lo=-Wide(2)*LIMIT,hi=Wide(2)*LIMIT;
        auto bound=[&](Wide a,Wide b){if(a>0)lo=max(lo,ceil_div(b,a));else if(a<0)hi=min(hi,floor_div(b,a));else if(b>0)throw runtime_error("infeasible current invariant");};
        bound(dx,-p[v].x);bound(-dx,p[v].x-box.w);bound(dy,-p[v].y);bound(-dy,p[v].y-box.h);
        for(int j=0;j<n;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v){
            int s=sign(v,j,k,geom);Wide a=(Wide(dx)*(p[j].y-p[k].y)+Wide(dy)*(p[k].x-p[j].x))*s;
            Wide b=cross(p[v],p[j],p[k])*s;bound(a,1-b);
        }
        if(lo>0||hi<0)throw runtime_error("feasible interval lost incumbent");
        if(lo==hi)return false;
        int64_t l=int64_t(lo),h=int64_t(hi),t;
        if(rng()%2){long double target=((box.w*.5L-p[v].x)*dx+(box.h*.5L-p[v].y)*dy)/(dx*dx+dy*dy);t=clamp<int64_t>(llround(target),l,h);}
        else t=l+int64_t(rng()%uint64_t(h-l+1));
        if(!t)return false;
        Points q=p;q[v].x+=t*dx;q[v].y+=t*dy;
        // Signs are unchanged. Cap restrictions additionally depend on x order.
        if(cap)return take(q);
        p.swap(q);box=normalize(p);accepted++;record();return true;
    }
    int orientation_errors(const Points&q,const Geometry&target,vector<int>*weights=nullptr)const{
        int count=0,n=q.size();if(weights)weights->assign(n,0);
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++)if(cross(q[i],q[j],q[k])*sign(i,j,k,target)<=0){count++;if(weights){(*weights)[i]++;(*weights)[j]++;(*weights)[k]++;}}
        return count;
    }
    bool repair(Points&q,const Geometry&target,int steps=100){
        vector<int> weights;int score=orientation_errors(q,target,&weights);if(!score)return true;
        if(score>100)return false;
        repairs++;Points incumbent=q;int best_score=score,n=q.size();
        Box b=normalize(q,false);
        for(int it=0;it<steps&&score&&time()<seconds&&!stopping;it++){
            int total=accumulate(weights.begin(),weights.end(),0),r=rng()%total,v=0;while(r>=weights[v])r-=weights[v++];
            bool axis=rng()%2;int64_t old=axis?q[v].y:q[v].x,upper=axis?b.h:b.w;
            vector<int64_t> candidates={0,upper,old};
            // Every incident inequality changes truth only next to one exact
            // rational threshold. Test neighboring lattice coordinates.
            for(int j=0;j<n;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v){
                Wide a=axis?Wide(q[k].x)-q[j].x:Wide(q[j].y)-q[k].y;
                if(!a)continue;
                Wide d=cross(q[v],q[j],q[k]);Wide root=floor_div(Wide(old)*a-d,a);
                for(int z=-1;z<=2;z++)if(root+z>=0&&root+z<=upper)candidates.push_back(int64_t(root+z));
            }
            sort(candidates.begin(),candidates.end());candidates.erase(unique(candidates.begin(),candidates.end()),candidates.end());
            int best_incident=weights[v];int64_t chosen=old;uint64_t ties=1;
            for(int64_t nv:candidates){Point t=q[v];if(axis)t.y=nv;else t.x=nv;int bad=0;
                for(int j=0;j<n&&bad<=best_incident;j++)if(j!=v)for(int k=j+1;k<n;k++)if(k!=v)bad+=cross(t,q[j],q[k])*sign(v,j,k,target)<=0;
                if(bad<best_incident){best_incident=bad;chosen=nv;ties=1;}else if(bad==best_incident&&rng()%++ties==0)chosen=nv;
            }
            if(axis)q[v].y=chosen;else q[v].x=chosen;
            score=orientation_errors(q,target,&weights);
            if(score<best_score){best_score=score;incumbent=q;}
            if(it%25==24&&score){q=incumbent;int u=rng()%n;int64_t radius=max<int64_t>(1,max(b.w,b.h)/100);q[u].x=clamp<int64_t>(q[u].x+int64_t(rng()%(2*radius+1))-radius,0,b.w);q[u].y=clamp<int64_t>(q[u].y+int64_t(rng()%(2*radius+1))-radius,0,b.h);score=orientation_errors(q,target,&weights);}
        }
        if(!score)return true;
        q=incumbent;return false;
    }
    void transform(){
        transforms++;int mode=rng()%5;long double angle=mode==0?unit()*6.283185307179586L:0;
        long double co=cos(angle),si=sin(angle),u=0,v=0,shear=0;
        if(mode==1||mode==2){u=(unit()-.5)*1.4;v=(unit()-.5)*1.4;}
        if(mode==3)shear=(unit()-.5)*1.5;
        vector<pair<long double,long double>> a;long double xmin=1e100L,xmax=-xmin,ymin=xmin,ymax=-xmin;
        for(auto q:p){long double x=(long double)q.x/max<int64_t>(1,box.w)-.5L,y=(long double)q.y/max<int64_t>(1,box.h)-.5L;
            long double den=1+u*x+v*y,X=(co*x-si*y+shear*y)/den,Y=(si*x+co*y)/den;a.emplace_back(X,Y);xmin=min(xmin,X);xmax=max(xmax,X);ymin=min(ymin,Y);ymax=max(ymax,Y);}
        long double scale=transforms<30?.5L+.49L*unit():.94L+.10L*unit();
        int64_t w=max<int64_t>(3,llround(box.w*scale)),h=max<int64_t>(3,llround(box.h*scale));
        if(mode==4){if(rng()%2)w=max<int64_t>(3,box.w-1);else h=max<int64_t>(3,box.h-1);}
        Points q;for(auto [x,y]:a)q.push_back({llround((x-xmin)/(xmax-xmin)*w),llround((y-ymin)/(ymax-ymin)*h)});
        bool expand=scale>1&&rng()%4==0;
        if(take(q,expand))return;
        if(repair(q,geom,40))take(q,expand);
        else if(!preserve)take(q,expand); // A different valid type may suffice.
    }
    void mutate(){
        Points q=p;int n=q.size(),i=rng()%n;int64_t radius=max<int64_t>(1,llround(max(box.w,box.h)*pow(10.,-1.-3.*unit())));
        q[i].x=clamp<int64_t>(q[i].x+int64_t(rng()%(2*radius+1))-radius,0,box.w);
        q[i].y=clamp<int64_t>(q[i].y+int64_t(rng()%(2*radius+1))-radius,0,box.h);take(q);
    }
    void log(const char*event){
        int changed=orientation_errors(best,original_geometry);
        cout<<setprecision(10)<<"{\"event\":\""<<event<<"\",\"family\":\""<<family<<"\",\"seed\":"<<seed<<",\"seconds\":"<<time()<<",\"cpu_seconds\":"<<double(clock()-cpu_start)/CLOCKS_PER_SEC
            <<",\"proposals\":"<<proposals<<",\"accepted\":"<<accepted<<",\"improvements\":"<<improvements<<",\"property_checks\":"<<property_checks<<",\"type_changes\":"<<type_changes<<",\"transforms\":"<<transforms<<",\"repairs\":"<<repairs
            <<",\"width\":"<<bestbox.w<<",\"height\":"<<bestbox.h<<",\"area\":"<<decimal(bestbox.area())<<",\"input_width\":"<<initialbox.w<<",\"input_height\":"<<initialbox.h<<",\"orientation_changes\":"<<changed
            <<",\"preserve_order_type\":"<<(preserve?"true":"false")<<",\"preserve_layers\":"<<(preserve_layers?"true":"false")<<",\"input_layers\":"<<json_array(original_layers)<<",\"layers\":"<<json_array(layers(best))<<",\"valid\":true}"<<endl;
    }
    void run(){
        original=p;box=normalize(p);original_geometry.build(p);geom=original_geometry;original_layers=layers(p);initialbox=box;best=p;bestbox=box;
        if(!geom.build(p)||geom.count(p,gon,hole).total()||geom.caps(p,cap))throw runtime_error("input violates general position or requested family");
        signal(SIGINT,stop_handler);signal(SIGTERM,stop_handler);rng.seed(seed);start=Clock::now();cpu_start=clock();dirty=true;checkpoint(true);log("start");
        while(time()<seconds&&proposals<iterations&&!stopping){
            proposals++;
            if(proposals%128==0)transform();else if(!preserve&&proposals%8==0)mutate();else line_move();
            if(proposals%10000==0&&box.area()>bestbox.area()){p=best;box=bestbox;geom.build(p);}
            checkpoint();if(time()-last_log>=10){log("progress");last_log=time();}
        }
        Geometry final_geometry;if(!final_geometry.build(best)||final_geometry.count(best,gon,hole).total()||final_geometry.caps(best,cap))throw runtime_error("final exact validation failed");
        if(preserve&&!final_geometry.same(original_geometry))throw runtime_error("final orientation preservation failed");
        if(preserve_layers&&layers(best)!=original_layers)throw runtime_error("final layer preservation failed");
        dirty=true;checkpoint(true);log("final");
    }
};
int main(int argc,char**argv)try{
    Optimizer o;string input;bool check=false;
    for(int i=1;i<argc;i++){string arg=argv[i];auto val=[&](){if(++i>=argc)throw runtime_error("missing value for "+arg);return string(argv[i]);};
        if(arg=="--input")input=val();else if(arg=="--output")o.output=val();else if(arg=="--seconds")o.seconds=stod(val());else if(arg=="--seed")o.seed=stoull(val());else if(arg=="--iterations")o.iterations=stoull(val());
        else if(arg=="--family")o.family=val();else if(arg=="--preserve-order-type")o.preserve=true;else if(arg=="--preserve-layers")o.preserve_layers=true;else if(arg=="--check")check=true;
        else if(arg=="--help"){cout<<"Usage: compact --input FILE.pts --output FILE.pts [--seconds 60] [--seed 1] [--family mixed23|holes29|gons32|caps26] [--preserve-order-type] [--preserve-layers] [--iterations N] [--check]\n";return 0;}else throw runtime_error("unknown option "+arg);
    }
    if(input.empty()||(!check&&o.output.empty())||!isfinite(o.seconds)||o.seconds<0)throw runtime_error("input/output and finite nonnegative seconds required");
    if(o.family=="holes29"){o.gon=0;o.hole=6;}else if(o.family=="gons32"){o.gon=7;o.hole=0;}else if(o.family=="caps26"){o.gon=7;o.hole=0;o.cap=5;}else if(o.family!="mixed23")throw runtime_error("unknown family");
    o.p=load_input(input);if(check){Geometry g;bool gp=g.build(o.p);Score s;if(gp){s=g.count(o.p,o.gon,o.hole);s.cap=g.caps(o.p,o.cap);}cout<<"{\"general_position\":"<<(gp?"true":"false")<<",\"gons\":"<<s.gon<<",\"holes\":"<<s.hole<<",\"caps\":"<<s.cap<<",\"valid\":"<<(gp&&!s.total()?"true":"false")<<",\"layers\":"<<json_array(layers(o.p))<<"}\n";return gp&&!s.total()?0:1;}
    o.run();return 0;
}catch(const exception&e){cerr<<e.what()<<'\n';return 2;}
