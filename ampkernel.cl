// THE VALVE AMP'S INPUT ON THE GPU (tubeamp._synth): sum A cos(w n + P) over a
// segment's partials, factored so the GPU does no trig at all. With the sample
// n = J*(NL*h + l) + j, a partial's phasor is a product of three tables,
//     A e^{i(P + w J NL h)} . e^{i w J l} . e^{i w j}
// each made in double by the host (the Iris has no fp64) and rounded once to
// float: about 140 dB under the sum, where the valve's products are 60-90 dB
// down. The host's trig is then (H + NL + J) values a partial, not one a block.
// One work-item a sample; the sum is the real part.
__kernel void amp_sum(const int K, const int J, const int NL,
                      __global const float2* H, __global const float2* L,
                      __global const float2* W, __global float* x)
{
    int j = get_global_id(0), b = get_global_id(1);
    __global const float2* hh = H + (long)(b/NL)*K;
    __global const float2* ll = L + (long)(b%NL)*K;
    float s = 0.f;
    for(int k=0; k<K; k++){
        float2 u = hh[k], v = ll[k], w = W[k*J+j];
        float2 e = (float2)(u.x*v.x - u.y*v.y, u.x*v.y + u.y*v.x);
        s += e.x*w.x - e.y*w.y;
    }
    x[(long)b*J+j] = s;
}
