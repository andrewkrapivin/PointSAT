// Experimental continuous realization repair: analytic hinge-loss gradients,
// L-BFGS, affine gauge fixing and randomized restarts. Not a proof procedure.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using Vec=std::vector<double>;
struct Constraint{int a,b,c;double sign;};
static volatile std::sig_atomic_t stop_requested=0;
static void stop(int){stop_requested=1;}
static double dot(const Vec&a,const Vec&b){return std::inner_product(a.begin(),a.end(),b.begin(),0.0);}
static double determinant(const Vec&x,int a,int b,int c){return (x[2*b]-x[2*a])*(x[2*c+1]-x[2*a+1])-(x[2*b+1]-x[2*a+1])*(x[2*c]-x[2*a]);}
static double loss(const Vec&x,const std::vector<Constraint>&cs,double margin,Vec&g,int&bad){
    std::fill(g.begin(),g.end(),0);double f=0;bad=0;
    for(auto [a,b,c,s]:cs){
        double d=s*determinant(x,a,b,c);bad+=d<=0;double h=margin-d;if(h<=0)continue;
        f+=h*h;double v=-2*h*s;
        g[2*a]+=v*(x[2*b+1]-x[2*c+1]);g[2*a+1]+=v*(x[2*c]-x[2*b]);
        g[2*b]+=v*(x[2*c+1]-x[2*a+1]);g[2*b+1]+=v*(x[2*a]-x[2*c]);
        g[2*c]+=v*(x[2*a+1]-x[2*b+1]);g[2*c+1]+=v*(x[2*b]-x[2*a]);
    }
    return f;
}
static void self_test(){
    std::mt19937_64 rng(321);std::normal_distribution<double>normal;int checks=0;
    for(int test=0;test<100;test++){
        Vec x(18),g(18),tmp(18);for(double&v:x)v=normal(rng);
        std::vector<Constraint>cs;for(int a=0;a<9;a++)for(int b=a+1;b<9;b++)for(int c=b+1;c<9;c++)cs.push_back({a,b,c,normal(rng)>0?1.0:-1.0});
        int bad;loss(x,cs,.01,g,bad);
        for(size_t i=0;i<x.size();i++){
            double old=x[i],h=1e-5;x[i]=old+h;double a=loss(x,cs,.01,tmp,bad);x[i]=old-h;double b=loss(x,cs,.01,tmp,bad);x[i]=old;
            double numeric=(a-b)/(2*h);if(std::abs(numeric-g[i])>1e-6*(1+std::abs(g[i])))throw std::runtime_error("gradient mismatch");checks++;
        }
    }
    std::cout<<"{\"gradient_checks\":"<<checks<<",\"passed\":true}\n";
}
int main(int argc,char**argv)try{
    if(argc==2&&std::string(argv[1])=="--self-test"){self_test();return 0;}
    if(argc<6)throw std::runtime_error("usage: gradient constraints.or warm.real output.real seconds seed [margin]");
    double seconds=std::stod(argv[4]),margin=argc>6?std::stod(argv[6]):1e-6;
    if(!(seconds>0&&std::isfinite(seconds)&&margin>0&&std::isfinite(margin)))throw std::runtime_error("invalid budget/margin");
    std::mt19937_64 rng(std::stoull(argv[5]));std::normal_distribution<double>normal;
    std::vector<Constraint>cs;std::ifstream orient(argv[1]);if(!orient)throw std::runtime_error("cannot open orientations");
    std::string line;int n=0;
    while(std::getline(orient,line)){
        if(line.empty())continue;
        char s,extra;int a,b,c;
        if(std::sscanf(line.c_str()," %c_(%d, %d, %d) %c",&s,&a,&b,&c,&extra)!=4||(s!='A'&&s!='B')||a<1||b<1||c<1||a==b||a==c||b==c)throw std::runtime_error("bad orientation row");
        n=std::max({n,a,b,c});cs.push_back({a-1,b-1,c-1,s=='A'?1.0:-1.0});
    }
    if(n<3||n>100)throw std::runtime_error("unsupported point count");
    Vec initial(2*n);std::vector<bool>seen(n);std::ifstream warm(argv[2]);int idx;double xx,yy;
    while(warm>>idx>>xx>>yy){if(idx<1||idx>n||seen[idx-1]||!std::isfinite(xx)||!std::isfinite(yy))throw std::runtime_error("bad warm point");seen[idx-1]=true;initial[2*(idx-1)]=xx;initial[2*(idx-1)+1]=yy;}
    if(!warm.eof()||std::count(seen.begin(),seen.end(),true)!=n)throw std::runtime_error("incomplete warm geometry");
    double cx=0,cy=0;for(int i=0;i<n;i++){cx+=initial[2*i]/n;cy+=initial[2*i+1]/n;}
    double scale=0;for(int i=0;i<n;i++){initial[2*i]-=cx;initial[2*i+1]-=cy;scale=std::max(scale,std::hypot(initial[2*i],initial[2*i+1]));}
    if(!(scale>0))throw std::runtime_error("collapsed geometry");
    for(double&v:initial)v/=scale;
    std::array<int,3>anchor{};double area=0;
    for(int a=0;a<n;a++)for(int b=a+1;b<n;b++)for(int c=b+1;c<n;c++){double d=std::abs(determinant(initial,a,b,c));if(d>area){area=d;anchor={a,b,c};}}
    if(area<1e-12)throw std::runtime_error("collinear seed");
    auto project=[&](Vec&v){for(int i:anchor)v[2*i]=v[2*i+1]=0;};
    std::signal(SIGINT,stop);std::signal(SIGTERM,stop);
    const auto start=std::chrono::steady_clock::now();
    auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
    Vec best=initial,g(initial.size());int bestbad;double bestloss=loss(best,cs,margin,g,bestbad);long long iterations=0,restarts=0;
    auto save=[&](){std::ofstream out(argv[3]);if(!out)throw std::runtime_error("cannot write coordinates");out<<std::setprecision(17);for(int i=0;i<n;i++)out<<i+1<<' '<<best[2*i]<<' '<<best[2*i+1]<<'\n';};
    save();
    bool solved=false;
    while(!stop_requested&&elapsed()<seconds&&!solved){
        Vec x=restarts%5==4?initial:best;
        if(restarts){double radius=std::pow(10.,-4+int(restarts%5));Vec delta(x.size());for(double&v:delta)v=radius*normal(rng);project(delta);for(size_t i=0;i<x.size();i++)x[i]+=delta[i];}
        int bad;double f=loss(x,cs,margin,g,bad);project(g);
        std::vector<Vec>ss,ys;std::vector<double>rhos;
        for(int it=0;it<3000&&!stop_requested&&elapsed()<seconds;it++,iterations++){
            if(bad<bestbad||(bad==bestbad&&f<bestloss)){
                bool improved=bad<bestbad;best=x;bestbad=bad;bestloss=f;
                if(improved){save();std::cout<<"{\"event\":\"best\",\"bad\":"<<bestbad<<",\"loss\":"<<bestloss<<",\"elapsed\":"<<elapsed()<<",\"iterations\":"<<iterations<<"}"<<std::endl;}
            }
            if(!bad&&f<margin*margin*.01){solved=true;break;}
            Vec q=g;std::vector<double>alpha(ss.size());
            for(int j=int(ss.size())-1;j>=0;j--){alpha[j]=rhos[j]*dot(ss[j],q);for(size_t k=0;k<q.size();k++)q[k]-=alpha[j]*ys[j][k];}
            double gamma=ss.empty()?1:dot(ss.back(),ys.back())/dot(ys.back(),ys.back());for(double&v:q)v*=gamma;
            for(size_t j=0;j<ss.size();j++){double beta=rhos[j]*dot(ys[j],q);for(size_t k=0;k<q.size();k++)q[k]+=ss[j][k]*(alpha[j]-beta);}
            for(double&v:q)v=-v;
            double descent=dot(q,g);
            if(!(descent<0&&std::isfinite(descent))){ss.clear();ys.clear();rhos.clear();q=g;for(double&v:q)v=-v;descent=-dot(g,g);}
            if(descent>=-1e-35)break;
            Vec next=x,ng(x.size());double step=1,nf=0;int nb=0;bool accepted=false;
            for(int ls=0;ls<40;ls++,step*=.5){for(size_t k=0;k<x.size();k++)next[k]=x[k]+step*q[k];nf=loss(next,cs,margin,ng,nb);if(std::isfinite(nf)&&nf<=f+1e-4*step*descent){accepted=true;break;}}
            if(!accepted)break;
            project(ng);Vec s(x.size()),y(x.size());for(size_t k=0;k<x.size();k++){s[k]=next[k]-x[k];y[k]=ng[k]-g[k];}
            double sy=dot(s,y);if(sy>1e-25){if(ss.size()==8){ss.erase(ss.begin());ys.erase(ys.begin());rhos.erase(rhos.begin());}ss.push_back(s);ys.push_back(y);rhos.push_back(1/sy);}
            x=std::move(next);g=std::move(ng);f=nf;bad=nb;
        }
        restarts++;
    }
    save();std::cout<<"{\"event\":\"finished\",\"bad\":"<<bestbad<<",\"loss\":"<<bestloss<<",\"margin\":"<<margin<<",\"solved_approximate\":"<<(solved?"true":"false")<<",\"elapsed\":"<<elapsed()<<",\"iterations\":"<<iterations<<",\"restarts\":"<<restarts<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
