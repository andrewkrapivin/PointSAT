/* Independent sweep-vs-dense-grid and archive regressions. */
#include "../src/solver_fast.c"

static int score(const Point *p,const Constraint *cs,int m) {
    int result=0;
    for(int a=0;a<m;++a) result+=constraint_bad(p,&cs[a]);
    return result;
}
static void test_archive(void) {
    synchronization_t sync; sync_init(&sync);
    Point p[MAX_POINTS]={{0}};
    for(int i=9;i>=0;--i) { p[0].x=i; sync_broadcast_new_solution(&sync,p,i); }
    for(int i=0;i<10;++i) {
        assert(sync.top_k_solutions[i].violations==i);
        assert(sync.top_k_solutions[i].points[0].x==i);
    }
    rng_t rng; rng_init(&rng,101);
    for(int i=0;i<1000;++i) {
        int v; sync_get_best_solution(&sync,p,&v,&rng);
        assert(v>=0 && v<10 && p[0].x==v);
    }
    sync_destroy(&sync);
}
static void test_thresholds(void) {
    Point p[3]={{0,0},{1,0},{0,1}};
    Constraint c={1,2,3,1};
    assert(!constraint_bad(p,&c));
    c.sign=-1; assert(constraint_bad(p,&c));
    c.sign=0; assert(constraint_bad(p,&c));
    p[2].y=0; assert(!constraint_bad(p,&c));
    p[2].y=NAN; assert(constraint_bad(p,&c));
}
static void test_known_weight_sum(void) {
    rng_t data; rng_init(&data,6062241);
    for(int n=1;n<=MAX_POINTS;++n) for(int attempt=0;attempt<100;++attempt) {
        int weights[MAX_POINTS],total=0;
        for(int i=0;i<n;++i) { weights[i]=(int)(rng_float(&data)*10000); total+=WEIGHT_ADJUSTMENT*weights[i]+1; }
        rng_t old_rng,new_rng; rng_init(&old_rng,data.state); new_rng=old_rng;
        for(int repeat=0;repeat<10;++repeat) {
            assert(sample_proportional(weights,n,&old_rng)==sample_proportional_known_total(weights,n,total,&new_rng));
            assert(old_rng.state==new_rng.state);
        }
    }
}
static void test_stop_flag(void) {
    synchronization_t sync; sync_init(&sync);
    assert(!sync_should_stop(&sync));
    assert(sync_set_stop(&sync));
    assert(sync_should_stop(&sync));
    assert(!sync_set_stop(&sync));
    sync_destroy(&sync);
}
static void test_lines(bool symmetric,bool paired) {
    const int n=9;
    Constraint cs[84]; int ids[84],m=0;
    rng_t rng; rng_init(&rng,(symmetric?1777:1771)+(paired?10000:0));
    Symmetry sym={0};
    if(symmetric) {
        sym.num_cycles=3;
        for(int c=0;c<3;++c) {
            sym.cycle_lengths[c]=3;
            for(int j=0;j<3;++j) sym.cycles[c][j]=c*3+j;
        }
    }
    for(int i=1;i<=n;++i) for(int j=i+1;j<=n;++j) for(int k=j+1;k<=n;++k) {
        ids[m]=m; cs[m++]=(Constraint){i,j,k,1};
    }
    LineEvent events[336];
    for(int attempt=0;attempt<200;++attempt) {
        Point p[MAX_POINTS]={{0}},test[MAX_POINTS],trial;
        generate_random_assignment(n,p,&rng);
        enforce_symmetry(&sym,p);
        for(int a=0;a<m;++a) cs[a].sign=rng_float(&rng)<0.5?1:-1;
        if(attempt%5==0) cs[attempt%m].sign=0;
        int chosen=symmetric?(attempt%3)*3:attempt%n;
        int second=symmetric?((attempt+1)%3)*3:(attempt+1)%n;
        double radius=0.01+15*rng_float(&rng);
        trial=random_point_in_ball(p[chosen],radius,&rng);
        Point trial2=paired?random_point_in_ball(p[second],radius,&rng):p[second],result2=trial2;
        SolverStats stats={0};
        Point result=paired?line_candidate_pair(p,chosen,trial,radius,cs,ids,m,&sym,events,&stats,second,&result2):
                            line_candidate(p,chosen,trial,radius,cs,ids,m,&sym,events,&stats);
        memcpy(test,p,sizeof(p)); test[chosen]=result;
        if(paired) test[second]=result2;
        enforce_symmetry(&sym,test);
        int found=score(test,cs,m),best_grid=score(p,cs,m);
        double dx=trial.x-p[chosen].x,dy=trial.y-p[chosen].y,len=hypot(dx,dy);
        double dx2=trial2.x-p[second].x,dy2=trial2.y-p[second].y;
        if(paired) len=hypot(len,hypot(dx2,dy2));
        dx/=len; dy/=len; dx2/=len; dy2/=len;
        for(int step=0;step<=1000;++step) {
            double t=-radius+2*radius*step/1000.0;
            memcpy(test,p,sizeof(p));
            test[chosen]=(Point){p[chosen].x+t*dx,p[chosen].y+t*dy};
            if(paired) test[second]=(Point){p[second].x+t*dx2,p[second].y+t*dy2};
            enforce_symmetry(&sym,test);
            int got=score(test,cs,m);
            if(got<best_grid) best_grid=got;
        }
        if(found>best_grid) {
            fprintf(stderr,"line mismatch symmetric=%d paired=%d attempt=%d found=%d grid=%d\n",
                    symmetric,paired,attempt,found,best_grid);
            abort();
        }
    }
}
int main(void) {
    test_archive(); test_thresholds();
    test_known_weight_sum(); test_stop_flag();
    test_lines(false,false); test_lines(true,false); test_lines(false,true); test_lines(true,true);
    puts("Native archive/stop tests, 81000 exact sampler comparisons, nonfinite/C thresholds, and 800 single/paired line-vs-1001-grid cases passed.");
    return 0;
}
