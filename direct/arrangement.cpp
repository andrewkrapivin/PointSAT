// Complete one-point extension search for fixed integer coordinates.
// Every cell of the arrangement of old pair-lines has the same extension
// order type. Test symbolic infinitesimal sectors at all line intersections.
#define main overmars_cli_main
#include "overmars.cpp"
#undef main
#include <unordered_set>
#include <boost/multiprecision/cpp_int.hpp>

using Wide=__int128_t;
using UnsignedWide=__uint128_t;
using Big=boost::multiprecision::cpp_int;
struct Line { Wide a,b,c;int i,j; };
struct Signature {
    std::array<uint64_t,8> words{};
    bool operator==(const Signature& other)const{return words==other.words;}
};
struct HashSignature {std::size_t operator()(const Signature& s)const {
    uint64_t h=1469598103934665603ULL;for(auto w:s.words){h^=w;h*=1099511628211ULL;}return h;
}};
Wide magnitude(Wide v){return v<0?-v:v;}
int signum(Wide v){return (v>0)-(v<0);}
Big round_ratio(Big numerator,const Big& denominator) {
    bool negative=numerator<0;if(negative)numerator=-numerator;
    Big q=(2*numerator+denominator)/(2*denominator);return negative?-q:q;
}
struct Certificate { bool small=false;std::string denominator;Points points; };
struct ArrangementResult { bool found=false,small=false,complete=false;Points points; };
Certificate materialize(const Points& old,const std::vector<Line>& lines,
                        Wide x,Wide y,Wide w,Wide dx,Wide dy,
                        const signed char qs[M][M],const std::string& output) {
    // epsilon=1/T, strictly below every nonzero line-sign crossing distance.
    UnsignedWide t_value=1;
    for(auto line:lines) {
        Wide value=line.a*x+line.b*y+line.c*w;
        Wide derivative=line.a*dx+line.b*dy;
        if(value&&derivative) {
            UnsignedWide bound=UnsignedWide(w)*UnsignedWide(magnitude(derivative))/UnsignedWide(magnitude(value))+1;
            if(bound>t_value)t_value=bound;
        }
    }
    t_value*=2;Big t(t_value);
    Big denominator=Big(w)*t,nx=Big(x)*t+Big(w)*Big(dx),ny=Big(y)*t+Big(w)*Big(dy);
    constexpr int64_t limit=1000000000000000000LL;
    // Try a compact common integer scaling of the old coordinates. Rounding
    // is accepted only if every extension orientation sign remains exact.
    for(int64_t scale=1;;) {
        bool fits=true;Points candidate;
        for(auto p:old) {
            Wide sx=Wide(p.x)*scale,sy=Wide(p.y)*scale;
            if(sx < -Wide(limit)||sx>limit||sy < -Wide(limit)||sy>limit){fits=false;break;}
            candidate.push_back({int64_t(sx),int64_t(sy)});
        }
        if(!fits)break;
        Big qx=round_ratio(nx*scale,denominator),qy=round_ratio(ny*scale,denominator);
        if(qx>=-Big(limit)&&qx<=limit&&qy>=-Big(limit)&&qy<=limit) {
            P q{qx.convert_to<int64_t>(),qy.convert_to<int64_t>()};bool matches=true;
            for(int i=0;i<int(old.size())&&matches;++i)for(int j=i+1;j<int(old.size())&&matches;++j)
                if(turn(q,candidate[i],candidate[j])!=qs[i][j])matches=false;
            if(matches) {
                candidate.push_back(q);std::ofstream f(output);if(!f)throw std::runtime_error("cannot write certificate");
                f << candidate.size() << '\n';for(auto p:candidate)f << p.x << ' ' << p.y << '\n';
                return {true,t.str(),candidate};
            }
        }
        if(scale>limit/10)break;
        scale*=10;
    }
    // Always construct exact integer coordinates, using arbitrary precision
    // if necessary. Independent verify_big is required for this certificate.
    std::ofstream f(output);if(!f)throw std::runtime_error("cannot write certificate");
    f << old.size()+1 << '\n';for(auto p:old)f << Big(p.x)*denominator << ' ' << Big(p.y)*denominator << '\n';
    f << nx << ' ' << ny << '\n';return {false,t.str(),{}};
}
std::vector<std::vector<int>> existing_empty_holes(const Points& p,const Oracle& oracle,int k) {
    std::vector<std::vector<int>> holes;if(!k||k>int(p.size()))return holes;
    std::vector<int> order(p.size()),chosen;std::iota(order.begin(),order.end(),0);
    std::sort(order.begin(),order.end(),[&](int a,int b){return p[a].x<p[b].x||(p[a].x==p[b].x&&p[a].y<p[b].y);});
    auto recurse=[&](auto&& self,int begin)->void {
        if(int(chosen.size())<k){for(int j=begin;j<=int(p.size())-(k-int(chosen.size()));++j){chosen.push_back(order[j]);self(self,j+1);chosen.pop_back();}return;}
        std::vector<int> boundary;
        for(int i:chosen){while(boundary.size()>1&&turn(p[boundary[boundary.size()-2]],p[boundary.back()],p[i])<=0)boundary.pop_back();boundary.push_back(i);}
        auto lower=boundary.size();for(int j=k-2;j>=0;--j){int i=chosen[j];while(boundary.size()>lower&&turn(p[boundary[boundary.size()-2]],p[boundary.back()],p[i])<=0)boundary.pop_back();boundary.push_back(i);}
        boundary.pop_back();if(int(boundary.size())!=k)return;
        U interior=(U(1)<<p.size())-1;for(int j=0;j<k;++j)interior&=oracle.left[boundary[j]][boundary[(j+1)%k]];
        if(!interior)holes.push_back(std::move(boundary));
    };
    recurse(recurse,0);return holes;
}
ArrangementResult arrangement_search(const Points& p,int gon,int hole,double seconds,
                                     const std::string& input,const std::string& output,bool allow_base_holes=false) {
    if(seconds<=0||!std::isfinite(seconds)||gon<0||gon>10||hole<0||hole>10||(gon&&gon<3)||(hole&&hole<3))throw std::runtime_error("invalid limits");
    if(p.size()<3||p.size()>32)throw std::runtime_error("require3..32 seed points");
    // With |coordinate|<=1e9, line coefficients satisfy |a|,|b|<=2e9,
    // |c|<=2e18; homogeneous intersection evaluation has magnitude <4.8e37,
    // within signed128-bit range (~1.7e38).
    for(auto q:p)if(q.x < -1000000000LL||q.x>1000000000LL||q.y < -1000000000LL||q.y>1000000000LL)throw std::runtime_error("exact128-bit arrangement requires |coordinates|<=1e9");
    auto oracle=std::make_unique<Oracle>(p,gon,hole);
    if(!oracle->general_position())throw std::runtime_error("seed must be in general position");
    if(!valid(p,gon,0)) {
        std::cout << "{\"method\":\"exact_line_arrangement\",\"input\":" << std::quoted(input) << ",\"seed_n\":" << p.size() << ",\"status\":\"base_has_forbidden_gon\"}" << std::endl;
        return {false,false,true,{}};
    }
    auto old_holes=existing_empty_holes(p,*oracle,hole);
    if(!allow_base_holes&&!old_holes.empty())throw std::runtime_error("seed has holes; pass --allow-base-holes to require the inserted point to fill all of them");
    std::vector<Line> lines;
    for(int i=0;i<int(p.size());++i)for(int j=i+1;j<int(p.size());++j)
        lines.push_back({Wide(p[i].y)-p[j].y,Wide(p[j].x)-p[i].x,Wide(p[i].x)*p[j].y-Wide(p[i].y)*p[j].x,i,j});
    std::unordered_set<Signature,HashSignature> cells;cells.reserve(200000);
    uint64_t vertices=0,sectors=0,duplicates=0,degenerate=0;bool timeout=false,found=false;Certificate certificate;
    Wide found_x=0,found_y=0,found_w=0,found_dx=0,found_dy=0;
    const auto start=std::chrono::steady_clock::now();
    auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
    for(std::size_t a=0;a<lines.size()&&!found&&!timeout;++a)for(std::size_t b=a+1;b<lines.size()&&!found&&!timeout;++b) {
        Wide x=lines[a].b*lines[b].c-lines[a].c*lines[b].b;
        Wide y=lines[a].c*lines[b].a-lines[a].a*lines[b].c;
        Wide w=lines[a].a*lines[b].b-lines[a].b*lines[b].a;
        if(!w)continue;
        if(w<0){x=-x;y=-y;w=-w;}++vertices;
        std::vector<Wide> values;values.reserve(lines.size());for(auto l:lines)values.push_back(l.a*x+l.b*y+l.c*w);
        for(int sa:{-1,1})for(int sb:{-1,1}) {
            if(found||timeout)break;
            if((++sectors&255)==0&&elapsed()>=seconds){timeout=true;break;}
            Wide dx=sa*lines[a].b+sb*lines[b].b,dy=-sa*lines[a].a-sb*lines[b].a;
            signed char qs[M][M]{};bool upper[M]{};Signature signature;bool gp=true;
            for(std::size_t k=0;k<lines.size();++k) {
                auto l=lines[k];int sign=values[k]?signum(values[k]):signum(l.a*dx+l.b*dy);
                if(!sign){gp=false;break;}
                qs[l.i][l.j]=sign;qs[l.j][l.i]=-sign;
                if(sign>0)signature.words[k/64]|=uint64_t(1)<<(k%64);
            }
            if(!gp){++degenerate;continue;}
            if(!cells.insert(signature).second){++duplicates;continue;}
            bool fills_all=true;
            for(const auto& boundary:old_holes) {
                for(std::size_t j=0;j<boundary.size();++j)if(qs[boundary[j]][boundary[(j+1)%boundary.size()]]<=0){fills_all=false;break;}
                if(!fills_all)break;
            }
            if(!fills_all)continue;
            for(int i=0;i<int(p.size());++i) {
                Wide py=Wide(p[i].y)*w-y,px=Wide(p[i].x)*w-x;
                int sy=py?signum(py):-signum(dy),sx=px?signum(px):-signum(dx);
                upper[i]=sy>0||(sy==0&&sx>0);
            }
            if(oracle->insertion_signs(qs,upper)) {
                certificate=materialize(p,lines,x,y,w,dx,dy,qs,output);
                found=true;found_x=x;found_y=y;found_w=w;found_dx=dx;found_dy=dy;
            }
        }
    }
    std::cout << "{\"method\":\"exact_line_arrangement\",\"input\":" << std::quoted(input) << ",\"seed_n\":" << p.size()
              << ",\"gon\":" << gon << ",\"hole\":" << hole << ",\"elapsed\":" << elapsed() << ",\"line_pairs\":" << vertices
              << ",\"old_empty_holes\":" << old_holes.size()
              << ",\"sectors\":" << sectors << ",\"distinct_cells\":" << cells.size() << ",\"duplicate_cells\":" << duplicates
              << ",\"degenerate_sectors\":" << degenerate << ",\"status\":\""
              << (found?(certificate.small?"extension_found_integer":"extension_found_bigint"):(timeout?"time_limit":"no_extension_fixed_seed")) << '"';
    if(found)std::cout << ",\"output\":" << std::quoted(output) << ",\"vertex\":[\"" << Big(found_x) << "\",\"" << Big(found_y) << "\",\"" << Big(found_w)
        << "\"],\"direction\":[\"" << Big(found_dx) << "\",\"" << Big(found_dy) << "\"],\"epsilon_denominator\":\"" << certificate.denominator << '"';
    std::cout << "}" << std::endl;return {found,certificate.small,!timeout,certificate.points};
}
static std::string callback_output="arrangement-extension.pts";
bool arrangement_callback(Points& p,int gon,int hole,double seconds_left) {
    if(seconds_left<=0)return false;
    for(auto q:p)if(q.x < -1000000000LL||q.x>1000000000LL||q.y < -1000000000LL||q.y>1000000000LL)return false;
    auto result=arrangement_search(p,gon,hole,seconds_left,"evolving_direct_coordinates",callback_output);
    if(result.found&&result.small){p=std::move(result.points);return true;}
    if(result.found){std::cout << "{\"event\":\"exact_bigint_certificate_saved\",\"output\":" << std::quoted(callback_output) << "}" << std::endl;std::exit(0);}
    return false;
}
#ifndef ARRANGEMENT_LIBRARY
int main(int argc,char** argv)try {
    if(argc>1&&std::string(argv[1])=="--grow") {
        for(int i=2;i+1<argc;++i)if(std::string(argv[i])=="--output")callback_output=std::string(argv[i+1])+".exact.pts";
        extension_search=&arrangement_callback;return overmars_cli_main(argc-1,argv+1);
    }
    std::string input,output="arrangement-extension.pts";double seconds=60;int gon=7,hole=6;bool allow_base_holes=false;
    for(int i=1;i<argc;++i) {
        std::string a=argv[i];if(a=="--crosscheck"){crosscheck_oracle=true;continue;}
        if(a=="--allow-base-holes"){allow_base_holes=true;continue;}
        if(i+1>=argc)throw std::runtime_error("missing option value");
        std::string v=argv[++i];
        if(a=="--input")input=v;else if(a=="--output")output=v;else if(a=="--gon")gon=std::stoi(v);
        else if(a=="--hole")hole=std::stoi(v);else if(a=="--seconds")seconds=std::stod(v);else throw std::runtime_error("unknown option "+a);
    }
    arrangement_search(read_points(input),gon,hole,seconds,input,output,allow_base_holes);return 0;
}catch(const std::exception& e){std::cerr << "arrangement: " << e.what() << '\n';return 2;}
#endif
