/* kprefix.h -- THE VOICE KERNELS' NAMES, PREFIXED, so that each build of
 * synthkernel.c (a variant at a rate: blockrender's libsynth*_<rate>.so) and
 * convolver.c can be linked into libnative side by side, no dlopen (iOS
 * loads no code of its own at run time). Forced in before the source
 * (-include) with NVK_TAG set to the build's tag (damp_48000); renames, and
 * nothing else, so the code is the library's to the bit. kernels.cpp is the
 * table that finds them by the library's name. A new global function in the
 * kernel must be added here AND to kernels.cpp's list. */
#ifndef NVK_TAG
#error "kprefix.h: NVK_TAG (the build's tag) not set"
#endif
#define NVK_CAT2(a, b, c) a##b##_##c
#define NVK_CAT(a, b, c) NVK_CAT2(a, b, c)
#define NVK(s) NVK_CAT(nvk_, NVK_TAG, s)

#define synth_voice NVK(synth_voice)
#define synth_voice_xdec NVK(synth_voice_xdec)
#define synth_voice_damp NVK(synth_voice_damp)
#define synth_voice_moogx NVK(synth_voice_moogx)
#define synth_voice_lobe NVK(synth_voice_lobe)
#define cone_table_set NVK(cone_table_set)
#define synth_organ NVK(synth_organ)
#define moog_coeff_rows NVK(moog_coeff_rows)
#define moog_pitch_cells NVK(moog_pitch_cells)
#define moog_shape_rows NVK(moog_shape_rows)
#define voice_block NVK(voice_block)
#define voice_damp_set NVK(voice_damp_set)
#define voice_moogx_set NVK(voice_moogx_set)
#define voice_pack NVK(voice_pack)
#define voice_samples NVK(voice_samples)
#define voice_sizes NVK(voice_sizes)
#define voice_team_set NVK(voice_team_set)
#define conv_new NVK(conv_new)
#define conv_process NVK(conv_process)
#define conv_reset NVK(conv_reset)
#define conv_free NVK(conv_free)
