// Independent exhaustive verifier: exact integer predicates, all 6-subsets.
#include <boost/multiprecision/cpp_int.hpp>
#include <algorithm>
#include <array>
#include <chrono>
#include <fstream>
#include <iostream>
#include <numeric>
#include <string>
#include <vector>
using boost::multiprecision::cpp_int;
struct Point { cpp_int x,y; };
static cpp_int cross(const Point&a,const Point&b,const Point&c) {
    return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
}
static std::vector<int> hull(std::vector<int> ids,const std::vector<Point>&p) {
    std::sort(ids.begin(),ids.end(),[&](int a,int b){return p[a].x<p[b].x||(p[a].x==p[b].x&&p[a].y<p[b].y);});
    std::vector<int> out;
    for(int v:ids){while(out.size()>1&&cross(p[out[out.size()-2]],p[out.back()],p[v])<=0)out.pop_back();out.push_back(v);}
    size_t lower=out.size();
    for(int i=int(ids.size())-2;i>=0;i--){int v=ids[i];while(out.size()>lower&&cross(p[out[out.size()-2]],p[out.back()],p[v])<=0)out.pop_back();out.push_back(v);}
    out.pop_back();return out;
}
int main(int argc,char**argv){
    try {
        if(argc!=2)throw std::runtime_error("usage: verify_hexagons INPUT.pts");
        auto start=std::chrono::steady_clock::now();
        std::ifstream file(argv[1]);int n=0;
        if(!(file>>n)||n<6||n>40)throw std::runtime_error("expected 6..40 points");
        std::vector<Point>p(n);std::string sx,sy;
        auto parse=[](const std::string&s){
            if(s.empty())throw std::runtime_error("empty coordinate");
            size_t i=(s[0]=='-'||s[0]=='+');if(i==s.size())throw std::runtime_error("bad coordinate");
            cpp_int v=0;for(;i<s.size();i++){if(s[i]<'0'||s[i]>'9')throw std::runtime_error("expected decimal integer");v=v*10+(s[i]-'0');}
            return s[0]=='-'?-v:v;
        };
        for(auto&q:p){if(!(file>>sx>>sy))throw std::runtime_error("missing coordinate");q={parse(sx),parse(sy)};}
        if(file>>sx)throw std::runtime_error("extra input");
        int collinear=0,duplicates=0;
        for(int i=0;i<n;i++)for(int j=i+1;j<n;j++){
            duplicates+=p[i].x==p[j].x&&p[i].y==p[j].y;
            for(int k=j+1;k<n;k++)collinear+=cross(p[i],p[j],p[k])==0;
        }
        std::vector<unsigned long long>hist(n-5);unsigned long long subsets=0;
        std::array<int,6> ids={0,1,2,3,4,5};std::vector<int>first;
        do {
            subsets++;std::vector<int> polygon=hull(std::vector<int>(ids.begin(),ids.end()),p);
            if(polygon.size()==6){
                int count=0;
                for(int v=0;v<n;v++){
                    bool inside=true;for(int e=0;e<6;e++)if(cross(p[polygon[e]],p[polygon[(e+1)%6]],p[v])<=0){inside=false;break;}
                    count+=inside;
                }
                hist[count]++;if((count==0||count==3)&&first.empty())first=polygon;
            }
            int i=5;while(i>=0&&ids[i]==n-6+i)i--;if(i<0)break;ids[i]++;for(int j=i+1;j<6;j++)ids[j]=ids[j-1]+1;
        }while(true);
        bool valid=collinear==0&&duplicates==0&&hist[0]==0&&(hist.size()<4||hist[3]==0);
        std::cout<<"{\"n\":"<<n<<",\"valid\":"<<(valid?"true":"false")<<",\"collinear_triples\":"<<collinear
            <<",\"duplicate_pairs\":"<<duplicates<<",\"six_subsets_checked\":"<<subsets<<",\"interior_histogram\":[";
        for(size_t i=0;i<hist.size();i++)std::cout<<(i?",":"")<<hist[i];
        std::cout<<"],\"first_forbidden_hexagon\":[";for(size_t i=0;i<first.size();i++)std::cout<<(i?",":"")<<first[i]+1;
        std::cout<<"],\"seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";
        return valid?0:1;
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
