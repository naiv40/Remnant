/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — FluCoMa Engine  v2                                                ║
║  Real-time spectral analysis of the orchestra mix                            ║
║                                                                              ║
║  Launch AFTER remnant_sc.scd (requires ~r_mixBus and ~r_flucoUpdate)       ║
║                                                                              ║
║  Analysis chain (all from the 16ch mono mix):                               ║
║    FluidLoudness    → loudness  (0→1)                                       ║
║    FluidSpectralShape[0] → centroid  (0→1)  — brightness                   ║
║    FluidSpectralShape[5] → flatness  (0→1)  — noise vs tonal               ║
║    FluidPitch[1]    → pitch confidence (0→1) — how pitched the sound is    ║
║    FluidNoveltySlice (via spectral flux) → onset/flux (0→1)                 ║
║                                                                              ║
║  Composite tension:                                                          ║
║    loudness      × ~fc_wLoud     (energy)                                   ║
║    centroid      × ~fc_wCent     (brightness → timbral abstraction)         ║
║    flatness      × ~fc_wFlat     (noise content → Geräusch territory)       ║
║    (1-confidence)× ~fc_wConf     (unpitched → tension)                      ║
║    flux          × ~fc_wFlux     (activity → Kadenz territory)              ║
║    ──────────────────────────────────────────────────────────────────────   ║
║    weights normalised to sum 1.0 → result always in [0, 1]                 ║
║                                                                              ║
║  Category hint (optional):                                                   ║
║    If the composite features suggest a category strongly (e.g. high         ║
║    flatness + low confidence → Geräusch), the engine posts a hint to        ║
║    the post window. The conductor decides whether to use it.                ║
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
~fc_hopSize    = 512;
~fc_windowSize = 1024;

// Smoothing times (seconds) — longer = less reactive, more structural
~fc_loudSmooth = 3.0;
~fc_centSmooth = 2.0;
~fc_flatSmooth = 1.5;   // flatness reacts faster — noise bursts are significant
~fc_confSmooth = 2.5;
~fc_fluxSmooth = 0.8;   // flux very reactive — onset energy

// Analysis ranges
~fc_loudMin    = -80.0;   ~fc_loudMax  = -20.0;
~fc_centMin    = 300.0;   ~fc_centMax  = 5000.0;
~fc_flatMin    = 0.0;     ~fc_flatMax  = 0.9;   // 0=pure tone, 1=white noise
~fc_confMin    = 0.0;     ~fc_confMax  = 1.0;
~fc_fluxMin    = 0.0;     ~fc_fluxMax  = 1.0;

// Feature weights — must sum to 1.0
// Adjust to shift the engine's sensitivity.
// Current bias: loudness and brightness drive tension most strongly;
//   flatness and unpitchedness add character; flux adds event-level reactivity.
~fc_wLoud = 0.30;   // energy
~fc_wCent = 0.25;   // brightness
~fc_wFlat = 0.20;   // noise content
~fc_wConf = 0.15;   // unpitchedness (1 - confidence)
~fc_wFlux = 0.10;   // spectral flux / onset activity

~fc_sendOSC     = false;
~fc_postHints   = true;    // post category hints to post window

// ── Control buses ──────────────────────────────────────────────────────────
~fc_loudBus  = Bus.control(s, 1);
~fc_centBus  = Bus.control(s, 1);
~fc_flatBus  = Bus.control(s, 1);
~fc_confBus  = Bus.control(s, 1);
~fc_fluxBus  = Bus.control(s, 1);
~fc_tensBus  = Bus.control(s, 1);

// ── SynthDef ───────────────────────────────────────────────────────────────
SynthDef(\fc_analyze, {
    | inBus=0,
      loudBus=0, centBus=0, flatBus=0, confBus=0, fluxBus=0, tensBus=0,
      loudMin= -60, loudMax= -6,
      centMin=300,  centMax=5000,
      flatMin=0.0,  flatMax=0.9,
      confMin=0.0,  confMax=1.0,
      fluxMin=0.0,  fluxMax=1.0,
      wLoud=0.30, wCent=0.25, wFlat=0.20, wConf=0.15, wFlux=0.10,
      loudSmooth=3.0, centSmooth=2.0, flatSmooth=1.5, confSmooth=2.5, fluxSmooth=0.8 |

    var sig, loudRaw, spectral, centRaw, flatRaw, pitchRaw, confRaw,
        loudNorm, centNorm, flatNorm, confNorm, fluxNorm,
        centPrev, fluxRaw, tension;

    sig = In.ar(inBus, 1);

    // ── Loudness ────────────────────────────────────────────────────────
    loudRaw  = FluidLoudness.kr(sig, windowSize: 1024, hopSize: 512)[0];
    loudNorm = Lag.kr(LinLin.kr(loudRaw, loudMin, loudMax, 0, 1).clip(0, 1), loudSmooth);

    // ── Spectral shape (centroid + flatness) ────────────────────────────
    // FluidSpectralShape returns [centroid, spread, skewness, kurtosis, rolloff, flatness, crest]
    spectral = FluidSpectralShape.kr(sig, hopSize: 512);
    centRaw  = spectral[0];   // centroid Hz
    flatRaw  = spectral[5];   // flatness (Wiener entropy): 0=tonal, ~1=white noise

    centNorm = Lag.kr(LinLin.kr(centRaw, centMin, centMax, 0, 1).clip(0, 1), centSmooth);
    flatNorm = Lag.kr(LinLin.kr(flatRaw, flatMin, flatMax, 0, 1).clip(0, 1), flatSmooth);

    // ── Pitch confidence ────────────────────────────────────────────────
    // FluidPitch returns [pitch_Hz, confidence]
    pitchRaw = FluidPitch.kr(sig, hopSize: 512, windowSize: 1024);
    confRaw  = pitchRaw[1];   // 0 = no pitch, 1 = strong pitch
    confNorm = Lag.kr(LinLin.kr(confRaw, confMin, confMax, 0, 1).clip(0, 1), confSmooth);
    // High confidence = pitched = less timbral tension from this axis
    // We invert: (1 - confidence) → unpitchedness → tension contribution

    // ── Spectral flux (approximated as centroid rate of change) ─────────
    // No dedicated FluidFlux yet in all distributions — use a 1-sample
    // delayed centroid delta as a lightweight flux measure.
    centPrev = Delay1.kr(centNorm);
    fluxRaw  = (centNorm - centPrev).abs;
    fluxNorm = Lag.kr(LinLin.kr(fluxRaw, fluxMin, fluxMax, 0, 1).clip(0, 1), fluxSmooth);

    // ── Composite tension ───────────────────────────────────────────────
    tension = (
        (loudNorm          * wLoud) +
        (centNorm          * wCent) +
        (flatNorm          * wFlat) +
        ((1 - confNorm)    * wConf) +   // inverted: unpitchedness → tension
        (fluxNorm          * wFlux)
    ).clip(0, 1);

    Out.kr(loudBus, loudNorm);
    Out.kr(centBus, centNorm);
    Out.kr(flatBus, flatNorm);
    Out.kr(confBus, confNorm);
    Out.kr(fluxBus, fluxNorm);
    Out.kr(tensBus, tension);
}).add;

// ── Launch ─────────────────────────────────────────────────────────────────
Routine({
    s.sync;

    ~fc_synth = Synth(\fc_analyze, [
        \inBus,      ~r_mixBus.index,
        \loudBus,    ~fc_loudBus.index,
        \centBus,    ~fc_centBus.index,
        \flatBus,    ~fc_flatBus.index,
        \confBus,    ~fc_confBus.index,
        \fluxBus,    ~fc_fluxBus.index,
        \tensBus,    ~fc_tensBus.index,
        \loudMin,    ~fc_loudMin,  \loudMax,  ~fc_loudMax,
        \centMin,    ~fc_centMin,  \centMax,  ~fc_centMax,
        \flatMin,    ~fc_flatMin,  \flatMax,  ~fc_flatMax,
        \confMin,    ~fc_confMin,  \confMax,  ~fc_confMax,
        \fluxMin,    ~fc_fluxMin,  \fluxMax,  ~fc_fluxMax,
        \wLoud,      ~fc_wLoud,
        \wCent,      ~fc_wCent,
        \wFlat,      ~fc_wFlat,
        \wConf,      ~fc_wConf,
        \wFlux,      ~fc_wFlux,
        \loudSmooth, ~fc_loudSmooth,
        \centSmooth, ~fc_centSmooth,
        \flatSmooth, ~fc_flatSmooth,
        \confSmooth, ~fc_confSmooth,
        \fluxSmooth, ~fc_fluxSmooth,
    ], target: ~r_gProc);

    // ── Polling routine ────────────────────────────────────────────────────
    ~fc_routine = Routine({
        var tension, loud, cent, flat, conf, flux;
        var hintTimer = 0;
        loop {
            0.1.wait;
            tension = ~fc_tensBus.getSynchronous;
            loud    = ~fc_loudBus.getSynchronous;
            cent    = ~fc_centBus.getSynchronous;
            flat    = ~fc_flatBus.getSynchronous;
            conf    = ~fc_confBus.getSynchronous;
            flux    = ~fc_fluxBus.getSynchronous;

            ~r_flucoUpdate.(tension);

            // ── Diagnostic log every 5s ───────────────────────────────
            if((thisThread.seconds % 5.0) < 0.12) {
                [
                    "FluCoMa",
                    "L="  ++ loud.round(0.01),
                    "C="  ++ cent.round(0.01),
                    "Fl=" ++ flat.round(0.01),
                    "P="  ++ conf.round(0.01),
                    "Fx=" ++ flux.round(0.01),
                    "→ T=" ++ tension.round(0.01),
                ].join("  ").postln;
            };

            // ── Category hint every 8s ────────────────────────────────
            // Posts a suggestion based on dominant features.
            // The conductor is free to ignore it.
            if(~fc_postHints and: { (thisThread.seconds % 8.0) < 0.12 }) {
                var hint = "—";
                // High flatness + low confidence → noise, no pitch → Geräusch
                if((flat > 0.6) and: { conf < 0.3 }) { hint = "→ Geräusch (noise, unpitched)" };
                // High confidence + low centroid + low flatness → sustained tonal → Klang
                if((conf > 0.7) and: { cent < 0.4 } and: { flat < 0.3 }) { hint = "→ Klang (tonal, dark)" };
                // High flux → rhythmic energy → Kadenz
                if(flux > 0.6) { hint = "→ Kadenz (high activity)" };
                // Low loudness + high confidence → faint pitched → Stille
                if((loud < 0.2) and: { conf > 0.5 }) { hint = "→ Stille (quiet, pitched)" };
                // High centroid + mid flatness → bright, complex → Farbklang
                if((cent > 0.65) and: { flat > 0.35 } and: { flat < 0.65 }) { hint = "→ Farbklang (bright, complex)" };
                // All mid values → Textur
                if((loud > 0.3) and: { loud < 0.7 } and: { flat > 0.3 } and: { flat < 0.7 }
                   and: { hint == "—" }) { hint = "→ Textur (dense, mid-range)" };
                if(hint != "—") { ("  FluCoMa hint: " ++ hint).postln };
            };

            if(~fc_sendOSC) {
                NetAddr("127.0.0.1", 57121).sendMsg('/remnant/fluco', tension);
            };
        };
    }).play(AppClock);

    "═══════════════════════════════════════".postln;
    "FluCoMa v2 active.".postln;
    "  features:  loudness  centroid  flatness  pitch_confidence  flux".postln;
    "  weights:   " ++ [~fc_wLoud, ~fc_wCent, ~fc_wFlat, ~fc_wConf, ~fc_wFlux].collect(_.round(0.01)).postln;
    "  contribution: max 0.4 on final tension".postln;
    "".postln;
    "Adjust weights (example):".postln;
    "  ~fc_synth.set(\\wFlat, 0.35, \\wLoud, 0.20)".postln;
    "  // then re-launch FluCoMa to apply".postln;
    "Category hints: ~fc_postHints = false  // silence them".postln;
    "Stop: ~fc_routine.stop; ~fc_synth.free".postln;
    "═══════════════════════════════════════".postln;

}).play(AppClock);

}; // end if
)
