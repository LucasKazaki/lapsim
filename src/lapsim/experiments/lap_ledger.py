"""Bounded seam-time/energy accounting; never resets or advances physical state."""
from math import isfinite


class LapLedger:
    def __init__(self,length_m,capacity_j,laps,initial_energy_j):
        if type(laps) is not int or laps not in (1,10):
            raise ValueError('Choose a one-lap diagnostic or ten-lap competition')
        if any(type(v) not in (int,float) or not isfinite(v) or v<=0 for v in (length_m,capacity_j)):
            raise ValueError('Positive finite course length and capacity required')
        if type(initial_energy_j) not in (int,float) or not 0<=initial_energy_j<=capacity_j:
            raise ValueError('Initial energy outside capacity')
        self.length_m,self.capacity_j,self.target_laps=length_m,capacity_j,laps
        self.previous=(0.,0.,initial_energy_j)
        self.boundary_time=0.;self.boundary_energy=initial_energy_j
        self.rows=[]

    def observe(self,time_s,progress_m,energy_j):
        if any(type(v) not in (int,float) or not isfinite(v) for v in (time_s,progress_m,energy_j)):
            raise ValueError('Finite time/progress/energy required')
        before_t,before_p,before_e=self.previous
        if time_s<before_t or not 0<=energy_j<=self.capacity_j:
            raise ValueError('Reversed time or out-of-bounds pack energy')
        added=[]
        while len(self.rows)<self.target_laps and progress_m>=(len(self.rows)+1)*self.length_m:
            boundary=(len(self.rows)+1)*self.length_m
            if progress_m<=before_p or before_p>=boundary:
                raise ValueError('Ambiguous lap crossing; ordered local progress required')
            fraction=(boundary-before_p)/(progress_m-before_p)
            finish=before_t+fraction*(time_s-before_t)
            energy=before_e+fraction*(energy_j-before_e)
            row={'lap':len(self.rows)+1,'finish_time_s':finish,'lap_time_s':finish-self.boundary_time,
                 'pack_energy_before_j':self.boundary_energy,'pack_energy_after_j':energy,
                 'net_energy_kwh':(self.boundary_energy-energy)/3_600_000,
                 'soc_after':energy/self.capacity_j,'crossing_interval_s':time_s-before_t,
                 'crossing_method':'linear interpolation between adjacent 10 ms plant boundaries; physical state is not interpolated/reset'}
            self.rows.append(row);added.append(row)
            self.boundary_time,self.boundary_energy=finish,energy
        self.previous=(time_s,progress_m,energy_j)
        return added

    def summary(self,time_s,progress_m,energy_j):
        return {'target_laps':self.target_laps,'completed_laps':len(self.rows),'laps':self.rows,
                'unfinished_lap':None if len(self.rows)==self.target_laps else len(self.rows)+1,
                'partial_lap_progress_m':max(0.,progress_m-len(self.rows)*self.length_m),
                'partial_lap_elapsed_s':max(0.,time_s-self.boundary_time),
                'partial_lap_net_energy_kwh':(self.boundary_energy-energy_j)/3_600_000,
                'thermal_model':'No integrated thermal state; static scenario temperature only'}
