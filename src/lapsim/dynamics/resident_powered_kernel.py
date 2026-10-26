"""Device-resident powered RK stages, ported from the CPU reference.

No relaxed math, state/energy clipping, implicit wheel projection or CPU fallback.
Each work item owns one lane's held-command interval and adaptive event loop.
The extra per-launch work ceiling is a GPU watchdog guard, never a scoring pass.
"""
from .planar_opencl import PLANAR_FUNCTION

RESIDENT_KERNEL = PLANAR_FUNCTION + r"""
#define PARAMS 89
#define STATE 28
#define MAX_LAUNCH_TRIALS 2048
// State: CPU's 23 augmented values, stop loss, substeps, trials, stop events, error.
// Error: 1 reverse, 2 cumulative work, 3 pack bounds, 4 time resolution,
//        5 nonfinite, 6 shaft mismatch, 7 watchdog work, 8 unsupported input.
double electrical_power(const double *a,const double *torque,const double *omega,
                         double scale,double *wheel_power) {
    double bus=0, wheel=0;
    for(int i=0;i<4;i++) {
        const double t=scale*torque[i];
        const double mt=t>=0 ? t/(a[0]*a[1]) : t*a[1]/a[0];
        const double current=mt/a[4];
        const double mechanical=mt*a[0]*omega[i];
        double dc=(mechanical>=0 ? mechanical/a[2] : mechanical*a[2]);
        dc+=current*current*a[10];
        bus+=(dc>=0 ? dc/a[3] : dc*a[3]);
        wheel+=t*omega[i];
    }
    *wheel_power=wheel;
    return bus;
}

int actuation_one(const double *p,const double *state,double horizon,
                   double *torques,double *pack_power,double *wheel_power,double *loss) {
    const double *a=p+60;
    if(state[14]<0 || state[14]>a[12])return 3;
    double requested[4],omega[4],available[4],limited[4];
    for(int i=0;i<4;i++) {
        requested[i]=state[10+i]; omega[i]=state[6+i];available[i]=p[80+i];
        if(omega[i]<0)return 1;
    }
    const int topology=(int)p[79];
    if(topology!=1 && (requested[0]!=0 || requested[1]!=0))return 8;
    if(topology>=2) {
        if(requested[2]!=requested[3])return 8;
        if(topology==3 && omega[2]!=omega[3])return 6;
        requested[2]=requested[2]+requested[3];requested[3]=0;
        omega[2]=omega[2]/2+omega[3]/2;omega[0]=omega[1]=omega[3]=0;
        available[2]=available[2] && available[3];available[0]=available[1]=available[3]=0;
    }
    const double current_torque=fmin(a[5],a[6])*a[4];
    for(int i=0;i<4;i++) {
        const double speed=a[0]*omega[i],request=requested[i];
        double motor_cap=fmin(a[7],current_torque);
        if(speed>a[8])motor_cap=fmin(motor_cap,a[7]*a[8]/speed);
        if(speed>=a[9] || !available[i])motor_cap=0;
        double cap=motor_cap*a[0]*(request>=0 ? a[1] : 1/a[1]);
        if(request<0) {
            const double current_cap=a[10]!=0 ? speed*a[4]*a[2]/(2*a[10]) : INFINITY;
            cap=fmin(cap,current_cap*a[4]*a[0]/a[1]);
            if(omega[i]==0)cap=0;
        }
        limited[i]=fmin(fabs(request),cap)*(request<0 ? -1 : 1);
    }
    const double upper=fmin(fmin(a[15],a[11]*a[13]),state[14]/horizon);
    const double lower=-fmin(fmin(a[16],a[11]*a[14]),(a[12]-state[14])/horizon);
    double work,power=electrical_power(a,limited,omega,1,&work),scale=1;
    if(!(lower<=power && power<=upper)) {
        double lo=0,hi=1;
        for(int i=0;i<60;i++) {
            const double mid=(lo+hi)/2;
            const double candidate=electrical_power(a,limited,omega,mid,&work);
            if(lower<=candidate && candidate<=upper)lo=mid;else hi=mid;
        }
        scale=lo;
    }
    // Match CPU's multiply-then-evaluate sequence after common scaling.
    for(int i=0;i<4;i++)limited[i]*=scale;
    power=electrical_power(a,limited,omega,1,&work);
    for(int i=0;i<4;i++)torques[i]=limited[i];
    if(topology>=2)torques[2]=torques[3]=limited[2]/2;
    *pack_power=power;*wheel_power=work;*loss=power-work;
    for(int i=0;i<4;i++)if(!isfinite(torques[i]))return 5;
    return isfinite(power) && isfinite(work) && isfinite(*loss) ? 0 : 5;
}

int powered_rate(const double *parameters,const double *state,double horizon,double *rate) {
    double p[60],force[89],torque[4],power,work,loss;
    int error=actuation_one(parameters,state,horizon,torque,&power,&work,&loss);
    if(error)return error;
    for(int i=0;i<60;i++)p[i]=parameters[i];
    for(int i=0;i<10;i++)p[7+i]=state[i];
    for(int i=0;i<4;i++)p[21+i]=torque[i];
    planar_one(p,force);
    for(int i=0;i<10;i++)rate[i]=force[i];
    if((int)parameters[79]==3) {
        const double inertia=p[2];
        double left=inertia*rate[8],right=inertia*rate[9],shaft=left+right;
        if(state[8]==0) {
            const double unbraked_left=torque[2]-p[35]*force[64];
            const double unbraked_right=torque[3]-p[36]*force[79];
            const double capacity=p[27]+p[28];
            const double total=unbraked_left+unbraked_right;
            const double applied=-fmax(-capacity,fmin(capacity,total));
            shaft=total+applied;
        }
        rate[8]=rate[9]=shaft/(2*inertia);
    }
    const double *a=parameters+60;
    const double slew=a[18]/((int)parameters[79]>=2 ? 2 : 1);
    for(int i=0;i<4;i++)rate[10+i]=fmax(-slew,fmin(slew,(parameters[21+i]-state[10+i])/a[17]));
    rate[14]=-power;rate[15]=work;rate[16]=loss;
    rate[17]=force[26];rate[18]=force[18];rate[19]=force[19];
    rate[20]=parameters[86];
    rate[21]=force[36]+force[51]+force[66]+force[81];
    rate[22]=fabs(parameters[86]-rate[21]);
    for(int i=0;i<23;i++)if(!isfinite(rate[i]))return 5;
    return 0;
}

// Return -1 for a rejected friction-brake trial, positive for a hard failure.
int check_trial_wheels(const double *p,const double *state) {
    for(int i=0;i<4;i++)if(state[6+i]<0) {
        if(p[25+i]>0 || ((int)p[79]==3 && i>=2 && (p[27]>0 || p[28]>0)))return -1;
        return 1;
    }
    return 0;
}

int rk_trial(const double *p,const double *state,double h,double *final) {
    double k1[23],k2[23],k3[23],k4[23],shift[23];
    int error=check_trial_wheels(p,state);
    if(error)return error;
    error=powered_rate(p,state,h,k1);if(error)return error;
    for(int i=0;i<23;i++)shift[i]=state[i]+h/2*k1[i];
    error=check_trial_wheels(p,shift);if(error)return error;
    error=powered_rate(p,shift,h,k2);if(error)return error;
    for(int i=0;i<23;i++)shift[i]=state[i]+h/2*k2[i];
    error=check_trial_wheels(p,shift);if(error)return error;
    error=powered_rate(p,shift,h,k3);if(error)return error;
    for(int i=0;i<23;i++)shift[i]=state[i]+h*k3[i];
    error=check_trial_wheels(p,shift);if(error)return error;
    error=powered_rate(p,shift,h,k4);if(error)return error;
    for(int i=0;i<23;i++)final[i]=state[i]+h/6*(k1[i]+2*k2[i]+2*k3[i]+k4[i]);
    return check_trial_wheels(p,final);
}

__kernel void powered_interval(__global const double *parameters,
                                __global double *states,const uint lanes) {
    const uint lane=get_global_id(0);if(lane>=lanes)return;
    __global double *saved=states+lane*STATE;
    if(parameters[lane*PARAMS+88]==0)return;
    if(saved[27]!=0)return; // Faulted lane requires explicit reset, never stale success.
    double p[PARAMS],state[STATE],rate[23],candidate[23];
    for(int i=0;i<PARAMS;i++)p[i]=parameters[lane*PARAMS+i];
    for(int i=0;i<STATE;i++)state[i]=saved[i];
    const double step_limit=fmin(p[87],p[77]/4);
    const double required=ceil(p[84]/step_limit);
    // Validate in the floating domain BEFORE integer conversion. Casting an
    // out-of-range count is undefined and must never skip as a valid interval.
    if(!isfinite(step_limit) || step_limit<=0 || !isfinite(required) || required<1 || required>50000) {
        saved[27]=2;return;
    }
    const int count=(int)required;
    int error=0,launch_trials=0;
    const double h=p[84]/count;
    for(int step=0;step<count && !error;step++) {
        double remaining=h;
        while(remaining>0 && !error) {
            error=powered_rate(p,state,remaining,rate);if(error)break;
            int stops[4],stop_count=0;
            for(int i=0;i<4;i++)stops[i]=(state[6+i]>0 && state[6+i]<=1e-9 && p[25+i]>0 && rate[6+i]<0);
            if((int)p[79]==3 && (stops[2] || stops[3]))stops[2]=stops[3]=1;
            double stop_square=0;
            for(int i=0;i<4;i++)if(stops[i]){stop_square+=state[6+i]*state[6+i];state[6+i]=0;stop_count++;}
            if(stop_count) {
                state[23]+=.5*p[2]*stop_square;state[26]+=stop_count;
                if(state[25]+state[26]>p[85])error=2;
                continue;
            }
            double trial_h=remaining;
            for(int i=0;i<4;i++)if(state[6+i]>0 && p[25+i]>0 && rate[6+i]<0)
                trial_h=fmin(trial_h,.25*state[6+i]/-rate[6+i]);
            while(!error) {
                state[25]++;launch_trials++;
                if(state[25]+state[26]>p[85]){error=2;break;}
                if(launch_trials>MAX_LAUNCH_TRIALS){error=7;break;}
                const int trial=rk_trial(p,state,trial_h,candidate);
                if(trial==-1) {
                    trial_h/=2;
                    if(remaining-trial_h==remaining)error=4;
                    continue;
                }
                if(trial){error=trial;break;}
                break;
            }
            if(error)break;
            for(int i=0;i<23;i++)state[i]=candidate[i];
            state[24]++;remaining-=trial_h;
            if(state[14]<0 || state[14]>p[72])error=3;
        }
    }
    for(int i=0;i<27 && !error;i++)if(!isfinite(state[i]))error=5;
    // Failed interval never publishes an accepted partial physical state.
    if(!error)for(int i=0;i<27;i++)saved[i]=state[i];
    saved[27]=error;
}
"""
