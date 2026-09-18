// Experimental direct-repair neighborhood: relocate a point just inside a hole.
// Reuse the portfolio's exact scoring engine; keep its search implementation stable.
// Build: c++ -O3 -std=c++17 -DNDEBUG direct/baseline/fill_hole.cpp -o direct/baseline/fill_hole
#define POINTSAT_GEOMETRY_ONLY
#include "../search.cpp"

static vector<int> hole_boundary(const Points& p, vector<int> ids) {
    sort(ids.begin(), ids.end(), [&](int a, int b) { return lessxy(p[a], p[b]); });
    vector<int> h;
    for (int i : ids) {
        while (h.size() >= 2 && cross(p[h[h.size()-2]], p[h.back()], p[i]) <= 0) h.pop_back();
        h.push_back(i);
    }
    size_t lower = h.size();
    for (int j = int(ids.size())-2; j >= 0; --j) {
        int i = ids[j];
        while (h.size() > lower && cross(p[h[h.size()-2]], p[h.back()], p[i]) <= 0) h.pop_back();
        h.push_back(i);
    }
    h.pop_back();
    return h;
}

int main(int argc, char** argv) try {
    string input, output="fill_hole.pts";
    int gon=7, hole=6;
    int insert_samples=0;
    bool adjacent_cells=false;
    bool breakout=false;
    bool require_triangle=false;
    uint64_t seed=51;
    double seconds=60, temperature=.5, hull_penalty=0;
    for (int i=1; i<argc; ++i) {
        string a=argv[i];
        if (a=="--adjacent-cells") { adjacent_cells=true; continue; }
        if (a=="--breakout") { breakout=true; adjacent_cells=true; continue; }
        if (a=="--require-triangle") { require_triangle=true; continue; }
        if (i+1>=argc) throw runtime_error("missing value for "+a);
        string value=argv[++i];
        if (a=="--input") input=value;
        else if (a=="--output") output=value;
        else if (a=="--gon") gon=stoi(value);
        else if (a=="--hole") hole=stoi(value);
        else if (a=="--seed") seed=stoull(value);
        else if (a=="--seconds") seconds=stod(value);
        else if (a=="--temperature") temperature=stod(value);
        else if (a=="--insert-samples") insert_samples=stoi(value);
        else if (a=="--hull-penalty") hull_penalty=stod(value);
        else throw runtime_error("unknown argument "+a);
    }
    if (seconds<0 || temperature<=0 || hull_penalty<0 || insert_samples<0 || hole<3 || hole>9 || gon<0 || gon>9 || (gon && gon<3))
        throw runtime_error("invalid parameters");
    Points p=read_points(input), best=p;
    Geometry geometry;
    if (!geometry.build(p)) throw runtime_error("input is not in general position");
    mt19937_64 rng(seed);
    uniform_real_distribution<double> unit(0,1);
    auto start=Clock::now();
    if (insert_samples) {
        if (p.size()>=40) throw runtime_error("cannot append beyond 40 points");
        int64_t minx=p[0].x,maxx=minx,miny=p[0].y,maxy=miny;
        for (auto q:p) { minx=min(minx,q.x); maxx=max(maxx,q.x); miny=min(miny,q.y); maxy=max(maxy,q.y); }
        uniform_int_distribution<int64_t> xs(minx,maxx),ys(miny,maxy);
        Points selected;
        uint64_t selected_score=numeric_limits<uint64_t>::max();
        for (int i=0;i<insert_samples && elapsed(start)<seconds;++i) {
            Points trial=p;
            trial.push_back({xs(rng),ys(rng)});
            Geometry candidate;
            if (!candidate.build(trial)) continue;
            if (require_triangle) {
                vector<int> candidate_ids(trial.size()); iota(candidate_ids.begin(),candidate_ids.end(),0);
                if (hole_boundary(trial,candidate_ids).size()!=3) continue;
            }
            auto score=candidate.count(trial,gon,hole);
            if (score.total()<selected_score) { selected_score=score.total(); selected=trial; }
            if (!selected_score) break;
        }
        if (selected.empty()) throw runtime_error("no general-position insertion sampled");
        p=selected; best=p; geometry.build(p);
    }
    Score score=geometry.count(p,gon,hole), best_score=score;
    vector<int> ids(p.size()); iota(ids.begin(),ids.end(),0);
    int hull_size=int(hole_boundary(p,ids).size()), best_hull=hull_size;
    if (require_triangle && hull_size!=3) throw runtime_error("--require-triangle needs a triangular starting hull");
    struct Penalty { uint64_t mask; double weight; bool empty; };
    vector<Penalty> penalties;
    uint64_t penalty_updates=0,last_penalty=0;
    double current_penalty=0;
    auto penalty_cost=[&](const Points& points,const Geometry& geom) {
        double cost=0;
        for (const auto& term:penalties) {
            vector<int> subset;
            for (int i=0;i<int(points.size());++i) if ((term.mask>>i)&1) subset.push_back(i);
            auto boundary=hole_boundary(points,subset);
            if (boundary.size()!=subset.size()) continue;
            if (term.empty) {
                uint64_t inside=(1ULL<<points.size())-1;
                for (size_t j=0;j<boundary.size();++j) inside &= geom.left[boundary[j]][boundary[(j+1)%boundary.size()]];
                if (inside) continue;
            }
            cost+=term.weight;
        }
        return cost;
    };
    uint64_t proposals=0,evaluations=1,accepted=0;
    double next_log=10;
    auto log=[&](const char* event) {
        cout << "{\"event\":\"" << event << "\",\"method\":\"fill_hole\",\"seed\":" << seed
             << ",\"n\":" << p.size() << ",\"insert_samples\":" << insert_samples
             << ",\"adjacent_cells\":" << (adjacent_cells ? "true" : "false")
             << ",\"breakout\":" << (breakout ? "true" : "false")
             << ",\"require_triangle\":" << (require_triangle ? "true" : "false")
             << ",\"penalty_terms\":" << penalties.size() << ",\"penalty_updates\":" << penalty_updates << ",\"penalty_cost\":" << current_penalty
             << ",\"hull_penalty\":" << hull_penalty << ",\"hull_size\":" << hull_size << ",\"best_hull\":" << best_hull
             << ",\"elapsed\":" << elapsed(start) << ",\"proposals\":" << proposals
             << ",\"evaluations\":" << evaluations << ",\"accepted\":" << accepted
             << ",\"gons\":" << score.gon << ",\"holes\":" << score.hole
             << ",\"best_gons\":" << best_score.gon << ",\"best_holes\":" << best_score.hole
             << ",\"best_score\":" << best_score.total() << "}" << endl;
    };
    save(output,best); log("start");
    while (elapsed(start)<seconds && best_score.total()) {
        ++proposals;
        vector<int> witness;
        geometry.count(p,0,hole,&witness,int(rng()%p.size()));
        if (witness.empty() && breakout) geometry.count(p,gon,0,&witness,int(rng()%p.size()));
        if (witness.empty()) {
            // A nonzero score may consist only of gons: return to the last
            // low-score point set to retain this neighborhood's target.
            p=best; geometry.build(p); score=best_score; hull_size=best_hull;
            current_penalty=penalty_cost(p,geometry);
            geometry.count(p,0,hole,&witness);
            if (witness.empty()) break;
        }
        auto boundary=hole_boundary(p,witness);
        long double cx=0,cy=0;
        for (int i : boundary) { cx+=p[i].x; cy+=p[i].y; }
        cx/=boundary.size(); cy/=boundary.size();
        if (adjacent_cells) {
            // Randomize the strict interior target while retaining the centroid
            // as positive weight, so boundary vertices are never target points.
            Point corner=p[boundary[rng()%boundary.size()]];
            long double weight=4.L*unit(rng);
            cx=(cx+weight*corner.x)/(1+weight);
            cy=(cy+weight*corner.y)/(1+weight);
        }
        int moved=int(rng()%p.size());
        if (!adjacent_cells && find(boundary.begin(),boundary.end(),moved)!=boundary.end()) continue;
        const Point from=p[moved];
        long double dx=cx-from.x,dy=cy-from.y,enter=0;
        // Intersect the segment from the selected outside point to the strict
        // interior centroid with the hole's supporting halfplanes. Floating
        // point selects a proposal only; exact geometry scores every trial.
        for (size_t j=0;j<boundary.size();++j) {
            Point a=p[boundary[j]],b=p[boundary[(j+1)%boundary.size()]];
            long double d=static_cast<long double>(cross(a,b,from));
            long double derivative=(b.x-a.x)*dy-(b.y-a.y)*dx;
            if (d<=0 && derivative>0) enter=max(enter,-d/derivative);
        }
        long double penetration=pow(10.L,-5.L*unit(rng));
        long double t=enter+(1-enter)*penetration;
        if (adjacent_cells) {
            long double first=1;
            for (int j=0;j<int(p.size());++j) if (j!=moved)
                for (int k=j+1;k<int(p.size());++k) if (k!=moved) {
                    long double d=static_cast<long double>(cross(from,p[j],p[k]));
                    long double derivative=dx*(p[j].y-p[k].y)+dy*(p[k].x-p[j].x);
                    if (derivative!=0) { long double crossing=-d/derivative; if (crossing>0) first=min(first,crossing); }
                }
            long double grid_step=2.L/max(1.L,max(abs(dx),abs(dy)));
            t=min(1.L,first*(1+pow(10.L,-4.L*unit(rng)))+grid_step);
        }
        Points trial=p;
        trial[moved]={llround(from.x+t*dx),llround(from.y+t*dy)};
        Geometry candidate;
        if (!candidate.build(trial)) continue;
        int candidate_hull=int(hole_boundary(trial,ids).size());
        if (require_triangle && candidate_hull!=3) continue;
        Score candidate_score=candidate.count(trial,gon,hole);
        double candidate_penalty=penalty_cost(trial,candidate);
        ++evaluations;
        double delta=double(candidate_score.total())-double(score.total())+hull_penalty*(candidate_hull-hull_size)+candidate_penalty-current_penalty;
        if (delta<=0 || unit(rng)<exp(-double(delta)/temperature)) {
            p.swap(trial); geometry=candidate; score=candidate_score; hull_size=candidate_hull; current_penalty=candidate_penalty; ++accepted;
        }
        if (score.total()<best_score.total() || (score.total()==best_score.total() && hull_size<best_hull)) {
            best=p; best_score=score; best_hull=hull_size; save(output,best); log("best");
            last_penalty=evaluations;
        }
        if (!breakout && proposals%(adjacent_cells ? 25000 : 2000)==0) { p=best; geometry.build(p); score=best_score; hull_size=best_hull; current_penalty=penalty_cost(p,geometry); }
        if (breakout && score.total() && evaluations-last_penalty>=5000) {
            vector<int> stubborn;
            geometry.count(p,gon,hole,&stubborn,int(rng()%p.size()));
            if (!stubborn.empty()) {
                uint64_t mask=0; for (int v:stubborn) mask|=1ULL<<v;
                bool empty=int(stubborn.size())==hole;
                auto found=find_if(penalties.begin(),penalties.end(),[&](const Penalty& term) { return term.mask==mask && term.empty==empty; });
                if (found!=penalties.end()) found->weight+=1;
                else {
                    if (penalties.size()==100) penalties.erase(penalties.begin());
                    penalties.push_back({mask,1,empty});
                }
                ++penalty_updates;
                current_penalty=penalty_cost(p,geometry);
            }
            last_penalty=evaluations;
        }
        if (elapsed(start)>=next_log) { log("progress"); next_log=elapsed(start)+10; }
    }
    save(output,best); log("done");
    return 0;
} catch (const exception& error) {
    cerr << error.what() << '\n';
    return 2;
}
