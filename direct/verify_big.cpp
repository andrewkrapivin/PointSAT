// Independent exhaustive validator for arbitrary-size INTEGER coordinates.
// Used only when a rational arrangement-cell witness needs a large common
// denominator. No search algorithm or geometric oracle is shared.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
#include <boost/multiprecision/cpp_int.hpp>
using Big=boost::multiprecision::cpp_int;
struct Point {Big x,y;};
static Big cross(const Point&a,const Point&b,const Point&c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
static Big decimal(const std::string&s){if(s.empty()||s.size()>10000)throw std::runtime_error("invalid coordinate length");std::size_t i=s[0]=='-'||s[0]=='+';if(i==s.size())throw std::runtime_error("invalid coordinate");Big x=0;for(;i<s.size();i++){if(s[i]<'0'||s[i]>'9')throw std::runtime_error("integer coordinates required");x*=10;x+=s[i]-'0';}return s[0]=='-'?-x:x;}
int main(int argc,char**argv)try{
    std::string input;int gon=7,hole=6;
    for(int i=1;i<argc;i++){std::string a=argv[i];if(i+1==argc)throw std::runtime_error("missing value");std::string v=argv[++i];if(a=="--input")input=v;else if(a=="--gon")gon=std::stoi(v);else if(a=="--hole")hole=std::stoi(v);else throw std::runtime_error("unknown option");}
    if((gon&&gon<3)||(hole&&hole<3))throw std::runtime_error("invalid polygon sizes");
    std::ifstream file;if(input!="-")file.open(input);std::istream&f=input=="-"?std::cin:file;int n;if(!(f>>n)||n<3||n>40)throw std::runtime_error("expected n in[3,40]");
    std::vector<Point>p(n);for(auto&a:p){std::string x,y;if(!(f>>x>>y))throw std::runtime_error("missing coordinates");a={decimal(x),decimal(y)};}
    std::string extra;if(f>>extra)throw std::runtime_error("extra data after coordinates");
    auto start=std::chrono::steady_clock::now();uint64_t collinear=0;
    for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)for(int k=j+1;k<n;k++)if(cross(p[i],p[j],p[k])==0)collinear++;
    std::vector<int>sorted(n);std::iota(sorted.begin(),sorted.end(),0);std::sort(sorted.begin(),sorted.end(),[&](int i,int j){return p[i].x<p[j].x||(p[i].x==p[j].x&&p[i].y<p[j].y);});
    auto hull=[&](const std::vector<int>&ids){std::vector<int>h;for(int i:ids){while(h.size()>1&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}auto lower=h.size();for(int k=int(ids.size())-2;k>=0;k--){int i=ids[k];while(h.size()>lower&&cross(p[h[h.size()-2]],p[h.back()],p[i])<=0)h.pop_back();h.push_back(i);}if(h.size()>1)h.pop_back();return h;};
    uint64_t checkedg=0,checkedh=0;
    auto count=[&](int k,bool empty,uint64_t&checked){uint64_t bad=0;if(!k||k>n)return bad;std::vector<int>ids;
        std::function<void(int)>rec=[&](int from){if(int(ids.size())==k){checked++;auto h=hull(ids);if(int(h.size())!=k)return;
            if(empty)for(int q=0;q<n;q++){if(std::find(ids.begin(),ids.end(),q)!=ids.end())continue;bool inside=true;for(int e=0;e<k;e++)if(cross(p[h[e]],p[h[(e+1)%k]],p[q])<=0){inside=false;break;}if(inside)return;}
            bad++;return;}
            for(int q=from;q<=n-(k-int(ids.size()));q++){ids.push_back(sorted[q]);rec(q+1);ids.pop_back();}};
        rec(0);return bad;};
    uint64_t g=count(gon,false,checkedg),h=count(hole,true,checkedh);bool valid=!collinear&&!g&&!h;
    std::cout<<"{\"n\":"<<n<<",\"gon\":"<<gon<<",\"hole\":"<<hole<<",\"valid\":"<<(valid?"true":"false")<<",\"arithmetic\":\"arbitrary_precision_integer\",\"collinear_triples\":"<<collinear<<",\"convex_gons\":"<<g<<",\"empty_holes\":"<<h<<",\"gon_subsets_checked\":"<<checkedg<<",\"hole_subsets_checked\":"<<checkedh<<",\"seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";return valid?0:1;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
