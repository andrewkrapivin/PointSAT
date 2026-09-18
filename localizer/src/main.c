#include <stdio.h>
#include <float.h>
#include <stdbool.h>
#include <unistd.h>
#include <getopt.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include "utils.c"
#include "solver_fast.c"
#include "rng.c"

typedef struct {
    int id,n,m,sub_iterations;
    Constraint *constraints;
    int **incident,*incident_count;
    bool *fixed;
    Point *fixed_points;
    Symmetry *symmetry;
    double minimum_distance;
    long long reset_its;
    rng_t rng;
    Point points[MAX_POINTS];
    synchronization_t *sync;
    SolverStats stats;
} thread_params_t;

static void print_usage(void) {
    fprintf(stderr,"Usage: localizer ORIENTATIONS [-i subiterations] [-s seed] [-d min_distance]\n"
            "  [-o output] [-r reset_iterations] [-t threads] [-f fixed] [-c symmetry]\n"
            "  [-w indexed_coordinates] [-T seconds] [-I max_iterations] [-q]\n"
            "  [--reference-evaluation] [--check-every iterations] [--line-every proposals]\n"
            "  [--min-radius radius] [--max-radius radius] [--archive-prefix PATH]\n"
            "  [--pair-every proposals] [--ordered-x]\n");
}
static void handle_signal(int sig) {
    (void)sig;
    atomic_store_explicit(&interrupt_requested,true,memory_order_relaxed);
}
static long long integer_arg(const char *s,long long low,long long high) {
    char *end; errno=0; long long v=strtoll(s,&end,10);
    if(errno || !*s || *end || v<low || v>high) {
        fprintf(stderr,"Invalid integer argument: %s\n",s); exit(1);
    }
    return v;
}
static double real_arg(const char *s) {
    char *end; errno=0; double v=strtod(s,&end);
    if(errno || !*s || *end || !isfinite(v)) { fprintf(stderr,"Invalid real argument: %s\n",s); exit(1); }
    return v;
}
static void read_warm(const char *path,int n) {
    FILE *f=fopen(path,"r");
    if(!f) { perror(path); exit(1); }
    bool seen[MAX_POINTS]={false};
    char line[1024],extra; int i,count=0; double x,y;
    while(fgets(line,sizeof(line),f)) {
        if(sscanf(line," %d %lf %lf %c",&i,&x,&y,&extra)!=3 || i<1 || i>n ||
           seen[i-1] || !isfinite(x) || !isfinite(y)) {
            fprintf(stderr,"Invalid warm-start row in %s\n",path); exit(1);
        }
        seen[i-1]=true; ++count; solver_options.initial[i-1]=(Point){x,y};
    }
    fclose(f);
    if(count!=n) { fprintf(stderr,"Warm start needs exactly %d indexed rows\n",n); exit(1); }
    solver_options.warm=true;
}
static void validate_symmetry(int n,Symmetry *sym,bool *fixed,Point *fixed_points) {
    bool seen[MAX_POINTS]={false};
    for(int c=0;c<sym->num_cycles;++c) {
        int k=sym->cycle_lengths[c],fixed_member=-1;
        if(k<1 || k>n) { fprintf(stderr,"Invalid symmetry cycle length\n"); exit(1); }
        for(int j=0;j<k;++j) {
            int i=sym->cycles[c][j];
            if(i<0 || i>=n || seen[i]) { fprintf(stderr,"Symmetry indices must be disjoint and in range\n"); exit(1); }
            seen[i]=true;
            if(fixed[i]) fixed_member=j;
        }
        if(fixed_member>=0) {
            int idx=sym->cycles[c][fixed_member];
            Point lead=rotate_r_k(fixed_points[idx],-fixed_member,k);
            for(int j=0;j<k;++j) {
                int i=sym->cycles[c][j]; Point expected=rotate_r_k(lead,j,k);
                double tolerance=1e-10*(1+fabs(expected.x)+fabs(expected.y));
                if(fixed[i] && (fabs(fixed_points[i].x-expected.x)>tolerance ||
                                 fabs(fixed_points[i].y-expected.y)>tolerance)) {
                    fprintf(stderr,"Fixed coordinates conflict with symmetry\n"); exit(1);
                }
                fixed[i]=true; fixed_points[i]=expected;
            }
        }
    }
}
static void *thread_solve(void *arg) {
    thread_params_t *p=arg;
    solve(p->n,p->constraints,p->m,(const int**)p->incident,p->incident_count,
          p->sub_iterations,p->minimum_distance,p->points,NULL,p->reset_its,p->id,
          p->sync,&p->rng,p->fixed,p->fixed_points,p->symmetry,&p->stats);
    return NULL;
}
int main(int argc,char **argv) {
    if(argc<2) { print_usage(); return 1; }
    if(strcmp(argv[1],"--help")==0 || strcmp(argv[1],"-h")==0) { print_usage(); return 0; }
    const char *orientation_file=argv[1],*output="output.txt",*fixed_file=NULL,*symmetry_file=NULL,*warm_file=NULL;
    const char *archive_prefix=NULL;
    int sub_iterations=10,nthreads=1,seed=42; double minimum_distance=-1;
    long long reset_its=30000;
    static const struct option long_options[]={
        {"reference-evaluation",no_argument,NULL,1000},
        {"check-every",required_argument,NULL,1001},
        {"line-every",required_argument,NULL,1002},
        {"min-radius",required_argument,NULL,1003},
        {"max-radius",required_argument,NULL,1004},
        {"archive-prefix",required_argument,NULL,1005},
        {"pair-every",required_argument,NULL,1006},
        {"ordered-x",no_argument,NULL,1007},
        {"max-iterations",required_argument,NULL,'I'},
        {"seconds",required_argument,NULL,'T'},
        {"warm-start",required_argument,NULL,'w'},
        {"help",no_argument,NULL,'h'},
        {NULL,0,NULL,0}};
    int opt;
    while((opt=getopt_long(argc-1,argv+1,"i:s:d:o:r:t:f:c:w:T:I:qh",long_options,NULL))!=-1) {
        switch(opt) {
            case 'i': sub_iterations=integer_arg(optarg,1,1000); break;
            case 's': seed=integer_arg(optarg,0,INT32_MAX); break;
            case 'd': minimum_distance=real_arg(optarg); break;
            case 'o': output=optarg; break;
            case 'r': reset_its=integer_arg(optarg,2,INT32_MAX); break;
            case 't': nthreads=integer_arg(optarg,1,256); break;
            case 'f': fixed_file=optarg; break;
            case 'c': symmetry_file=optarg; break;
            case 'w': warm_file=optarg; break;
            case 'T': solver_options.seconds=real_arg(optarg); if(solver_options.seconds<=0) return 1; break;
            case 'I': solver_options.iterations=integer_arg(optarg,1,INT64_MAX); break;
            case 'q': solver_options.quiet=true; break;
            case 'h': print_usage(); return 0;
            case 1000: solver_options.reference=true; break;
            case 1001: solver_options.check_every=integer_arg(optarg,1,INT64_MAX); break;
            case 1002: solver_options.line_every=integer_arg(optarg,1,INT64_MAX); break;
            case 1003: solver_options.minimum_radius=real_arg(optarg); if(solver_options.minimum_radius<0) return 1; break;
            case 1004: solver_options.maximum_radius=real_arg(optarg); if(solver_options.maximum_radius<=0) return 1; break;
            case 1005: archive_prefix=optarg; break;
            case 1006: solver_options.pair_every=integer_arg(optarg,1,INT64_MAX); break;
            case 1007: solver_options.ordered_x=true; break;
            default: print_usage(); return 1;
        }
    }
    int n,m;
    Constraint *constraints=calloc(MAX_CONSTRAINTS,sizeof(Constraint));
    int **incident=calloc(MAX_POINTS,sizeof(int*)),*incident_count=calloc(MAX_POINTS,sizeof(int));
    if(!constraints||!incident||!incident_count) { perror("allocation"); return 1; }
    for(int i=0;i<MAX_POINTS;++i) {
        incident[i]=calloc(MAX_CONSTRAINTS,sizeof(int));
        if(!incident[i]) { perror("allocation"); return 1; }
    }
    parse_constraints(orientation_file,&n,constraints,&m,incident,incident_count);
    bool fixed[MAX_POINTS]={false}; Point fixed_points[MAX_POINTS]={{0}};
    parse_fixed_points(fixed_file,n,fixed_points,fixed);
    Symmetry sym={0}; parse_symmetry(symmetry_file,&sym);
    validate_symmetry(n,&sym,fixed,fixed_points);
    if(solver_options.ordered_x) {
        if(sym.num_cycles) { fprintf(stderr,"--ordered-x cannot be combined with rotation cycles\n"); return 1; }
        for(int i=0;i<n;++i) if(fixed[i]) for(int j=i+1;j<n;++j)
            if(fixed[j] && !(fixed_points[i].x<fixed_points[j].x)) {
                fprintf(stderr,"Fixed points contradict --ordered-x\n"); return 1;
            }
    }
    if(warm_file) read_warm(warm_file,n);
    synchronization_t sync; sync_init(&sync);
    struct sigaction sa={0}; sa.sa_handler=handle_signal; sigemptyset(&sa.sa_mask);
    sigaction(SIGINT,&sa,NULL); sigaction(SIGTERM,&sa,NULL);
    pthread_t *threads=calloc(nthreads,sizeof(*threads));
    thread_params_t *params=calloc(nthreads,sizeof(*params));
    if(!threads||!params) { perror("allocation"); return 1; }
    if(!solver_options.quiet) printf("Parsed %d constraints over %d points\n",m,n);
    int created=0;
    for(int i=0;i<nthreads;++i) {
        thread_params_t *p=&params[i];
        p->id=i+1; p->n=n; p->m=m; p->constraints=constraints; p->incident=incident;
        p->incident_count=incident_count; p->fixed=fixed; p->fixed_points=fixed_points; p->symmetry=&sym;
        p->sub_iterations=sub_iterations; p->minimum_distance=minimum_distance; p->reset_its=reset_its; p->sync=&sync;
        rng_init(&p->rng,(uint64_t)seed+i);
        if(pthread_create(&threads[i],NULL,thread_solve,p)!=0) {
            fprintf(stderr,"Failed to create worker\n"); atomic_store(&interrupt_requested,true); break;
        }
        ++created;
    }
    for(int i=0;i<created;++i) pthread_join(threads[i],NULL);
    Solution best=sync.top_k_solutions[0];
    if(best.violations==INT32_MAX) { fprintf(stderr,"No worker initialized\n"); return 1; }
    int checked,counts[MAX_POINTS],maxp; double md=0;
    evaluate(best.points,n,constraints,m,(const int**)incident,minimum_distance,&checked,counts,&maxp,&md,-1,-1);
    if(checked!=best.violations) { fprintf(stderr,"Internal objective mismatch\n"); return 2; }
    serialize_solution(n,best.points,output);
    if(archive_prefix && *archive_prefix) {
        size_t size=strlen(archive_prefix)+32;
        char *archive_name=malloc(size);
        if(!archive_name) { perror("archive filename allocation"); return 1; }
        for(int k=0;k<K_TOP && sync.top_k_solutions[k].violations!=INT32_MAX;++k) {
            Solution *entry=&sync.top_k_solutions[k];
            int archive_checked;
            evaluate(entry->points,n,constraints,m,(const int**)incident,minimum_distance,
                     &archive_checked,counts,&maxp,&md,-1,-1);
            if(archive_checked!=entry->violations) { fprintf(stderr,"Archive objective mismatch\n"); return 2; }
            snprintf(archive_name,size,"%s-%02d.real",archive_prefix,k);
            serialize_solution(n,entry->points,archive_name);
            printf("Archive saved: %s (violations %d)\n",archive_name,archive_checked);
        }
        free(archive_name);
    }
    printf("%s\nViolations: %d\nSolution saved to %s\n",checked?"STOPPED":"SOLVED",checked,output);
    for(int i=0;i<created;++i) {
        SolverStats *s=&params[i].stats;
        printf("{\"thread\":%d,\"seconds\":%.9f,\"iterations\":%lld,\"proposals\":%lld,"
               "\"constraint_evaluations\":%lld,\"early_rejections\":%lld,\"accepted\":%lld,"
               "\"improvements\":%lld,\"restarts\":%lld,\"paired_proposals\":%lld,\"line_proposals\":%lld,"
               "\"final_violations\":%d,\"best_violations\":%d}\n",
               i+1,s->seconds,s->iterations,s->proposals,s->evaluations,s->early_rejections,
               s->accepted,s->improvements,s->restarts,s->paired_proposals,s->line_proposals,s->final_violations,checked);
    }
    sync_destroy(&sync);
    for(int i=0;i<MAX_POINTS;++i) free(incident[i]);
    free(incident); free(incident_count); free(constraints); free(threads); free(params);
    return created==nthreads?0:1;
}
