// ssshift: Signalsmith Stretch pitch shift with formants placed relative to the INPUT.
// Interleaved float32 raw in/out, same length, latency removed.
//   ssshift IN OUT channels samplerate pitch_st formant_st [formant_base_hz=0] [tonality_hz=8000]
// formant_st: where the spectral envelope ends up relative to the input (0 = kept).
#include "signalsmith-stretch.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

int main(int argc, char **argv) {
    if (argc < 7) { fprintf(stderr, "usage: ssshift IN OUT ch sr pitch_st formant_st [base_hz] [tonality_hz]\n"); return 2; }
    int ch = atoi(argv[3]); double sr = atof(argv[4]);
    double pitch = atof(argv[5]), formant = atof(argv[6]);
    double base = argc > 7 ? atof(argv[7]) : 0, tonality = argc > 8 ? atof(argv[8]) : 8000;
    FILE *f = fopen(argv[1], "rb"); fseek(f, 0, SEEK_END); long bytes = ftell(f); fseek(f, 0, SEEK_SET);
    size_t n = bytes / sizeof(float) / ch;
    std::vector<float> in(n * ch); fread(in.data(), sizeof(float), n * ch, f); fclose(f);

    signalsmith::stretch::SignalsmithStretch<float> st;
    st.presetDefault(ch, sr);
    st.setTransposeSemitones(pitch, tonality / sr);
    // compensatePitch=true: formants first kept where they were, then moved by `formant`
    st.setFormantSemitones(formant, true);
    st.setFormantBase(base / sr);

    int inLat = st.inputLatency(), outLat = st.outputLatency();
    size_t total = n + inLat + outLat;
    std::vector<std::vector<float>> inb(ch, std::vector<float>(total, 0.f)), outb(ch, std::vector<float>(total, 0.f));
    for (size_t i = 0; i < n; ++i) for (int c = 0; c < ch; ++c) inb[c][i] = in[i * ch + c];
    // process input (zero-padded) and trim the latency from the output start
    st.process(inb, (int)(n + inLat + outLat), outb, (int)(n + inLat + outLat));
    size_t off = inLat + outLat;
    std::vector<float> o(n * ch);
    for (size_t i = 0; i < n; ++i) for (int c = 0; c < ch; ++c) o[i * ch + c] = outb[c][i + off];
    FILE *g = fopen(argv[2], "wb"); fwrite(o.data(), sizeof(float), n * ch, g); fclose(g);
    fprintf(stderr, "latency in %d out %d\n", inLat, outLat);
    return 0;
}
