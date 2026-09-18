// Two-point geometric repair: perturb one old point across an arrangement
// boundary, then exhaust all possible locations of another point exactly.
#define ARRANGEMENT_LIBRARY
#include "arrangement.cpp"

int main(int argc,char** argv)try {
    std::string input,output="coupled-solution23.pts";double seconds=180;uint64_t seed=771;
    for(int i=1;i<argc;++i){std::string a=argv[i];if(i+1>=argc)throw std::runtime_error("missing value");std::string v=argv[++i];if(a=="--input")input=v;else if(a=="--output")output=v;else if(a=="--seconds")seconds=std::stod(v);else if(a=="--seed")seed=std::stoull(v);else throw std::runtime_error("unknown option "+a);}
    if(seconds<=0||!std::isfinite(seconds))throw std::runtime_error("invalid duration");
    Points p=read_points(input);if(p.size()!=23||!valid(p,7,0))throw std::runtime_error("expected23 GP points without7gons");
    auto original=std::make_unique<Oracle>(p,7,6);auto holes=existing_empty_holes(p,*original,6);
    if(holes.empty())throw std::runtime_error("input is already a solution; this is a repair experiment");
    std::mt19937_64 random(seed);std::uniform_real_distribution<double> unit(0,1);
    auto start=std::chrono::steady_clock::now();auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
    uint64_t proposals=0,scans=0,exhausted=0,walks=0;bool found=false;double nextlog=0;
    auto log=[&](const char* event){std::cout << "{\"event\":\"" << event << "\",\"method\":\"coupled_exact_repair\",\"seed\":" << seed << ",\"elapsed\":" << elapsed() << ",\"proposals\":" << proposals << ",\"scans\":" << scans << ",\"exhausted_scans\":" << exhausted << ",\"accepted_walks\":" << walks << ",\"current_holes\":" << holes.size() << ",\"found\":" << (found?"true":"false") << "}" << std::endl;};
    log("start");
    while(elapsed()<seconds&&!found) {
        ++proposals;const auto& witness=holes[random()%holes.size()];int removed=witness[random()%witness.size()];
        int moved=random()%23;while(moved==removed)moved=random()%23;
        Points base;int j=-1;for(int i=0;i<23;++i)if(i!=removed){if(i==moved)j=base.size();base.push_back(p[i]);}
        int64_t minx=p[0].x,maxx=minx,miny=p[0].y,maxy=miny;for(auto q:p){minx=std::min(minx,q.x);maxx=std::max(maxx,q.x);miny=std::min(miny,q.y);maxy=std::max(maxy,q.y);}
        double span=std::max(maxx-minx,maxy-miny),angle=unit(random)*6.283185307179586,dx=std::cos(angle),dy=std::sin(angle),distance=span;
        if(random()%5) {
            for(int a=0;a<22;++a)if(a!=j)for(int b=a+1;b<22;++b)if(b!=j) {
                double value=double((Wide(base[a].x)-base[j].x)*(Wide(base[b].y)-base[j].y)-(Wide(base[a].y)-base[j].y)*(Wide(base[b].x)-base[j].x));
                double derivative=dx*double(base[a].y-base[b].y)+dy*double(base[b].x-base[a].x);
                if(derivative){double t=-value/derivative;if(t>0)distance=std::min(distance,t);}
            }
            distance=distance*(1.+std::pow(10.,-4.+3.*unit(random)))+2.;
        }else distance=span*std::pow(10.,-5.+3.5*unit(random));
        base[j].x+=std::llround(dx*distance);base[j].y+=std::llround(dy*distance);
        if(base[j].x < -1000000000LL||base[j].x>1000000000LL||base[j].y < -1000000000LL||base[j].y>1000000000LL)continue;
        if(!valid(base,7,0))continue;
        double remaining=seconds-elapsed();if(remaining<=0)break;
        auto result=arrangement_search(base,7,6,std::min(1.,remaining),"coupled_perturbed_direct23",output,true);
        ++scans;if(result.complete&&!result.found)++exhausted;
        if(result.found){found=true;break;}
        // A small walk among one/two-hole near-solutions diversifies the fixed
        // coordinates used by the next exact two-point repair attempt.
        Points trial=p;trial[moved]=base[j];
        if(valid(trial,7,0)) {
            auto oracle=std::make_unique<Oracle>(trial,7,6);auto newholes=existing_empty_holes(trial,*oracle,6);
            if(newholes.empty()){
                std::ofstream f(output);if(!f)throw std::runtime_error("cannot write solution");f << trial.size() << '\n';for(auto q:trial)f << q.x << ' ' << q.y << '\n';found=true;
            }else if(newholes.size()<=2&&(newholes.size()<=holes.size()||random()%10==0)){p.swap(trial);holes=std::move(newholes);++walks;}
        }
        if(elapsed()>=nextlog){log("progress");nextlog=elapsed()+10;}
    }
    log("done");return 0;
}catch(const std::exception& e){std::cerr << "coupled: " << e.what() << '\n';return 2;}
