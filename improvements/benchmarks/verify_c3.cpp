// Exact algebraic C3 reconstruction and exhaustive 19-point hexagon verifier.
// Coefficients are arbitrary-size integers; a+b*sqrt(3) signs use integer
// squares, never a floating-point tolerance. Search/native code is not shared.
#include <boost/multiprecision/cpp_int.hpp>
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using Big=boost::multiprecision::cpp_int;
static int sign(const Big&x){return (x>0)-(x<0);}
struct Q {
    Big a,b; // a+b sqrt(3)
    Q operator+(const Q&o)const{return {a+o.a,b+o.b};}
    Q operator-(const Q&o)const{return {a-o.a,b-o.b};}
    Q operator*(const Q&o)const{return {a*o.a+3*b*o.b,a*o.b+b*o.a};}
    int sgn()const{
        int sa=sign(a),sb=sign(b);
        if(!sa)return sb;
        if(!sb||sa==sb)return sa;
        int difference=sign(Big(a*a-3*b*b));return sa*difference;
    }
};
struct Point{Q x,y;};
struct IntegerPoint{Big x,y;};
static Q cross(const Point&a,const Point&b,const Point&c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
static Big integer_cross(const IntegerPoint&a,const IntegerPoint&b,const IntegerPoint&c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
static Big parse(const std::string&s){
    if(s.empty()||s.size()>10000)throw std::runtime_error("invalid integer length");
    size_t i=s[0]=='-'||s[0]=='+';if(i==s.size())throw std::runtime_error("invalid integer");
    Big x=0;for(;i<s.size();i++){if(s[i]<'0'||s[i]>'9')throw std::runtime_error("integer coordinates required");x=x*10+s[i]-'0';}
    return s[0]=='-'?-x:x;
}
static std::vector<int> hull(std::vector<int>ids,const std::vector<Point>&p){
    std::sort(ids.begin(),ids.end(),[&](int i,int j){int x=(p[i].x-p[j].x).sgn();return x<0||(!x&&(p[i].y-p[j].y).sgn()<0);});
    std::vector<int>out;
    for(int i:ids){while(out.size()>1&&cross(p[out[out.size()-2]],p[out.back()],p[i]).sgn()<=0)out.pop_back();out.push_back(i);}
    auto lower=out.size();
    for(int j=int(ids.size())-2;j>=0;j--){int i=ids[j];while(out.size()>lower&&cross(p[out[out.size()-2]],p[out.back()],p[i]).sgn()<=0)out.pop_back();out.push_back(i);}
    if(out.size()>1)out.pop_back();
    return out;
}
static void self_test(){
    unsigned checked=0;
    for(int a=-200;a<=200;a++)for(int b=-200;b<=200;b++){
        long double x=a+b*sqrtl(3);assert((Q{a,b}.sgn())==((x>0)-(x<0)));checked++;
    }
    Point p{{2,0},{0,0}},q{{-1,0},{0,1}},r{{-1,0},{0,-1}};
    Q determinant=cross(p,q,r);assert(determinant.a==0&&determinant.b==6);
    assert((p.x+q.x+r.x).sgn()==0&&(p.y+q.y+r.y).sgn()==0);
    std::cout<<"{\"status\":\"passed\",\"algebraic_sign_checks\":"<<checked<<"}\n";
}
int main(int argc,char**argv)try{
    std::string input,cycles,orient,output;bool lattice=false;
    for(int i=1;i<argc;i++){
        std::string a=argv[i];if(a=="--self-test"){self_test();return 0;}
        if(a=="--lattice"){lattice=true;continue;}
        if(i+1==argc)throw std::runtime_error("missing option value");
        std::string v=argv[++i];
        if(a=="--input")input=v;else if(a=="--cycles")cycles=v;else if(a=="--orient")orient=v;
        else if(a=="--output")output=v;else throw std::runtime_error("unknown option "+a);
    }
    auto start=std::chrono::steady_clock::now();
    std::ifstream in(input);int n;if(!(in>>n)||n!=19)throw std::runtime_error("expected19 integer points");
    std::vector<IntegerPoint>original(n);std::string x,y;
    for(auto&p:original){if(!(in>>x>>y))throw std::runtime_error("missing point");p={parse(x),parse(y)};}
    if(in>>x)throw std::runtime_error("extra point data");
    std::ifstream cycle_file(cycles);if(!cycle_file)throw std::runtime_error("cannot read cycles");
    std::vector<std::array<int,3>>orbits;std::array<bool,19>seen{};std::string line;
    while(std::getline(cycle_file,line)){
        if(line.find_first_not_of(" \t\r\n")==std::string::npos)continue;
        std::istringstream row(line);std::array<int,3>o;int extra;
        if(!(row>>o[0]>>o[1]>>o[2])||(row>>extra))throw std::runtime_error("each orbit needs exactly3 indices");
        for(int&i:o){--i;if(i<0||i>=n||seen[i])throw std::runtime_error("orbit indices must be disjoint in1..19");seen[i]=true;}
        orbits.push_back(o);
    }
    if(orbits.size()!=6)throw std::runtime_error("expected6 disjoint3cycles");
    int center=int(std::find(seen.begin(),seen.end(),false)-seen.begin());
    std::vector<Point>p(n);
    for(auto o:orbits){
        Big a=original[o[0]].x-original[center].x,b=original[o[0]].y-original[center].y;
        if(lattice){
            // Positive-determinant embedding L(x,y)=(2x-y,sqrt(3)*y)
            // conjugates T(x,y)=(-y,x-y) to Euclidean 120-degree rotation.
            p[o[0]]={{2*a-b,0},{0,b}};
            p[o[1]]={{-a-b,0},{0,a-b}};
            p[o[2]]={{2*b-a,0},{0,-a}};
        }else{
            p[o[0]]={{2*a,0},{2*b,0}};
            p[o[1]]={{-a,-b},{-b,a}};
            p[o[2]]={{-a,b},{-b,-a}};
        }
    }
    int collinear=0,duplicates=0,changed=0;
    for(int i=0;i<n;i++)for(int j=i+1;j<n;j++){
        duplicates+=(p[i].x-p[j].x).sgn()==0&&(p[i].y-p[j].y).sgn()==0;
        for(int k=j+1;k<n;k++){
            int s=cross(p[i],p[j],p[k]).sgn();collinear+=!s;
            changed+=s!=sign(integer_cross(original[i],original[j],original[k]));
        }
    }
    int constraints=0,violations=0;
    if(!orient.empty()){
        std::ifstream file(orient);if(!file)throw std::runtime_error("cannot read orientations");
        while(std::getline(file,line)){
            char c,extra;int i,j,k;
            if(std::sscanf(line.c_str()," %c_(%d, %d, %d) %c",&c,&i,&j,&k,&extra)!=4 ||
               (c!='A'&&c!='B'&&c!='C')||i<1||j<1||k<1||i>n||j>n||k>n||i==j||i==k||j==k)
                throw std::runtime_error("invalid orientation row");
            int desired=c=='A'?1:c=='B'?-1:0;
            violations+=cross(p[i-1],p[j-1],p[k-1]).sgn()!=desired;constraints++;
        }
    }
    std::array<unsigned long long,14>hist{};unsigned long long checked=0;
    std::array<int,6>ids={0,1,2,3,4,5};std::vector<int>first;
    for(;;){
        checked++;auto polygon=hull(std::vector<int>(ids.begin(),ids.end()),p);
        if(polygon.size()==6){
            int interior=0;
            for(int q=0;q<n;q++){
                bool inside=true;for(int e=0;e<6;e++)if(cross(p[polygon[e]],p[polygon[(e+1)%6]],p[q]).sgn()<=0){inside=false;break;}
                interior+=inside;
            }
            hist[interior]++;if((interior==0||interior==3)&&first.empty())first=polygon;
        }
        int j=5;while(j>=0&&ids[j]==n-6+j)--j;if(j<0)break;
        ++ids[j];for(int k=j+1;k<6;k++)ids[k]=ids[k-1]+1;
    }
    if(!output.empty()){
        std::ofstream f(output);if(!f)throw std::runtime_error("cannot write algebraic witness");
        f<<n<<'\n';for(auto&q:p)f<<q.x.a<<' '<<q.x.b<<' '<<q.y.a<<' '<<q.y.b<<'\n';
        std::ofstream o(output+".or");for(int k=2;k<n;k++)for(int j=1;j<k;j++)for(int i=0;i<j;i++){
            int s=cross(p[i],p[j],p[k]).sgn();o<<(s>0?'A':s<0?'B':'C')<<"_("<<i+1<<", "<<j+1<<", "<<k+1<<")\n";
        }
    }
    bool valid=!collinear&&!duplicates&&!hist[0]&&!hist[3];
    std::cout<<"{\"n\":19,\"arithmetic\":\"exact_integer_Qsqrt3\",\"exact_C3_symmetry\":true,\"valid\":"<<(valid?"true":"false")
             <<",\"input_basis\":\""<<(lattice?"affine_C3_lattice":"Cartesian")<<"\""
             <<",\"center_original_index\":"<<center+1<<",\"collinear_triples\":"<<collinear<<",\"duplicate_pairs\":"<<duplicates
             <<",\"orientation_changes_from_rounded_input\":"<<changed<<",\"constraint_count\":"<<constraints
             <<",\"orientation_violations\":"<<violations<<",\"six_subsets_checked\":"<<checked<<",\"interior_histogram\":[";
    for(size_t i=0;i<hist.size();i++)std::cout<<(i?",":"")<<hist[i];
    std::cout<<"],\"first_forbidden_hexagon\":[";for(size_t i=0;i<first.size();i++)std::cout<<(i?",":"")<<first[i]+1;
    std::cout<<"],\"seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<"}\n";
    return valid?0:1;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
