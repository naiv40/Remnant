/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — FluCoMa Engine                                                    ║
║  Analisi spettrale in tempo reale del mix orchestra                          ║
║                                                                              ║
║  Avvia DOPO remnant_sc.scd (richiede ~r_mixBus e ~r_flucoUpdate)            ║
║                                                                              ║
║  Flusso:                                                                     ║
║    Mix mono 16ch → FluidLoudness + FluidSpectralShape                       ║
║    → tensione normalizzata (0→1)                                             ║
║    → ~r_flucoUpdate.(tension)  ogni ~100ms                                  ║
║    → OSC /remnant/fluco [tension]  (fallback se SC separato)                ║
║                                                                              ║
║  Tensione finale in remnant_sc.scd:                                          ║
║    clip(gestTension + flucoTension * 0.4, 0, 1)                             ║
║    FluCoMa contribuisce max 0.4 — non sovrascrive la regia                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/

(
// ── Verifica che remnant_sc sia già avviato ────────────────────────────────
if(~r_mixBus.isNil) {
    "ERRORE: avvia prima remnant_sc.scd".postln;
} {

// ── Parametri analisi ──────────────────────────────────────────────────────
~fc_hopSize     = 512;    // campioni tra analisi successive (~10ms a 48kHz)
~fc_loudSmooth  = 3.0;    // secondi di smoothing loudness (risposta lenta = marea)
~fc_centSmooth  = 2.0;    // secondi di smoothing centroide
~fc_loudMin     = -60.0;  // dB: silenzio → tensione 0
~fc_loudMax     = -6.0;   // dB: fortissimo → tensione 1
~fc_centMin     = 300.0;  // Hz: spettro scuro
~fc_centMax     = 5000.0; // Hz: spettro brillante
~fc_centWeight  = 0.3;    // peso centroide nella tensione finale (loudness = 0.7)
~fc_sendOSC     = false;  // true se vuoi anche il messaggio OSC (debug)

// ── Bus per i descriptor ───────────────────────────────────────────────────
~fc_loudBus  = Bus.control(s, 1);  // loudness normalizzata 0→1
~fc_centBus  = Bus.control(s, 1);  // centroide normalizzato 0→1
~fc_tensBus  = Bus.control(s, 1);  // tensione FluCoMa risultante 0→1

// ── SynthDef analisi ───────────────────────────────────────────────────────
SynthDef(\fc_analyze, {
    |inBus=0, loudBus=0, centBus=0, tensBus=0,
     loudMin= -60, loudMax= -6,
     centMin=300,  centMax=5000,
     centWeight=0.3,
     loudSmooth=3.0, centSmooth=2.0|

    var sig, loud, cent, loudNorm, centNorm, tension;

    sig = In.ar(inBus, 1);

    // FluidLoudness: [loudness dBFS, true peak dBFS]
    loud = FluidLoudness.kr(sig, hopSize: ~fc_hopSize)[0];

    // FluidSpectralShape: [centroid, spread, skewness, kurtosis, rolloff, flatness, crest]
    cent = FluidSpectralShape.kr(sig, hopSize: ~fc_hopSize)[0];

    // Normalizzazione con smoothing lento (Lag = risposta a marea, non a impulso)
    loudNorm = Lag.kr(
        LinLin.kr(loud, loudMin, loudMax, 0, 1).clip(0, 1),
        loudSmooth);
    centNorm = Lag.kr(
        LinLin.kr(cent, centMin, centMax, 0, 1).clip(0, 1),
        centSmooth);

    // Tensione = loudness (70%) + centroide (30%)
    tension = ((loudNorm * (1 - centWeight)) + (centNorm * centWeight)).clip(0, 1);

    Out.kr(loudBus, loudNorm);
    Out.kr(centBus, centNorm);
    Out.kr(tensBus, tension);
}).add;

// ── Avvia analisi ─────────────────────────────────────────────────────────
s.sync;

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

// ── Polling → aggiorna tensione in remnant_sc ogni ~100ms ─────────────────
~fc_routine = Routine({
    var tension, loud, cent;
    loop {
        0.1.wait;
        tension = ~fc_tensBus.getSynchronous;
        loud    = ~fc_loudBus.getSynchronous;
        cent    = ~fc_centBus.getSynchronous;

        // Aggiorna remnant_sc direttamente (stesso processo SC)
        ~r_flucoUpdate.(tension);

        // Debug post ogni 5 secondi
        if((thisThread.seconds % 5.0) < 0.12) {
            ["FluCoMa  loud=" ++ loud.round(0.01),
             "cent=" ++ cent.round(0.01),
             "→ tension=" ++ tension.round(0.01)].join("  ").postln;
        };

        // OSC opzionale per debug esterno
        if(~fc_sendOSC) {
            NetAddr("127.0.0.1", 57121).sendMsg('/remnant/fluco', tension);
        };
    };
}).play(AppClock);

"═══════════════════════════════════════".postln;
"FluCoMa attivo.".postln;
"  loud range:  " ++ ~fc_loudMin ++ " → " ++ ~fc_loudMax ++ " dB".postln;
"  cent range:  " ++ ~fc_centMin ++ " → " ++ ~fc_centMax ++ " Hz".postln;
"  peso:        loudness " ++ (1 - ~fc_centWeight) ++ "  centroide " ++ ~fc_centWeight.postln;
"  contributo:  max 0.4 sulla tensione finale".postln;
"".postln;
"Stop: ~fc_routine.stop; ~fc_synth.free".postln;
"═══════════════════════════════════════".postln;

}; // fine if
)
