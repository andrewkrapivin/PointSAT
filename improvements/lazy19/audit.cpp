// Streaming abstract-order-type audit and sound geometric obstruction clauses.
// Input: complete colex signed orientation cube followed by 0, once per line.
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <vector>
using Mask=uint32_t;
int main(int argc,char**argv)try{
    int n=argc>1?std::stoi(argv[1]):19,limit=argc>2?std::stoi(argv[2]):128;
    if(n<6||n>30||limit<0)throw std::runtime_error("invalid n/cut limit");
    int vars=n*(n-1)*(n-2)/6;
    int literal[30][30][30]{};int id=0;
    for(int k=2;k<n;k++)for(int j=1;j<k;j++)for(int i=0;i<j;i++){
        ++id;literal[i][j][k]=literal[j][k][i]=literal[k][i][j]=id;
        literal[j][i][k]=literal[i][k][j]=literal[k][j][i]=-id;
    }
    int x;
    while(std::cin>>x){
        std::vector<int>truth(vars+1);int received=0;
        while(x){if(abs(x)>vars||truth[abs(x)])throw std::runtime_error("bad orientation cube");
            truth[abs(x)]=x>0?1:-1;received++;if(!(std::cin>>x))throw std::runtime_error("unterminated cube");}
        if(received!=vars)throw std::runtime_error("incomplete cube");
        Mask left[30][30]{};
        for(int i=0;i<n;i++)for(int j=0;j<n;j++)if(i!=j)
            for(int k=0;k<n;k++)if(k!=i&&k!=j){int v=literal[i][j][k];if(truth[abs(v)]*(v>0?1:-1)>0)left[i][j]|=Mask(1)<<k;}
        std::array<unsigned long long,25>hist{};std::vector<std::vector<int>>cuts;
        std::array<int,6>s={0,1,2,3,4,5};unsigned checked=0;
        for(;;){
            checked++;Mask subset=0;for(int i:s)subset|=Mask(1)<<i;
            std::vector<std::pair<int,int>>edges;Mask sources=0,targets=0;
            for(int i:s)for(int j:s)if(i!=j){Mask others=subset&~((Mask(1)<<i)|(Mask(1)<<j));
                if((others&left[i][j])==others){edges.emplace_back(i,j);sources|=Mask(1)<<i;targets|=Mask(1)<<j;}}
            if(edges.size()==6&&sources==subset&&targets==subset){
                Mask inside=(Mask(1)<<n)-1;for(auto [i,j]:edges)inside&=left[i][j];
                int count=__builtin_popcount(inside);hist[count]++;
                if((count==0||count==3)&&int(cuts.size())<limit){
                    // These signs force the same hull edges and inside/outside
                    // classification. At least one must change in any solution.
                    std::set<int>conjunction;
                    for(auto [i,j]:edges)for(int k:s)if(k!=i&&k!=j)conjunction.insert(literal[i][j][k]);
                    for(int q=0;q<n;q++)if(!(subset&(Mask(1)<<q))){
                        if(inside&(Mask(1)<<q)){for(auto [i,j]:edges)conjunction.insert(literal[i][j][q]);}
                        else{for(auto [i,j]:edges)if(!(left[i][j]&(Mask(1)<<q))){conjunction.insert(-literal[i][j][q]);break;}}
                    }
                    std::vector<int>clause;
                    for(int v:conjunction){if(truth[abs(v)]!=(v>0?1:-1))throw std::runtime_error("unsatisfied obstruction premise");clause.push_back(-v);}
                    cuts.push_back(std::move(clause));
                }
            }
            int j=5;while(j>=0&&s[j]==n-6+j)--j;if(j<0)break;
            ++s[j];for(int k=j+1;k<6;k++)s[k]=s[k-1]+1;
        }
        std::cout<<"{\"six_subsets\":"<<checked<<",\"histogram\":[";
        for(int i=0;i<=n-6;i++)std::cout<<(i?",":"")<<hist[i];
        std::cout<<"],\"cuts\":[";
        for(size_t i=0;i<cuts.size();i++){std::cout<<(i?",[":"[");for(size_t j=0;j<cuts[i].size();j++)std::cout<<(j?",":"")<<cuts[i][j];std::cout<<"]";}
        std::cout<<"]}"<<std::endl;
    }
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
