// The player's audio: five stems in memory, mixed by mode; another tempo is a Rubber Band R3 offline render of every stem.
#ifndef ENGINE_H
#define ENGINE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { STEM_S = 0, STEM_A, STEM_T, STEM_B, STEM_I, STEM_COUNT };
// which voices are heard: a mask of these. All four is the balanced mix, none is the instruments alone.
enum { VOICE_S = 1, VOICE_A = 2, VOICE_T = 4, VOICE_B = 8, VOICES_ALL = 15 };

// paths in stem order; false on a file that can't be read or stems of different rate or length
int engine_load(const char *const *paths, const char *cache_dir);
int engine_start_output(void);
// output devices: count, then each one's Core Audio UID and name. Listing also refreshes what the index means.
int engine_device_count(void);
void engine_device_info(int index, char *uid, char *name, int capacity);
// an empty uid is the system default, which follows the Mac's Sound setting; false if the device can't be opened
int engine_set_device(const char *uid);
void engine_stop_output(void);

void engine_set_playing(int playing);
int engine_is_playing(void);
void engine_set_voices(int voices);
// What the voice files are. Part-predominant (0): a file has its part loudest with the others bleeding through, so voices not
// heard are off and those heard are boosted. Isolated (1): one voice per file, so those heard are at 0 dB and the others at -18 dB.
void engine_set_isolated(int isolated);
// the whole mix, in dB: -3 until set
void engine_set_master_db(double db);
void engine_seek(double source_seconds);
// where the listener is, in seconds of the original audio (output latency taken off while playing)
double engine_position(void);
double engine_duration(void);

// speed 1 = the files themselves. Playback carries on at the old tempo for a moment, then moves over.
void engine_set_speed(double speed);
double engine_speed(void);
// 0..1 while whole renders are running in the background, -1 when idle. Playback doesn't wait for them.
double engine_render_progress(void);
// asked to play, and the audio here isn't rendered yet
int engine_waiting(void);
// starts a render at the playhead if none is near. For when the mixer has gone somewhere by itself, as a loop does.
void engine_render_here(void);
// on reaching end by playing, goes back to start: both in seconds of the original audio. A negative start is no loop.
void engine_set_loop(double start, double end);
// how another tempo is made, for the four voices and for the instruments
enum { METHOD_R3_TOGETHER = 0, METHOD_R3_APART, METHOD_SIGNALSMITH, METHOD_SIGNALSMITH_SHORT, METHOD_PSOLA };
void engine_set_methods(int voices, int instruments);

// The notes to correct, replacing any before: per fix a stem, its span in seconds of the original audio, and either mute
// or semitones. Like a tempo change, playback carries on as it was until the corrected audio is ready.
void engine_set_fixes(int count, const int *stems, const double *starts, const double *ends, const int *mutes, const double *semitones);

// left and right gains per stem for a mask of voices, master included (linear)
void engine_gains(int voices, float gains[STEM_COUNT][2]);
// the mixer the output uses, for tests: renders frames*2 samples and advances the position
void engine_mix(float *out, int frames);
// blocks until no render is running or waiting
void engine_wait_render(void);
int engine_sample_rate(void);

#ifdef __cplusplus
}
#endif
#endif
