#details
network: 2x128
input: 50
output: 3

#legend
v: Velocity[[3]]
R: attitude[[9]]
g_t: positions of inner corners of target gate [[12]]
t_f: target gate unrevealed flag[[1]]
g_n: positions of inner corners of next gate [[12]]
n_f: next gate unrevealed flag[[1]]
poles: 4 poles' x,y, unrevealed flag [[12]]

c: mass normalized thrust 
roll, pitch: attitude setpoints

input vector: [[v, R, g_t, t_f, g_n, n_f, poles]]

output vector: [[c, roll, pitch]]

action mapping (network output a in [-1, 1]^3, a = 0 is near hover):
c = 9.81 + 9.0 * a_c, linear, past the range [1.97, 18.4] m/s^2 (env thrust 0.085-0.8 N / 0.0434 kg)
  a_c = 0 is hover at the nominal mass
  the ends are clipped: max thrust at a_c ~ 0.96 (tanh never outputs exactly 1), min thrust at a_c ~ -0.87
  checkpoints store c_offset / c_scale; runs before this change used 10.19 + 8.6 * a_c
thrust [N] = c * 0.0434 (nominal mass)
roll, pitch = pi/2 * a (full env range, needed to lead setpoints)
yaw = 0 (fixed)
env action: [roll, pitch, 0, thrust]


