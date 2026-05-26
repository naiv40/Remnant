/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — SuperCollider Engine                                              ║
║  Elaborazione timbrica in tempo reale per orchestra amplificata              ║
║                                                                              ║
║  AVVIO: esegui il blocco 0 — carica tutto automaticamente                   ║
║                                                                              ║
║  OSC in ingresso (porta 57121):                                              ║
║    /remnant/gesture   [idx, category, tension, azimuth]                      ║
║      → cambia categoria + parametri su tutti i synth (click regia)          ║
║    /remnant/update    [idx, instr, azimuth, tension]                         ║
║      → aggiorna parametri di un singolo strumento                            ║
║    /remnant/param     [key, value]                                           ║
║      → masterVol, bpm                                                        ║
║    /remnant/panic                                                             ║
║      → reset a Neutro, tensione 0.3                                          ║
║                                                                              ║
║  FluCoMa (remnant_flucos.scd):                                               ║
║    Analizza mix mono orchestra → modula ~r_flucoTension (0→1)               ║
║    La tensione finale = clip(gestTension + flucoTension * 0.4, 0, 1)        ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/

// ─────────────────────────────────────────────────────────────────────────────
// 0. BOOT + AVVIO COMPLETO
// ─────────────────────────────────────────────────────────────────────────────

(
// Path relativo allo script — funziona su qualsiasi computer
~r_dir = thisProcess.nowExecutingPath.dirname ++ "/";

s.options.inDevice             = "BlackHole 16ch";
s.options.outDevice            = "Built-in Output";
s.options.numInputBusChannels  = 16;
s.options.numOutputBusChannels = 2;
s.options.memSize              = 65536;
s.options.numBuffers           = 2048;
s.options.blockSize            = 512;
s.options.sampleRate           = 48000;
s.options.numWireBufs          = 256;
s.options.maxNodes             = 1024;

s.waitForBoot({

    // ── 1. Gruppi ─────────────────────────────────────────────────────────
    ~r_gIn   = Group.new;
    ~r_gProc = Group.after(~r_gIn);
    ~r_gSpat = Group.after(~r_gProc);
    "1. Gruppi OK".postln;

    // ── 2. Bus interni per categoria ──────────────────────────────────────
    ~r_bus = Dictionary[
        "Klang"     -> Bus.audio(s, 2),
        "Farbklang" -> Bus.audio(s, 2),
        "Gerausch"  -> Bus.audio(s, 2),
        "Geräusch"  -> Bus.audio(s, 2),
        "Kadenz"    -> Bus.audio(s, 2),
        "Textur"    -> Bus.audio(s, 2),
        "Stille"    -> Bus.audio(s, 2),
        "Neutro"    -> Bus.audio(s, 2),
    ];
    // Bus mix mono per FluCoMa (somma di tutti i canali in ingresso)
    ~r_mixBus = Bus.audio(s, 1);
    "2. Bus OK".postln;

    // ── 3. Mappa strumento → canale ADC ───────────────────────────────────
    ~r_instrBus = Dictionary[
        "violin"         -> 0,
        "viola"          -> 1,
        "violoncello"    -> 2,
        "double bass"    -> 3,
        "flute"          -> 4,
        "oboe"           -> 5,
        "bb clarinet"    -> 6,
        "bassoon"        -> 7,
        "horn in f"      -> 8,
        "trumpet in c"   -> 9,
        "tenor trombone" -> 10,
        "bass tuba"      -> 11,
        "piano"          -> 12,
        "harp"           -> 13,
        "vibraphone"     -> 14,
        "marimbaphone"   -> 15,
    ];
    "3. Mappa strumenti OK".postln;

    // ── 4. SynthDef ───────────────────────────────────────────────────────
    //
    // Grammatica di Lerdahl:
    //   tension (0→1) = forza di tensione timbrica (gesto + FluCoMa)
    //   azimuth (0→360) = posizione spaziale → pan stereo
    //
    //   Klang     → stabilità, riverbero lungo
    //   Farbklang → colore timbrico, detuning lento
    //   Textur    → trama, freeze progressivo
    //   Kadenz    → impulso ritmico, delay sincopato
    //   Geräusch  → rumore fisico, saturazione + granulare
    //   Stille    → silenzio attivo, gate + coda infinita
    //   Neutro    → passthrough, EQ leggero

    // Mix mono per FluCoMa — somma pesata dei 16 canali ADC
    SynthDef(\r_mix, { |outBus=0|
        var sig = Mix.ar(SoundIn.ar((0..15))) / 16.0;
        Out.ar(outBus, sig);
    }).add;

    // Input live per strumento — legge da ADC, scrive sul bus proc
    SynthDef(\r_input, { |adcBus=0, amp=1.0, outBus=0|
        var sig = SoundIn.ar(adcBus) * amp;
        Out.ar(outBus, sig);
    }).add;

    // Spazializzatore stereo con pan reale dall'azimuth
    SynthDef(\r_spatialize, { |inBus=0, outBase=0, amp=0.8, azimuth=180|
        var sig, gainL, gainR, az_rad;
        sig    = In.ar(inBus, 2).sum;
        az_rad = (azimuth / 360.0) * 2pi;
        gainR  = ((az_rad.sin + 1) * 0.5).clip(0, 1);
        gainL  = 1.0 - gainR;
        sig    = Limiter.ar(sig * amp, 0.95);
        Out.ar(outBase, [sig * gainL, sig * gainR]);
    }).add;

    // ── KLANG ─────────────────────────────────────────────────────────────
    // Stabilità. Riverbero lungo e trasparente.
    // tension bassa → decay 8s, mix 15%, shimmer assente
    // tension alta  → decay 1s, mix 55%, shimmer armonico leggero
    SynthDef(\r_klang, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, rev, shimmer, wet, decayT, mix;
        dry    = In.ar(inBus);
        decayT = Lag.kr(LinExp.kr(tension, 0, 1, 8.0, 1.0), 1.0);
        mix    = Lag.kr(LinLin.kr(tension, 0, 1, 0.15, 0.55), 0.3);
        rev    = GVerb.ar(dry, roomsize: 40,
                    revtime: decayT,
                    damping: Lag.kr(LinLin.kr(tension, 0, 1, 0.1, 0.6), 0.5),
                    inputbw: 0.9, spread: 15,
                    drylevel: 0, earlyreflevel: 0.4, taillevel: 0.6,
                    maxroomsize: 50);
        shimmer = PitchShift.ar(dry, 0.2, 2.0, 0.0, 0.001)
                  * Lag.kr(tension * 0.12, 0.5);
        wet = (dry * (1 - mix)) + (rev * mix) + shimmer;
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── FARBKLANG ─────────────────────────────────────────────────────────
    // Colore timbrico. Tre layer detuned con modulazione di fase lenta.
    // tension bassa → detuning impercettibile, rate 0.05Hz
    // tension alta  → semitono abbondante, rate 0.8Hz, coda più corta
    SynthDef(\r_farbklang, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, layers, modRate, detune, wet;
        dry     = In.ar(inBus);
        modRate = Lag.kr(LinExp.kr(tension, 0, 1, 0.05, 0.8), 0.8);
        detune  = Lag.kr(LinLin.kr(tension, 0, 1, 0.998, 1.035), 0.6);
        layers  = [
            PitchShift.ar(dry, 0.15, detune,
                SinOsc.kr(modRate * 0.7).range(0, tension * 0.015), 0.003),
            PitchShift.ar(dry, 0.15, 1.0 / detune,
                SinOsc.kr(modRate * 1.3).range(0, tension * 0.015), 0.003),
            PitchShift.ar(dry, 0.15, 1.0 + ((detune - 1.0) * 0.5),
                SinOsc.kr(modRate).range(0, tension * 0.01), 0.002),
        ];
        wet = (dry * 0.35) + (layers[0] * 0.28) + (layers[1] * 0.22) + (layers[2] * 0.15);
        wet = GVerb.ar(wet, 25,
            Lag.kr(LinExp.kr(tension, 0, 1, 2.0, 0.4), 0.5),
            0.4, 0.5, 15, 0.5, 0.3, 0.4, 30);
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── GERÄUSCH ──────────────────────────────────────────────────────────
    // Gesto fisico. Saturazione tanh + granulare.
    // tension bassa → drive 1x, grain 300ms
    // tension alta  → drive 18x, grain 15ms, noise layer
    SynthDef(\r_gerausch, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, sat, gran, noise, wet, granSize, scatter;
        dry      = In.ar(inBus);
        sat      = (dry * Lag.kr(LinExp.kr(tension, 0, 1, 1.0, 18.0), 0.2)).tanh;
        granSize = Lag.kr(LinExp.kr(tension, 0, 1, 0.3, 0.015), 0.3);
        scatter  = Lag.kr(tension * 0.4, 0.2);
        gran     = PitchShift.ar(sat, granSize,
                       Lag.kr(LinExp.kr(azimuth, 0, 360, 0.7, 1.4), 0.5),
                       scatter, scatter * 0.5);
        noise    = HPF.ar(BPF.ar(WhiteNoise.ar, 1200, 1.5), 400)
                   * Lag.kr(LinLin.kr(tension, 0.4, 1, 0, 0.18).max(0), 0.2);
        wet      = HPF.ar((gran * 0.55) + (sat * 0.25) + (noise * 0.20), 80);
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── KADENZ ────────────────────────────────────────────────────────────
    // Impulso ritmico. Delay sincopato.
    // tension bassa → delay 1.5s, feedback basso, transienti lievi
    // tension alta  → delay 70ms, feedback alto, attacchi accentuati
    SynthDef(\r_kadenz, { |inBus=0, outBus=0, azimuth=180, tension=0.5, bpm=60|
        var dry, transient, delayed, wet, delTime, feedback;
        dry       = In.ar(inBus);
        transient = dry + (HPF.ar(dry, 600) * Lag.kr(LinLin.kr(tension, 0, 1, 0.5, 3.5), 0.15));
        delTime   = Lag.kr(LinExp.kr(tension, 0, 1, 1.5, 0.07), 0.4);
        feedback  = Lag.kr(LinLin.kr(tension, 0, 1, 0.15, 0.72), 0.3);
        delayed   = CombL.ar(transient, 2.0, delTime, feedback * 3.5);
        wet       = Limiter.ar(
                        (transient * Lag.kr(LinLin.kr(tension, 0, 1, 0.9, 0.5), 0.2))
                      + (delayed   * Lag.kr(LinLin.kr(tension, 0, 1, 0.2, 0.65), 0.2)),
                        0.92);
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── TEXTUR ────────────────────────────────────────────────────────────
    // Trama continua. Freeze progressivo + shimmer spettrale.
    // tension bassa → revtime 1.5s, niente freeze
    // tension alta  → revtime 35s (freeze percettivo), shimmer doppio
    SynthDef(\r_textur, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, frozen, shimmerA, shimmerB, wet, freezeAmt, revTime;
        dry       = In.ar(inBus);
        freezeAmt = Lag.kr(tension.squared, 1.2);
        revTime   = Lag.kr(LinExp.kr(tension, 0, 1, 1.5, 35.0), 1.5);
        frozen    = GVerb.ar(dry, roomsize: 60, revtime: revTime,
                        damping: Lag.kr(1.0 - (tension * 0.8), 0.5),
                        inputbw: 0.95, spread: 15,
                        drylevel: 1 - freezeAmt,
                        earlyreflevel: 0.0,
                        taillevel: freezeAmt * 0.95,
                        maxroomsize: 80);
        shimmerA  = PitchShift.ar(frozen, 0.4, 2.0, 0.005, 0.005)
                    * Lag.kr(tension * 0.3, 0.8);
        shimmerB  = PitchShift.ar(frozen, 0.6, 1.5, 0.008, 0.008)
                    * Lag.kr(tension * 0.18, 0.8);
        wet       = LeakDC.ar(frozen + shimmerA + shimmerB);
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── STILLE ────────────────────────────────────────────────────────────
    // Silenzio attivo. Gate morbido + coda lunga.
    // tension bassa → gate quasi chiuso, LPF 400Hz, reverb 6s
    // tension alta  → gate si apre, LPF 3500Hz, reverb 30s (trattenuto imminente)
    SynthDef(\r_stille, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, env, gated, tail, wet, gateAttack, gateRelease, gateThresh;
        dry         = In.ar(inBus);
        gateThresh  = Lag.kr(LinLin.kr(tension, 0, 1, -72, -30).dbamp, 1.0);
        gateAttack  = Lag.kr(LinExp.kr(tension, 0, 1, 2.0, 0.1), 0.5);
        gateRelease = Lag.kr(LinExp.kr(tension, 0, 1, 8.0, 0.8), 0.5);
        env         = Lag.ar(
                          (Amplitude.ar(dry, gateAttack, gateRelease) > gateThresh).asFloat,
                          gateRelease);
        gated       = dry * env;
        tail        = GVerb.ar(gated, roomsize: 50,
                          revtime: Lag.kr(LinExp.kr(tension, 0, 1, 6.0, 30.0), 2.0),
                          damping: 0.05, inputbw: 0.98, spread: 15,
                          drylevel: 0, earlyreflevel: 0.1, taillevel: 0.7,
                          maxroomsize: 60);
        wet         = LPF.ar(gated + (tail * 0.6),
                          Lag.kr(LinExp.kr(tension, 0, 1, 400, 3500), 1.0));
        Out.ar(outBus, wet ! 2);
    }).add;

    // ── NEUTRO ────────────────────────────────────────────────────────────
    // Passthrough. EQ parametrico leggero come unico segno.
    SynthDef(\r_neutro, { |inBus=0, outBus=0, azimuth=180, tension=0.5|
        var dry, wet;
        dry = In.ar(inBus);
        wet = BPeakEQ.ar(dry,
                  Lag.kr(LinExp.kr(tension, 0, 1, 500, 2500), 0.5),
                  0.7,
                  Lag.kr(LinLin.kr(tension, 0, 1, 0, 4).ampdb, 0.3));
        Out.ar(outBus, LeakDC.ar(wet) ! 2);
    }).add;

    "4. SynthDef OK".postln;

    // ── 5. Mappa categoria → SynthDef ─────────────────────────────────────
    ~r_catSynth = Dictionary[
        "Klang"     -> \r_klang,
        "Farbklang" -> \r_farbklang,
        "Gerausch"  -> \r_gerausch,
        "Geräusch"  -> \r_gerausch,
        "Kadenz"    -> \r_kadenz,
        "Textur"    -> \r_textur,
        "Stille"    -> \r_stille,
        "Neutro"    -> \r_neutro,
    ];
    "5. Mappa categorie OK".postln;

    // ── 6. Stato globale ──────────────────────────────────────────────────
    // ~r_synths: Dictionary strumento → [procSynth, spatSynth]
    //   synth permanenti per tutta la durata del concerto
    // ~r_gestTension: tensione base impostata dall'ultimo click gesto
    // ~r_flucoTension: tensione modulata da FluCoMa in tempo reale
    //   tensione finale = clip(gestTension + flucoTension * 0.4, 0, 1)
    ~r_synths      = Dictionary.new;
    ~r_gestTension = 0.3;
    ~r_flucoTension = 0.0;  // aggiornato da remnant_flucos.scd
    ~r_masterVol   = 1.6;
    ~r_oscPort     = 57121;
    ~r_currentCat  = "Neutro";
    ~r_currentAz   = 180.0;
    ~r_score       = nil;   // partitura caricata da brownian_score.json
    ~r_scorePath   = ~r_dir ++ "brownian_score.json";
    "6. Stato OK".postln;

    // ── 7. Funzioni ───────────────────────────────────────────────────────

    // Tensione finale = tensione gesto + contributo FluCoMa
    ~r_tension = { (~r_gestTension + (~r_flucoTension * 0.4)).clip(0, 1) };

    // Boot permanente: crea synth proc + spat per ogni strumento
    // Tutti partono in Neutro, tensione 0.3
    ~r_boot = {
        var mixSynth;
        // Mix mono per FluCoMa
        mixSynth = Synth(\r_mix, [\outBus, ~r_mixBus.index], target: ~r_gIn);
        ~r_synths[\mix] = [mixSynth];

        ~r_instrBus.keysValuesDo { |instr, adcBus|
            var procBus, proc, spat;
            procBus = ~r_bus["Neutro"];
            proc    = Synth(\r_neutro,
                         [\inBus, adcBus, \outBus, procBus.index,
                          \azimuth, 180, \tension, 0.3],
                         target: ~r_gProc);
            spat    = Synth(\r_spatialize,
                         [\inBus, procBus.index, \outBase, 0,
                          \amp, ~r_masterVol, \azimuth, 180],
                         target: ~r_gSpat);
            ~r_synths[instr] = [proc, spat, procBus, adcBus];
            ("  boot: " ++ instr ++ " adc=" ++ adcBus).postln;
        };
        "Boot orchestra OK — " ++ ~r_instrBus.size ++ " strumenti attivi".postln;
    };

    // Click gesto da Remnant → cambia categoria e tensione su tutti gli strumenti
    // Sostituisce il proc synth di ogni strumento con il nuovo SynthDef
    ~r_gesture = { |category, tension, azimuth|
        var synthName, newProcBus;
        category = category ?? "Neutro";
        tension  = tension  ?? 0.3;
        azimuth  = azimuth  ?? 180.0;
        ~r_gestTension = tension;
        ~r_currentCat  = category;
        ~r_currentAz   = azimuth;
        synthName  = ~r_catSynth[category] ?? \r_neutro;
        newProcBus = ~r_bus[category] ?? ~r_bus["Neutro"];

        ~r_instrBus.keysValuesDo { |instr, adcBus|
            var entry, oldProc, spat, newProc, finalTension;
            entry = ~r_synths[instr];
            if(entry.notNil) {
                oldProc     = entry[0];
                spat        = entry[1];
                finalTension = ~r_tension.();
                // Sostituisce proc con nuova categoria
                oldProc.free;
                newProc = Synth(synthName,
                    [\inBus, adcBus, \outBus, newProcBus.index,
                     \azimuth, azimuth, \tension, finalTension],
                    target: ~r_gProc);
                spat.set(\inBus, newProcBus.index, \azimuth, azimuth);
                ~r_synths[instr] = [newProc, spat, newProcBus, adcBus];
            };
        };
        ("▶ Gesto: " ++ category ++ " tension=" ++ tension.round(0.01)
         ++ " az=" ++ azimuth.round(0.1)).postln;
    };

    // Aggiornamento tensione da FluCoMa — chiamato da remnant_flucos.scd
    // Aggiorna solo il parametro tension sui proc synth attivi, senza ricrearli
    ~r_flucoUpdate = { |flucoTension|
        var finalTension;
        ~r_flucoTension = flucoTension;
        finalTension = ~r_tension.();
        ~r_synths.keysValuesDo { |instr, entry|
            if(instr != \mix and: { entry.notNil }) {
                entry[0].set(\tension, finalTension);
            };
        };
    };

    ~r_panic = {
        // Reset a Neutro senza fermare i synth — rilancia boot
        ~r_synths.do { |entry| entry.do { |s| s.free } };
        ~r_synths = Dictionary.new;
        ~r_gestTension  = 0.3;
        ~r_flucoTension = 0.0;
        ~r_currentCat   = "Neutro";
        ~r_boot.();
        "PANIC → reset Neutro".postln;
    };

    "7. Funzioni OK".postln;

    // ── 8. OSC Receiver ───────────────────────────────────────────────────
    OSCdef.freeAll;

    // Click gesto dalla timeline di Remnant
    // msg: [path, idx, category, tension, azimuth]
    OSCdef(\r_gesture, { |msg|
        var idx      = msg[1].asInteger;
        var category = msg[2].asString;
        var tension  = msg[3].asFloat;
        var azimuth  = msg[4].asFloat;
        ["OSC /gesture G" ++ idx, category,
         "t=" ++ tension.round(0.01),
         "az=" ++ azimuth.round(0.1)].join(" ").postln;
        AppClock.sched(0, {
            ~r_gesture.(category, tension, azimuth);
            nil;
        });
    }, '/remnant/gesture', nil, ~r_oscPort);

    // Aggiornamento parametri singolo strumento (da Remnant o da FluCoMa esterno)
    OSCdef(\r_update, { |msg|
        var instr   = msg[1].asString;
        var azimuth = msg[2].asFloat;
        var tension = msg[3].asFloat;
        var entry   = ~r_synths[instr];
        if(entry.notNil) {
            entry[0].set(\azimuth, azimuth, \tension, tension);
            entry[1].set(\azimuth, azimuth);
        };
    }, '/remnant/update', nil, ~r_oscPort);

    // Aggiornamento tensione FluCoMa via OSC (da remnant_flucos.scd)
    OSCdef(\r_fluco, { |msg|
        var ft = msg[1].asFloat;
        ~r_flucoUpdate.(ft);
    }, '/remnant/fluco', nil, ~r_oscPort);

    OSCdef(\r_param, { |msg|
        var key = msg[1].asString;
        var val = msg[2].asFloat;
        if(key == "masterVol") {
            ~r_masterVol = val;
            ~r_synths.do { |entry|
                if(entry.size > 1) { entry[1].set(\amp, val) };
            };
        };
        if(key == "bpm") {
            ~r_synths.do { |entry|
                if(entry.notNil) { entry[0].set(\bpm, val) };
            };
        };
        ("param " ++ key ++ " = " ++ val).postln;
    }, '/remnant/param', nil, ~r_oscPort);

    OSCdef(\r_panic, { |msg|
        AppClock.sched(0, { ~r_panic.(); nil });
    }, '/remnant/panic', nil, ~r_oscPort);

    "8. OSC OK".postln;

    // ── 9. Boot orchestra ─────────────────────────────────────────────────
    ~r_boot.();
    "9. Orchestra OK".postln;

    // ── 10. Carica partitura ───────────────────────────────────────────────
    // Legge brownian_score.json dalla stessa cartella dello script.
    // ~r_score contiene tutti i gesti con category, tension, azimuth medio.
    // ~r_scoreGesture.(idx) applica direttamente un gesto dalla partitura —
    // equivalente a cliccare quel blocco sulla timeline di Remnant.
    if(File.exists(~r_scorePath)) {
        var f   = File.open(~r_scorePath, "r");
        var raw = f.readAllString;
        f.close;
        ~r_score = raw.parseJSON;
        // Pre-calcola azimuth medio per ogni gesto
        ~r_scoreAz = Dictionary.new;
        ~r_score["gestures"].do { |g|
            var evs = g["events"];
            var azMean = if(evs.notNil and: { evs.size > 0 }) {
                evs.collect { |e| e["azimuth"].asFloat }.sum / evs.size
            } { 180.0 };
            ~r_scoreAz[g["index"].asInteger] = azMean.round(0.1);
        };
        ("10. Partitura caricata: "
            ++ ~r_score["gestures"].size ++ " gesti  ·  "
            ++ ~r_scorePath).postln;
    } {
        "10. Partitura non trovata — genera da Remnant e salva in: ".postln;
        ~r_scorePath.postln;
    };

    // Applica un gesto dalla partitura per indice (0-based)
    // Utile per test: ~r_scoreGesture.(2)
    ~r_scoreGesture = { |idx|
        if(~r_score.notNil) {
            var g = ~r_score["gestures"].detect { |x| x["index"].asInteger == idx };
            if(g.notNil) {
                var cat     = g["lachenmann"] ?? "Neutro";
                var tension = g["tension"].asFloat;
                var azimuth = ~r_scoreAz[idx] ?? 180.0;
                ~r_gesture.(cat, tension, azimuth);
            } {
                ("Gesto " ++ idx ++ " non trovato in partitura").postln;
            };
        } {
            "Nessuna partitura caricata".postln;
        };
    };

    // ── Pronto ────────────────────────────────────────────────────────────
    "═══════════════════════════════════════".postln;
    "REMNANT pronto.".postln;
    "".postln;
    "Gesto da partitura: ~r_scoreGesture.(0)   // indice 0-based".postln;
    "Gesto manuale:      ~r_gesture.(\"Klang\", 0.7, 90)".postln;
    "FluCoMa test:       ~r_flucoUpdate.(0.6)".postln;
    "Panic:              ~r_panic.()".postln;
    "CPU:                s.avgCPU".postln;
    "Score path:         ~r_scorePath".postln;
    "═══════════════════════════════════════".postln;
});
)
