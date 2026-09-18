#define main triangle_command_main
#include "triangle.cpp"
#undef main
int main(){
    mt19937_64 rng(765431);Points p=random_points(23,1000000,rng);Geometry g;g.build(p);
    for(int iteration=0;iteration<20000;iteration++){
        auto trial=p;int v=rng()%p.size();trial[v]={int64_t(rng()%1000000),int64_t(rng()%1000000)};
        Geometry fast=g,reference;bool a=update(fast,trial,v),b=reference.build(trial);
        if(a!=b || (a&&!fast.same(reference))){cerr<<"incremental mismatch at "<<iteration<<'\n';return 1;}
        if(a){g=fast;p.swap(trial);}
    }
    cout<<"{\"incremental_orientation_tests\":20000,\"passed\":true}\n";
}
