#include <float.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <signal.h>
#include "utils.c"
#include "evaluation.c"
#include "threading.c"

_Static_assert(ATOMIC_BOOL_LOCK_FREE == 2, "signal flag must be lock-free");
static atomic_bool interrupt_requested = false;
typedef struct {
    double seconds, minimum_radius, maximum_radius;
    long long iterations, check_every, line_every, pair_every;
    bool quiet, reference, warm, ordered_x;
    Point initial[MAX_POINTS];
} SolverOptions;
static SolverOptions solver_options = {.minimum_radius=0.1,.maximum_radius=15.0};
#ifndef LOCALIZER_WEIGHT_SUM_FAST
#define LOCALIZER_WEIGHT_SUM_FAST 0
#endif
static inline int sample_point(int *counts, int n, int total, double minimum_distance, rng_t *rng) {
#if LOCALIZER_WEIGHT_SUM_FAST
    /* Every violated distinct-point triple contributes to exactly three
     * per-point counts. Minimum-distance penalties affect only two points and
     * therefore deliberately retain the general reference sampler. */
    if (minimum_distance <= 0)
        return sample_proportional_known_total(counts, n, 3*WEIGHT_ADJUSTMENT*total+n, rng);
#else
    (void)total; (void)minimum_distance;
#endif
    return sample_proportional(counts, n, rng);
}
static bool points_ordered(const Point *points,int n) {
    for(int i=1;i<n;++i) if(!(points[i-1].x<points[i].x)) return false;
    return true;
}
static void initialize_ordered(Point *points,int n,const bool *fixed) {
    int left=-1;
    while(left<n) {
        int right=left+1;
        while(right<n && !fixed[right]) ++right;
        double lo=left>=0?points[left].x:(right<n?points[right].x-10:0);
        double hi=right<n?points[right].x:(left>=0?points[left].x+10:10);
        for(int j=left+1;j<right;++j)
            points[j].x=lo+(hi-lo)*(j-left)/(right-left);
        left=right;
    }
    if(!points_ordered(points,n)) {
        fprintf(stderr,"Fixed anchors leave no representable strictly ordered x initialization\n");
        exit(1);
    }
}
static void bound_ordered_proposal(Point *test,const Point *points,int chosen,int n,rng_t *rng) {
    double lo=chosen>0?nextafter(points[chosen-1].x,INFINITY):-DBL_MAX;
    double hi=chosen+1<n?nextafter(points[chosen+1].x,-INFINITY):DBL_MAX;
    if(test[chosen].x<lo || test[chosen].x>hi) {
        if(chosen>0 && chosen+1<n) test[chosen].x=lo+(hi-lo)*rng_float(rng);
        else if(test[chosen].x<lo) test[chosen].x=lo;
        else test[chosen].x=hi;
    }
}
typedef struct {
    long long iterations, proposals, evaluations, early_rejections, accepted, improvements, restarts;
    long long paired_proposals, line_proposals;
    double seconds;
    int final_violations;
} SolverStats;

typedef struct { double t; int delta; } LineEvent;
static int compare_events(const void *a,const void *b) {
    double x=((const LineEvent*)a)->t,y=((const LineEvent*)b)->t;
    return (x>y)-(x<y);
}
/* A determinant is affine in one moved point, quadratic for a coupled orbit.
 * Sweep its threshold crossings and select a minimum-violation interval.
 * Ordinary cached evaluation still checks the resulting floating-point move. */
static Point line_candidate_pair(const Point *points,int chosen,Point trial,double radius,
                            const Constraint *cs,const int *ids,int count,
                            const Symmetry *sym,LineEvent *events,SolverStats *stats,
                            int second,Point *second_trial) {
    Point p=points[chosen];
    double dx=trial.x-p.x,dy=trial.y-p.y,dx2=0,dy2=0,length=hypot(dx,dy);
    if(second>=0) {
        dx2=second_trial->x-points[second].x;
        dy2=second_trial->y-points[second].y;
        length=hypot(length,hypot(dx2,dy2));
    }
    if(!(length>0)) return trial;
    dx/=length; dy/=length; dx2/=length; dy2/=length;
    Point velocity[MAX_POINTS]={{0}};
    velocity[chosen]=(Point){dx,dy};
    if(second>=0) velocity[second]=(Point){dx2,dy2};
    for(int c=0;c<sym->num_cycles;++c)
      if(sym->cycles[c][0]==chosen || sym->cycles[c][0]==second) {
        Point v=velocity[sym->cycles[c][0]];
        for(int j=0;j<sym->cycle_lengths[c];++j)
            velocity[sym->cycles[c][j]]=rotate_r_k(v,j,sym->cycle_lengths[c]);
      }
    int used=0,score=0;
    for(int j=0;j<count;++j) {
        const Constraint *c=&cs[ids[j]];
        Point a=points[c->i-1],b=points[c->j-1],z=points[c->k-1];
        Point va=velocity[c->i-1],vb=velocity[c->j-1],vz=velocity[c->k-1];
        double bx=b.x-a.x,by=b.y-a.y,zx=z.x-a.x,zy=z.y-a.y;
        double vx=vb.x-va.x,vy=vb.y-va.y,wx=vz.x-va.x,wy=vz.y-va.y;
        double d=det(a,b,z),linear=vx*zy-vy*zx+bx*wy-by*wx;
        double quadratic=vx*wy-vy*wx;
        ++stats->evaluations;
        double left=d-radius*linear+radius*radius*quadratic;
        score+=!isfinite(left)||(c->sign==1?left<=EPSILON:c->sign==-1?left>=-EPSILON:fabs(left)>EPSILON);
        for(int side=-1;side<=1;side+=2) {
            if(c->sign && c->sign!=side) continue;
            double constant=d-side*EPSILON,roots[2];
            int nr=0;
            if(quadratic==0) {
                if(linear!=0) roots[nr++]=-constant/linear;
            } else {
                double disc=linear*linear-4*quadratic*constant;
                if(disc>0 && isfinite(disc)) {
                    double q=-0.5*(linear+copysign(sqrt(disc),linear));
                    roots[nr++]=q/quadratic;
                    if(q!=0) roots[nr++]=constant/q;
                }
            }
            for(int r=0;r<nr;++r) {
                double t=roots[r],slope=linear+2*quadratic*t;
                if(t<=-radius || t>=radius || !isfinite(t) || slope==0) continue;
                int delta;
                if(c->sign==1) delta=slope>0?-1:1;
                else if(c->sign==-1) delta=slope>0?1:-1;
                else delta=side==-1?(slope>0?-1:1):(slope>0?1:-1);
                events[used++]=(LineEvent){t,delta};
            }
        }
    }
    qsort(events,used,sizeof(*events),compare_events);
    int best=INT32_MAX,j=0;
    double left=-radius,best_t=0;
    while(j<=used) {
        double right=j<used?events[j].t:radius;
        double t=left+(right-left)*0.5;
        if(right>left && (score<best || (score==best && fabs(t)<fabs(best_t)))) {
            best=score; best_t=t;
        }
        if(j==used) break;
        left=right;
        do { score+=events[j++].delta; } while(j<used && events[j].t==left);
    }
    if(second>=0) *second_trial=(Point){points[second].x+best_t*dx2,points[second].y+best_t*dy2};
    return (Point){p.x+best_t*dx,p.y+best_t*dy};
}
static Point line_candidate(const Point *points,int chosen,Point trial,double radius,
                            const Constraint *cs,const int *ids,int count,
                            const Symmetry *sym,LineEvent *events,SolverStats *stats) {
    return line_candidate_pair(points,chosen,trial,radius,cs,ids,count,sym,events,stats,-1,NULL);
}
static inline unsigned char constraint_bad(const Point *p, const Constraint *c) {
    double d = det(p[c->i-1], p[c->j-1], p[c->k-1]);
    return !isfinite(d) || (c->sign == 1 ? d <= EPSILON :
                           c->sign == -1 ? d >= -EPSILON : fabs(d) > EPSILON);
}
static void cache_refresh(int n, const Point *p, const Constraint *cs, int m,
                          unsigned char *bad, int *counts, int *total, SolverStats *stats) {
    memset(counts,0,n*sizeof(int)); *total=0;
    for (int a=0;a<m;++a) {
        bad[a]=constraint_bad(p,&cs[a]); ++stats->evaluations;
        if (bad[a]) { ++*total; ++counts[cs[a].i-1]; ++counts[cs[a].j-1]; ++counts[cs[a].k-1]; }
    }
}
static void cache_check(int n,const Point *p,const Constraint *cs,int m,
                        const unsigned char *bad,const int *counts,int total) {
    int got[MAX_POINTS]={0},sum=0;
    for(int a=0;a<m;++a) {
        int v=constraint_bad(p,&cs[a]); assert(v==bad[a]);
        if(v) { ++sum; ++got[cs[a].i-1]; ++got[cs[a].j-1]; ++got[cs[a].k-1]; }
    }
    assert(sum==total);
    for(int i=0;i<n;++i) assert(got[i]==counts[i]);
}
/* Cache one flag per constraint and update only the deduplicated union of
 * constraints incident to a moved point/orbit. Rejected trials can stop early:
 * once new violations exceed the old sum, acceptance is impossible. */
void solve(int n,const Constraint *cs,int m,const int **incident,const int *incident_count,
           int sub_iterations,double minimum_distance,Point *points,const char *output_file,
           long long reset_its,int thread_id,synchronization_t *sync,rng_t *rng,
           const bool *fixed,const Point *fixed_points,const Symmetry *sym,SolverStats *stats) {
    (void)incident_count; (void)output_file;
    memset(stats,0,sizeof(*stats));
    int leader[MAX_POINTS],group_count[MAX_POINTS]={0},*groups[MAX_POINTS]={0};
    bool group_fixed[MAX_POINTS]={false};
    for(int i=0;i<n;++i) leader[i]=i;
    for(int c=0;c<sym->num_cycles;++c)
        for(int j=0;j<sym->cycle_lengths[c];++j)
            leader[sym->cycles[c][j]]=sym->cycles[c][0];
    for(int i=0;i<n;++i) if(fixed[i]) group_fixed[leader[i]]=true;
    for(int i=0;i<n;++i) if(leader[i]==i) {
        groups[i]=malloc((size_t)m*sizeof(int));
        if(!groups[i]) { perror("incident allocation"); exit(1); }
        for(int a=0;a<m;++a)
            if(leader[cs[a].i-1]==i||leader[cs[a].j-1]==i||leader[cs[a].k-1]==i)
                groups[i][group_count[i]++]=a;
    }
    unsigned char *bad=malloc((size_t)m),*candidate_bad=malloc((size_t)m);
    LineEvent *events=solver_options.line_every?malloc(4*(size_t)m*sizeof(LineEvent)):NULL;
    int *pair_ids=solver_options.pair_every?malloc((size_t)m*sizeof(int)):NULL;
    if(solver_options.pair_every && !pair_ids) { perror("pair allocation"); exit(1); }
    if(solver_options.line_every && !events) { perror("line allocation"); exit(1); }
    if(!bad||!candidate_bad) { perror("cache allocation"); exit(1); }
    if(solver_options.warm) memcpy(points,solver_options.initial,n*sizeof(Point));
    else generate_random_assignment(n,points,rng);
    for(int i=0;i<n;++i) if(fixed[i]) points[i]=fixed_points[i];
    enforce_symmetry(sym,points);
    if(solver_options.ordered_x) {
        if(!solver_options.warm) initialize_ordered(points,n,fixed);
        else if(!points_ordered(points,n)) { fprintf(stderr,"Warm start violates --ordered-x\n"); exit(1); }
    }
    struct timespec start=get_time();
    int total,counts[MAX_POINTS],maxp;
    double min_distance=0;
    cache_refresh(n,points,cs,m,bad,counts,&total,stats);
    if(minimum_distance>0)
        evaluate(points,n,cs,m,incident,minimum_distance,&total,counts,&maxp,&min_distance,-1,-1);
    sync_broadcast_new_solution(sync,points,total);
    long long since_improvement=0;
    double radii[sub_iterations];
    for(int s=0;s<sub_iterations;++s)
        radii[s]=fmax(solver_options.minimum_radius,solver_options.maximum_radius/pow(2,s));
    while(total>0) {
        long long it=stats->iterations;
        if(atomic_load_explicit(&interrupt_requested,memory_order_relaxed) ||
           (solver_options.iterations && it>=solver_options.iterations) ||
           (solver_options.seconds>0 && elapsed_time_sec(start,get_time())>=solver_options.seconds) ||
           sync_should_stop(sync)) break;
        if(since_improvement>reset_its) {
            ++stats->restarts;
            sync_get_best_solution(sync,points,&total,rng);
            for(int i=0;i<n;++i) if(fixed[i]) points[i]=fixed_points[i];
            enforce_symmetry(sym,points);
            Point best[MAX_POINTS],test[MAX_POINTS];
            int best_score=INT32_MAX;
            for(int attempt=0;attempt<100;++attempt) {
                memcpy(test,points,n*sizeof(Point));
                for(int j=0;j<n;++j) if(leader[j]==j&&!group_fixed[j])
                    test[j]=random_point_in_ball(points[j],0.2,rng);
                enforce_symmetry(sym,test);
                if(solver_options.ordered_x && !points_ordered(test,n)) continue;
                int score,cc[MAX_POINTS],mp; double md;
                evaluate(test,n,cs,m,incident,minimum_distance,&score,cc,&mp,&md,-1,-1);
                stats->evaluations+=m;
                if(score<best_score) { best_score=score; memcpy(best,test,n*sizeof(Point)); }
            }
            if(best_score!=INT32_MAX && (best_score<total || rng_float(rng)<0.3)) memcpy(points,best,n*sizeof(Point));
            cache_refresh(n,points,cs,m,bad,counts,&total,stats);
            if(minimum_distance>0)
                evaluate(points,n,cs,m,incident,minimum_distance,&total,counts,&maxp,&min_distance,-1,-1);
            sync_broadcast_new_solution(sync,points,total);
            since_improvement=0;
            if(!total) break;
        }
        if(!solver_options.quiet && it%(reset_its/2)==0)
            sync_printf(sync,"[Thread %d] [t %.3f s] [iterations %lld] [unsat %d]\n",
                        thread_id,elapsed_time_sec(start,get_time()),it,total);
        for(int s=0;s<sub_iterations;++s) {
            int chosen=leader[sample_point(counts,n,total,minimum_distance,rng)];
            if(group_fixed[chosen]) continue;
            ++stats->proposals;
            Point test[MAX_POINTS]; memcpy(test,points,n*sizeof(Point));
            test[chosen]=random_point_in_ball(points[chosen],radii[s],rng);
            if(solver_options.ordered_x) bound_ordered_proposal(test,points,chosen,n,rng);
            int second=-1,*ids=groups[chosen],gc=group_count[chosen];
            if(solver_options.pair_every && stats->proposals%solver_options.pair_every==0) {
                for(int attempt=0;attempt<8;++attempt) {
                    int candidate=leader[sample_point(counts,n,total,minimum_distance,rng)];
                    if(candidate!=chosen && !group_fixed[candidate]) { second=candidate; break; }
                }
                if(second>=0) {
                    ++stats->paired_proposals;
                    test[second]=random_point_in_ball(points[second],radii[s],rng);
                    if(solver_options.ordered_x) bound_ordered_proposal(test,points,second,n,rng);
                    ids=pair_ids; gc=0;
                    for(int a=0;a<m;++a) {
                        int x=leader[cs[a].i-1],y=leader[cs[a].j-1],z=leader[cs[a].k-1];
                        if(x==chosen||y==chosen||z==chosen||x==second||y==second||z==second)
                            ids[gc++]=a;
                    }
                }
            }
            if(solver_options.line_every && minimum_distance<=0 &&
               stats->proposals%solver_options.line_every==0) {
                ++stats->line_proposals;
                if(second<0)
                    test[chosen]=line_candidate(points,chosen,test[chosen],radii[s],cs,ids,gc,sym,events,stats);
                else
                    test[chosen]=line_candidate_pair(points,chosen,test[chosen],radii[s],cs,ids,gc,
                                                    sym,events,stats,second,&test[second]);
            }
            enforce_symmetry(sym,test);
            if(solver_options.ordered_x && !points_ordered(test,n)) continue;
            int old_local=0,new_local=0;
            int next_counts[MAX_POINTS],next_max; double next_min;
            if(minimum_distance>0) {
                old_local=total;
                evaluate(test,n,cs,m,incident,minimum_distance,&new_local,next_counts,&next_max,&next_min,-1,-1);
                stats->evaluations+=m;
            } else {
                if(!solver_options.reference && sym->num_cycles==0 && second<0) old_local=counts[chosen];
                else for(int j=0;j<gc;++j) {
                    if(solver_options.reference) {
                        old_local+=constraint_bad(points,&cs[ids[j]]); ++stats->evaluations;
                    } else old_local+=bad[ids[j]];
                }
                for(int j=0;j<gc;++j) {
                    candidate_bad[j]=constraint_bad(test,&cs[ids[j]]);
                    new_local+=candidate_bad[j]; ++stats->evaluations;
                    if(!solver_options.reference && new_local>old_local) {
                        ++stats->early_rejections; break;
                    }
                }
            }
            int improvement=new_local-old_local;
            if(improvement>0) continue;
            ++stats->accepted;
            memcpy(points,test,n*sizeof(Point));
            if(minimum_distance>0) { total=new_local; memcpy(counts,next_counts,n*sizeof(int)); }
            else {
                for(int j=0;j<gc;++j) {
                    int a=ids[j],change=(int)candidate_bad[j]-bad[a];
                    if(change) {
                        counts[cs[a].i-1]+=change; counts[cs[a].j-1]+=change; counts[cs[a].k-1]+=change;
                        bad[a]=candidate_bad[j];
                    }
                }
                total+=improvement;
            }
            if(improvement<0) {
                ++stats->improvements; sync_broadcast_new_solution(sync,points,total);
                since_improvement=0; break;
            }
        }
        ++stats->iterations; ++since_improvement;
        if(minimum_distance<=0 && solver_options.check_every>0 && stats->iterations%solver_options.check_every==0)
            cache_check(n,points,cs,m,bad,counts,total);
    }
    if(!total) { sync_broadcast_new_solution(sync,points,0); sync_set_stop(sync); }
    stats->final_violations=total; stats->seconds=elapsed_time_sec(start,get_time());
    free(bad); free(candidate_bad); free(events); free(pair_ids);
    for(int i=0;i<n;++i) free(groups[i]);
}
