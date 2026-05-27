/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — FluCoMa Engine                                                    ║
║  Real-time spectral analysis of the orchestra mix                            ║
║                                                                              ║
║  Launch AFTER remnant_sc.scd (requires ~r_mixBus and ~r_flucoUpdate)       ║
║                                                                              ║
║  Flow:                                                                       ║
║    16ch mono mix → FluidLoudness + FluidSpectralShape                       ║
║    → normalised tension (0→1)                                               ║
║    → ~r_flucoUpdate.(tension)  every ~100ms                                 ║
║    → OSC /remnant/fluco [tension]  (fallback if separate SC)                ║
║                                                                              ║
║  Final tension in remnant_sc.scd:                                           ║
║    clip(gestTension + flucoTension * 0.4, 0, 1)                             ║
║    FluCoMa contributes max 0.4 — does not override direction                ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/

(
if(~r_mixBus.isNil) {
    "ERROR: launch remnant_sc.scd first".postln;
} {

// ── Analysis parameters ────────────────────────────────────────────────────
~fc_hopSize     = 512;
~fc_loudSmooth  = 3.0;
~fc_centSmooth  = 2.0;
~fc_loudMin     = -60.0;
~fc_loudMax     = -6.0;
~fc_centMin     = 300.0;
~fc_centMax     = 5000.0;
~fc_centWeight  = 0.3;
~fc_sendOSC     = false;

// ── Control buses ──────────────────────────────────────────────────────────
~fc_loudBus  = Bus.control(s, 1);
~fc_centBus  = Bus.control(s, 1);
~fc_tensBus  = Bus.control(s, 1);

// ── SynthDef ───────────────────────────────────────────────────────────────
SynthDef(\fc_analyze, {
    |inBus=0, loudBus=0, centBus=0, tensBus=0,
     loudMin= -60, loudMax= -6,
     centMin=300,  centMax=5000,
     centWeight=0.3,
     loudSmooth=3.0, centSmooth=2.0|

    var sig, loud, cent, loudNorm, centNorm, tension;

    sig = In.ar(inBus, 1);

    loud = FluidLoudness.kr(sig, hopSize: ~fc_hopSize)[0];
    cent = FluidSpectralShape.kr(sig, hopSize: ~fc_hopSize)[0];

    loudNorm = Lag.kr(
        LinLin.kr(loud, loudMin, loudMax, 0, 1).clip(0, 1),
        loudSmooth);
    centNorm = Lag.kr(
        LinLin.kr(cent, centMin, centMax, 0, 1).clip(0, 1),
        centSmooth);

    tension = ((loudNorm * (1 - centWeight)) + (centNorm * centWeight)).clip(0, 1);

    Out.kr(loudBus, loudNorm);
    Out.kr(centBus, centNorm);
    Out.kr(tensBus, tension);
}).add;

// ── Launch — wrapped in Routine so s.sync works correctly ─────────────────
Routine({
    s.sync;  // wait for SynthDef to be sent to server

    ~fc_synth = Synth(\fc_analyze, [
        \inBus,       ~r_mixBus.index,
        \loudBus,     ~fc_loudBus.index,
        \centBus,     ~fc_centBus.index,
        \tensBus,     ~fc_tensBus.index,
        \loudMin,     ~fc_loudMin,
        \loudMax,     ~fc_loudMax,
        \centMin,     ~fc_centMin,
        \centMax,     ~fc_centMax,
        \centWeight,  ~fc_centWeight,
        \loudSmooth,  ~fc_loudSmooth,
        \centSmooth,  ~fc_centSmooth,
    ], target: ~r_gProc);

    // ── Polling routine → update tension every ~100ms ──────────────────────
    ~fc_routine = Routine({
        var tension, loud, cent;
        loop {
            0.1.wait;
            tension = ~fc_tensBus.getSynchronous;
            loud    = ~fc_loudBus.getSynchronous;
            cent    = ~fc_centBus.getSynchronous;

            ~r_flucoUpdate.(tension);

            if((thisThread.seconds % 5.0) < 0.12) {
                ["FluCoMa  loud=" ++ loud.round(0.01),
                 "cent=" ++ cent.round(0.01),
                 "→ tension=" ++ tension.round(0.01)].join("  ").postln;
            };

            if(~fc_sendOSC) {
                NetAddr("127.0.0.1", 57121).sendMsg('/remnant/fluco', tension);
            };
        };
    }).play(AppClock);

    "═══════════════════════════════════════".postln;
    "FluCoMa active.".postln;
    "  loud range:  " ++ ~fc_loudMin ++ " → " ++ ~fc_loudMax ++ " dB".postln;
    "  cent range:  " ++ ~fc_centMin ++ " → " ++ ~fc_centMax ++ " Hz".postln;
    "  weight:      loudness " ++ (1 - ~fc_centWeight) ++ "  centroid " ++ ~fc_centWeight.postln;
    "  contribution: max 0.4 on final tension".postln;
    "".postln;
    "Stop: ~fc_routine.stop; ~fc_synth.free".postln;
    "═══════════════════════════════════════".postln;

}).play(AppClock);

}; // end if
)
