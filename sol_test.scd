// ─────────────────────────────────────────────────────────────────────────────
// Remnant — SOL HQ playback — FOA ottafonico (ATK)
// ─────────────────────────────────────────────────────────────────────────────

// ── Blocco 0 — Decoder e encoder (esegui prima del boot) ─────────────────────
(
~decoder = FoaDecoderMatrix.newPanto(8);
"Decoder OK — %".format(~decoder).postln;
)

// ── Blocco 1 — Boot ──────────────────────────────────────────────────────────
(
s.options.numOutputBusChannels = 8;
s.waitForBoot {
    ~solBase   = "/Volumes/disk 1/SOL_0.9_HQ 2";
    ~scorePath = "~/Desktop/remnant/brownian_score.json".standardizePath;
    ~bufCache  = Dictionary.new;

    ~instrFolderMap = Dictionary.new;
    PathName(~solBase).entries.do { |famPath|
        famPath.entries.do { |instrPath|
            var folder = instrPath.folderName;
            var idx    = folder.indexOf($_);
            var clean  = if(idx.notNil){ folder.copyToEnd(idx+1) }{ folder };
            ~instrFolderMap[clean] = folder;
        };
    };
    ("Instrument map: % entries".format(~instrFolderMap.size)).postln;

    ~foaBus = Bus.audio(s, 4);
    "Ready. Run Block 2.".postln;
};
)

// ── Blocco 2 — SynthDef ───────────────────────────────────────────────────────
(
// Encoder per ogni posizione azimutale — creati SC-side, non dentro SynthDef
// Usiamo FoaEncode.ar con omni encoder e poi FoaRotate per posizionare
// Encode manuale B-format: W=sig, X=cos(az)*sig, Y=sin(az)*sig, Z=0
// Compatibile con qualsiasi versione ATK — nessun matrix oggetto dentro SynthDef

SynthDef(\r_sol_foa, { |bufnum, amp=0.7, azimuth=0, out=0|
    var sig, env, az, w, x, y, z;
    env  = EnvGen.kr(Env.linen(0.02, BufDur.kr(bufnum) - 0.06, 0.1), doneAction: 2);
    sig  = PlayBuf.ar(1, bufnum, loop: 0, doneAction: 2) * env * amp;
    az   = azimuth * (pi/180);
    w    = sig * 0.7071;
    x    = sig * cos(az);
    y    = sig * sin(az);
    z    = sig * 0;
    Out.ar(out, [w, x, y, z]);
}).add;

SynthDef(\r_sol_foa2, { |bufnum, amp=0.7, azimuth=0, out=0|
    var sig, mono, env, az, w, x, y, z;
    env  = EnvGen.kr(Env.linen(0.02, BufDur.kr(bufnum) - 0.06, 0.1), doneAction: 2);
    sig  = PlayBuf.ar(2, bufnum, loop: 0, doneAction: 2);
    mono = (sig[0] + sig[1]) * 0.5 * env * amp;
    az   = azimuth * (pi/180);
    w    = mono * 0.7071;
    x    = mono * cos(az);
    y    = mono * sin(az);
    z    = mono * 0;
    Out.ar(out, [w, x, y, z]);
}).add;

SynthDef(\r_foa_decode, { |in=0, out=0|
    var bfmt, decoded;
    bfmt    = In.ar(in, 4);
    decoded = FoaDecode.ar(bfmt, ~decoder);
    Out.ar(out, decoded);
}).add;

"SynthDefs ready. Run Block 3.".postln;
)

// ── Blocco 3 — Avvia decoder e funzioni playback ──────────────────────────────
(
~decoderSynth = Synth(\r_foa_decode,
    [\in, ~foaBus.index, \out, 0],
    addAction: \addToTail);

~findWav = { |id, family, instrument, technique|
    var instrFolder = ~instrFolderMap[instrument] ? instrument;
    var candidates  = [
        "%/%/%/%/%.wav".format(~solBase, family, instrFolder, technique, id),
        "%/%/%/%/%.wav".format(~solBase, family, instrument, technique, id),
        "%/%/%/%/%.wav".format(~solBase, family, instrFolder,
            technique.replace("-","_"), id),
    ];
    candidates.detect { |p| File.exists(p) }
};

~playEvent = { |ev|
    var id        = ev["id"].asString;
    var instr     = ev["instrument"].asString;
    var family    = ev["family"].asString;
    var technique = ev["technique"] !? _.asString ?? "";
    var azimuth   = ev["azimuth"].asFloat;
    var wavPath   = ~findWav.(id, family, instr, technique);

    if (wavPath.notNil) {
        if (~bufCache.includesKey(wavPath)) {
            Synth(
                if(~bufCache[wavPath].numChannels==2){\r_sol_foa2}{\r_sol_foa},
                [\bufnum, ~bufCache[wavPath].bufnum, \azimuth, azimuth, \amp, 0.7, \out, ~foaBus.index],
                addAction: \addToHead
            );
            ("  ♪ % [cached]  az=%°".format(id, azimuth.round(1))).postln;
        } {
            Buffer.read(s, wavPath, action: { |buf|
                ~bufCache[wavPath] = buf;
                Synth(
                    if(buf.numChannels==2){\r_sol_foa2}{\r_sol_foa},
                    [\bufnum, buf.bufnum, \azimuth, azimuth, \amp, 0.7, \out, ~foaBus.index],
                    addAction: \addToHead
                );
                ("  ♪ %  az=%°".format(id, azimuth.round(1))).postln;
            });
        };
    } {
        ("  ✗ %".format(id)).postln;
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
)

// ── Blocco 4 — Stop ──────────────────────────────────────────────────────────
(
~decoderSynth.free;
s.freeAll;
"Stopped.".postln;
)
