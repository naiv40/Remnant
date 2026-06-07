// ─────────────────────────────────────────────────────────────────────────────
// Remnant — ConTimbre playback test — FOA ottafonico (ATK)
// File separato, non tocca nessun file esistente.
//
// Prerequisiti:
//   1. brownian_score.json generato con corpus ConTimbre
//   2. SBCL installato in /usr/local/bin/sbcl
//   3. contimbre_resolve_paths.lisp nella stessa cartella
// ─────────────────────────────────────────────────────────────────────────────

// ── Blocco 0 — Decoder FOA (esegui prima del boot) ───────────────────────────
(
~decoder = FoaDecoderMatrix.newPanto(8);
"Decoder OK".postln;
)

// ── Blocco 1 — Boot ──────────────────────────────────────────────────────────
(
s.options.numOutputBusChannels = 8;
s.waitForBoot {
    ~scorePath = "~/Desktop/remnant/brownian_score.json".standardizePath;
    ~lispPath  = "~/Desktop/remnant/contimbre_resolve_paths.lisp".standardizePath;
    ~bufCache  = Dictionary.new;
    ~foaBus    = Bus.audio(s, 4);
    "Ready. Run Block 2.".postln;
};
)

// ── Blocco 2 — SynthDef ───────────────────────────────────────────────────────
// Nel Blocco 2, sostituisci r_ct_foa con questa versione:
(
SynthDef(\r_ct_foa, { |bufnum, amp=0.7, azimuth=0, out=0, revTime=2.0, revMix=0.3|
    var sig, env, az, w, x, y, z, wet;
    // doneAction:0 — il synth NON muore quando il sample finisce;
    // DetectSilence aspetta che la coda del riverbero si esaurisca.
    env = EnvGen.kr(Env.linen(0.02, BufDur.kr(bufnum) - 0.06, 0.04), doneAction: 0);
    sig = PlayBuf.ar(1, bufnum, loop: 0, doneAction: 0) * env * amp;
    wet = FreeVerb.ar(sig, mix: revMix, room: revTime, damp: 0.5);
    az  = azimuth * (pi/180);
    w   = wet * 0.7071;
    x   = wet * cos(az);
    y   = wet * sin(az);
    z   = wet * 0;
    // Il synth si libera solo quando l'uscita è sotto la soglia di silenzio
    DetectSilence.ar(wet, amp: 0.001, time: 0.3, doneAction: 2);
    Out.ar(out, [w, x, y, z]);
}).add;

SynthDef(\r_ct_foa2, { |bufnum, amp=0.7, azimuth=0, out=0, revTime=2.0, revMix=0.3|
    var sig, mono, env, az, w, x, y, z, wet;
    env  = EnvGen.kr(Env.linen(0.02, BufDur.kr(bufnum) - 0.06, 0.04), doneAction: 0);
    sig  = PlayBuf.ar(2, bufnum, loop: 0, doneAction: 0);
    mono = (sig[0] + sig[1]) * 0.5 * env * amp;
    wet  = FreeVerb.ar(mono, mix: revMix, room: revTime, damp: 0.5);
    az   = azimuth * (pi/180);
    w    = wet * 0.7071;
    x    = wet * cos(az);
    y    = wet * sin(az);
    z    = wet * 0;
    DetectSilence.ar(wet, amp: 0.001, time: 0.3, doneAction: 2);
    Out.ar(out, [w, x, y, z]);
}).add;

SynthDef(\r_foa_decode_ct, { |in=0, out=0|
    var bfmt, decoded;
    bfmt    = In.ar(in, 4);
    decoded = FoaDecode.ar(bfmt, ~decoder);
    Out.ar(out, decoded);
}).add;

SynthDef(\r_ct_rec, { |bufnum=0, in=0|
    var sig = In.ar(in, 8);
    DiskOut.ar(bufnum, sig);
}).add;

"SynthDefs ready. Run Block 3.".postln;
)

// ── Blocco 3 — Risolvi path via SBCL ─────────────────────────────────────────
(
"Resolving ConTimbre paths via SBCL...".postln;
"(this may take ~30 seconds)".postln;

Routine {
    var result = String.new;
    var pipe   = Pipe.new(
        "/usr/local/bin/sbcl --load %".format(~lispPath.shellQuote),
        "r"
    );
    var line;
    while { (line = pipe.getLine).notNil } {
        line.postln;
    };
    pipe.close;

    // Leggi il JSON dei path
    ~pathMap = Dictionary.new;
    if (File.exists("/tmp/contimbre_paths.json")) {
        var json = "/tmp/contimbre_paths.json".parseJSONFile;
        json.keysValuesDo { |k, v| ~pathMap[k] = v };
        ("Path map: % entries".format(~pathMap.size)).postln;
        "Run Block 4.".postln;
    } {
        "ERROR: /tmp/contimbre_paths.json not found.".postln;
    };
}.play;
)

// ── Blocco 4 — Avvia decoder e funzioni playback ──────────────────────────────
(
~decoderSynth = Synth(\r_foa_decode_ct,
    [\in, ~foaBus.index, \out, 0],
    addAction: \addToTail);

~playEvent = { |ev|
    var id      = ev["id"].asString;
    var azimuth = ev["azimuth"].asFloat;
    var wavPath = ~pathMap[id];

    if (wavPath.notNil) {
        if (~bufCache.includesKey(wavPath)) {
            Synth(
                if(~bufCache[wavPath].numChannels==2){\r_ct_foa2}{\r_ct_foa},
                [\bufnum, ~bufCache[wavPath].bufnum,
                 \azimuth, azimuth, \amp, 0.7, \out, ~foaBus.index],
                addAction: \addToHead
            );
            ("  ♪ % [cached]  az=%°".format(id, azimuth.round(1))).postln;
        } {
            Buffer.read(s, wavPath, action: { |buf|
                ~bufCache[wavPath] = buf;
                Synth(
                    if(buf.numChannels==2){\r_ct_foa2}{\r_ct_foa},
                    [\bufnum, buf.bufnum,
                     \azimuth, azimuth, \amp, 0.7, \out, ~foaBus.index],
                    addAction: \addToHead
                );
                ("  ♪ %  az=%°".format(id, azimuth.round(1))).postln;
            });
        };
    } {
        ("  ✗ no path for: %".format(id)).postln;
    };
};

~playGesture = { |gestureIdx=0|
    var score  = ~scorePath.parseJSONFile;
    var g      = score["gestures"][gestureIdx];
    var events = g["events"];
    var t0     = events[0]["t"].asFloat;
    ("Playing gesture % — % events".format(gestureIdx+1, events.size)).postln;
    {
        events.do { |ev|
            (ev["t"].asFloat - t0).wait;
            t0 = ev["t"].asFloat;
            ~playEvent.(ev);
        };
        "Done.".postln;
    }.fork;
};

"~playGesture.(0)  →  gesto 1".postln;
"~playGesture.(1)  →  gesto 2".postln;

// Playback sequenziale dell'intera score
// ── Registrazione ────────────────────────────────────────────────────────────
~recStart = { |path|
    var ts;
    ts   = Date.getDate.format("%Y%m%d_%H%M%S");
    path = path ?? (Platform.userHomeDir ++ "/Desktop/remnant_" ++ ts ++ ".aiff");
    ~recBuf  = Buffer.alloc(s, 65536, 8);
    ~recBuf.write(path, "AIFF", "float", 0, 0, true);
    ~recSynth = Synth(\r_ct_rec,
        [\bufnum, ~recBuf.bufnum, \in, 0],
        addAction: \addToTail);
    ("● REC → " ++ path).postln;
    ~recPath = path;
};

~recStop = {
    if (~recSynth.notNil) { ~recSynth.free; ~recSynth = nil };
    if (~recBuf.notNil)   { ~recBuf.close;  ~recBuf.free;  ~recBuf  = nil };
    ("■ REC stop → " ++ ~recPath).postln;
};

~playScore = {
    var score, gestures;
    score    = ~scorePath.parseJSONFile;
    gestures = score["gestures"];
    ~scoreRoutine = Routine {
        ("═══ Score start — % gesti ═══".format(gestures.size)).postln;
        ~recStart.();  // avvia registrazione automaticamente
        gestures.do { |g|
            var idx    = g["index"].asInteger;
            var events = g["events"];
            var t0, gestDur;
            if (events.size > 0) {
                // Attesa dall\'inizio del gesto (t_start assoluto)
                t0      = events[0]["t"].asFloat;
                gestDur = g["t_end"].asFloat - g["t_start"].asFloat;
                ("▶ Gesto %/% — % eventi  [%s → %s]".format(
                    idx+1, gestures.size, events.size,
                    g["t_start"].asFloat.round(0.1),
                    g["t_end"].asFloat.round(0.1))).postln;
                events.do { |ev|
                    (ev["t"].asFloat - t0).wait;
                    t0 = ev["t"].asFloat;
                    ~playEvent.(ev);
                };
                // Attesa fino alla fine del gesto prima di avanzare
                (g["t_end"].asFloat - events.last["t"].asFloat).wait;
            };
        };
        "═══ Score fine ═══".postln;
        // Aspetta che tutti i synth attivi (code riverbero) si liberino
        // prima di chiudere la registrazione.
        // Controlla ogni 0.5s — esce quando non ci sono più synth audio
        // oltre al decoder FOA.
        block { |break|
            50.do {  // max 25 secondi di attesa
                0.5.wait;
                if (s.numSynths <= 2) { break.(nil) };  // solo decoder + rec
            };
        };
        1.0.wait;  // margine finale
        ~recStop.();
    };
    ~scoreRoutine.play;
};

~stopScore = {
    if (~scoreRoutine.notNil) {
        ~scoreRoutine.stop;
        ~scoreRoutine = nil;
        "Score interrotta.".postln;
    };
    ~recStop.();
};

"~playScore.()          →  intera score + rec automatica".postln;
"~stopScore.()          →  interrompi".postln;
"~recStart.()           →  solo rec (senza playback)".postln;
"~recStop.()            →  ferma rec".postln;
)
~recStart.()
~playScore.()
// ── Blocco 5 — Stop ──────────────────────────────────────────────────────────
(
~decoderSynth.free;
s.freeAll;
"Stopped.".postln;
)
