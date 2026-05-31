(
~r_dir = thisProcess.nowExecutingPath.dirname ++ "/";

s.options.inDevice             = "BlackHole 16ch";
s.options.outDevice            = "Built-in Output";
s.options.numInputBusChannels  = 16;
s.options.numOutputBusChannels = 8;
s.options.memSize              = 131072;
s.options.numBuffers           = 2048;
s.options.blockSize            = 512;
s.options.sampleRate           = 48000;
s.options.numWireBufs          = 512;
s.options.maxNodes             = 2048;

s.waitForBoot({
    Routine({

    // ── 1. Groups ─────────────────────────────────────────────────────────
    ~r_gIn    = Group.new;
    ~r_gProc  = Group.after(~r_gIn);
    ~r_gXfade = Group.after(~r_gProc);
    ~r_gSpat  = Group.after(~r_gXfade);
    "1. Groups OK".postln;

    // ── 2. Buses ──────────────────────────────────────────────────────────
    // Fields arrive on BlackHole CH 0..N-1 (0-based)
    // nFields is set from score after loading — default 4 until score loads
    ~r_scorePath = ~r_dir ++ "brownian_score.json";
    ~r_nFields = if(File.exists(~r_scorePath)) {
        var f, raw, sc;
        f   = File.open(~r_scorePath, "r");
        raw = f.readAllString;
        f.close;
        sc  = raw.parseJSON;
        sc["gestures"].size.max(1)
    } { 4 };
    ~r_fieldChs = Array.series(~r_nFields, 0, 1);
    ("nFields: " ++ ~r_nFields).postln;

    ~r_procBusA  = Array.fill(~r_nFields, { Bus.audio(s, 1) });
    ~r_procBusB  = Array.fill(~r_nFields, { Bus.audio(s, 1) });
    ~r_xfadeBus  = Array.fill(~r_nFields, { Bus.audio(s, 1) });
    ~r_mixBus    = Bus.audio(s, 1);   // mono mix for FluCoMa
    "2. Buses OK".postln;

    // ── 3. SynthDefs ──────────────────────────────────────────────────────

    // Mono mix of all field inputs for FluCoMa analysis
    SynthDef(\r_mix, { |outBus=0, nFields=4|
        var sig = Mix.ar(SoundIn.ar([0,1,2,3])) / 4.0;
        Out.ar(outBus, sig);
    }).add;

    // Passthrough (silent) — used before conv engine loads
    SynthDef(\r_input, { |adcBus=0, outBus=0, amp=0.0|
        Out.ar(outBus, SoundIn.ar(adcBus) * amp);
    }).add;

    // 8ch octophonic spatialiser
    SynthDef(\r_spat8, { |inBus=0, amp=0.85, azimuth=180|
        var sig, az, g0, g1, g2, g3, g4, g5, g6, g7;
        var angDist;
        sig = In.ar(inBus) * amp;
        sig = Limiter.ar(sig, 0.95);
        az  = azimuth % 360;
        angDist = { |spkAngle|
            var d       = (az - spkAngle) % 360;
            var dFolded = (d - 180).fold2(180);
            (dFolded.abs * (pi / 90)).cos.max(0)
        };
        g0 = angDist.(0);   g1 = angDist.(45);
        g2 = angDist.(90);  g3 = angDist.(135);
        g4 = angDist.(180); g5 = angDist.(225);
        g6 = angDist.(270); g7 = angDist.(315);
        Out.ar(0, [sig*g0, sig*g1, sig*g2, sig*g3,
                   sig*g4, sig*g5, sig*g6, sig*g7]);
    }).add;

    // Gate — envelope follower, outputs control signal 0→1
    SynthDef(\r_gate, {
        |inBus=0, outBus=0, thresh= -42, attackTime=0.08, releaseTime=1.2, depth=1.0|
        var sig  = Mix.ar(SoundIn.ar([0,1,2,3])) / 4.0;
        var amp  = Amplitude.ar(sig, attackTime, releaseTime);
        var gate = (amp > thresh.dbamp).lag(attackTime, releaseTime);
        var env  = ((1 - depth) + (gate * depth)).clip(0, 1);
        Out.kr(outBus, env);
    }).add;

    // Crossfader (mono)
    SynthDef(\r_xfade, { |busA=0, busB=0, outBus=0, xfade=0, amp=1.0|
        var sigA = In.ar(busA);
        var sigB = In.ar(busB);
        var xf   = Lag.kr(xfade, 0.05);
        Out.ar(outBus, XFade2.ar(sigA, sigB, xf * 2 - 1) * amp);
    }).add;

    "3. SynthDefs OK".postln;
    s.sync;

    // ── 4. Category map — populated by remnant_conv.scd ──────────────────
    ~r_catSynth = Dictionary.new;
    [\r_conv, \r_input].do { |sym|
        ["Klang","Farbklang","Geräusch","Gerausch",
         "Kadenz","Textur","Stille","Neutro","Forward"].do { |cat|
            ~r_catSynth[cat] = \r_input;
        };
    };
    "4. Category map (passthrough until remnant_conv.scd)".postln;

    // ── 5. Global state ───────────────────────────────────────────────────
    ~r_synths       = Dictionary.new;  // fieldIdx -> [procA, xfader, spat]
    ~r_gestTension  = 0.3;
    ~r_flucoTension = 0.0;
    ~r_masterVol    = 1.0;
    ~r_xfadeTime    = 3.0;
    ~r_oscPort      = 57121;
    ~r_currentCat   = "Neutro";
    ~r_currentAz    = 180.0;
    ~r_score        = nil;
    // Per-field azimuth from score (set when score loads)
    ~r_fieldAz      = Array.fill(~r_nFields, { 180.0 });
    ~r_fieldCat     = Array.fill(~r_nFields, { "Neutro" });
    ~r_fieldTension = Array.fill(~r_nFields, { 0.3 });
    "5. State OK".postln;

    // ── 6. Functions ──────────────────────────────────────────────────────
    ~r_tension = { (~r_gestTension + (~r_flucoTension * 0.4)).clip(0, 1) };

    // Boot: one proc/xfade/spat chain per field
    ~r_boot = {
        var mixSynth = Synth(\r_mix, [\outBus, ~r_mixBus.index], target: ~r_gIn);
        ~r_synths[\mix] = mixSynth;

        ~r_nFields.do { |i|
            var adcBus  = ~r_fieldChs[i];
            var procA   = Synth(\r_input,
                [ \adcBus, adcBus, \outBus, ~r_procBusA[i].index, \amp, 1.0 ],
                target: ~r_gProc);
            var xfader  = Synth(\r_xfade,
                [ \busA, ~r_procBusA[i].index, \busB, ~r_procBusB[i].index,
                  \outBus, ~r_xfadeBus[i].index, \xfade, 0.0, \amp, 1.0 ],
                target: ~r_gXfade);
            var spat    = Synth(\r_spat8,
                [ \inBus, ~r_xfadeBus[i].index,
                  \amp, ~r_masterVol, \azimuth, 180 ],
                target: ~r_gSpat);
            ~r_synths[i] = [procA, xfader, spat];
            ("  field " ++ (i+1) ++ " → BlackHole CH" ++ adcBus).postln;
        };
        "Boot OK — " ++ ~r_nFields ++ " fields active".postln;
    };

    // Gesture: activate convolution on all fields with new category
    ~r_gesture = { |category, tension, azimuth|
        var synthName  = ~r_catSynth[category] ?? \r_input;
        var finalT     = ~r_tension.();
        category  = category ?? "Neutro";
        tension   = tension  ?? 0.3;
        azimuth   = azimuth  ?? 180.0;
        ~r_gestTension = tension;
        ~r_currentCat  = category;
        ~r_currentAz   = azimuth;

        ~r_nFields.do { |i|
            var entry    = ~r_synths[i];
            var adcBus   = ~r_fieldChs[i];
            var fieldAz  = ~r_fieldAz[i];
            if(entry.notNil) {
                var procA, xfader, spat, procB;
                procA  = entry[0];
                xfader = entry[1];
                spat   = entry[2];
                procB  = Synth(synthName,
                    [ \inBus,   adcBus,
                      \outBus,  ~r_procBusB[i].index,
                      \azimuth, fieldAz,
                      \tension, finalT ],
                    target: ~r_gProc);
                xfader.set(\busA, ~r_procBusA[i].index,
                           \busB, ~r_procBusB[i].index);
                spat.set(\azimuth, fieldAz);
                Routine({
                    var steps = 40;
                    var dt    = ~r_xfadeTime / steps;
                    steps.do { |i2|
                        xfader.set(\xfade, (i2 + 1) / steps);
                        dt.wait;
                    };
                    procA.free;
                    ~r_synths[i] = [procB, xfader, spat];
                    xfader.set(\busA, ~r_procBusB[i].index,
                               \busB, ~r_procBusA[i].index, \xfade, 0.0);
                }).play(AppClock);
            };
        };
        ("▶ " ++ category ++ " t=" ++ tension.round(0.01)
         ++ " az=" ++ azimuth.round(0.1)).postln;
    };

    // Update tension on all running processors
    ~r_flucoUpdate = { |flucoTension|
        var finalTension;
        ~r_flucoTension = flucoTension;
        finalTension = ~r_tension.();
        ~r_nFields.do { |i|
            var entry = ~r_synths[i];
            if(entry.notNil) {
                try { entry[0].set(\tension, finalTension) };
            };
        };
    };

    ~r_panic = {
        ~r_nFields.do { |i|
            var entry = ~r_synths[i];
            if(entry.notNil) { entry.do { |syn| try { syn.free } } };
        };
        ~r_synths = Dictionary.new;
        ~r_gestTension  = 0.3;
        ~r_flucoTension = 0.0;
        ~r_currentCat   = "Neutro";
        ~r_boot.();
        "PANIC → reset".postln;
    };

    "6. Functions OK".postln;

    // ── 7. OSC ────────────────────────────────────────────────────────────
    OSCdef.freeAll;

    OSCdef(\r_gesture, { |msg|
        var idx      = msg[1].asInteger;
        var category = msg[2].asString;
        var tension  = msg[3].asFloat;
        var azimuth  = msg[4].asFloat;
        AppClock.sched(0, {
            ~r_gesture.(category, tension, azimuth);
            nil;
        });
        ["OSC /gesture F"++idx, category,
         "t="++tension.round(0.01), "az="++azimuth.round(0.1)].join(" ").postln;
    }, '/remnant/gesture', nil, ~r_oscPort);

    OSCdef(\r_fluco, { |msg|
        ~r_flucoUpdate.(msg[1].asFloat);
    }, '/remnant/fluco', nil, ~r_oscPort);

    OSCdef(\r_param, { |msg|
        var key = msg[1].asString;
        var val = msg[2].asFloat;
        switch(key,
            "masterVol",  {
                ~r_masterVol = val;
                ~r_nFields.do { |i|
                    var entry = ~r_synths[i];
                    if(entry.notNil) { try { entry[2].set(\amp, val) } };
                };
            },
            "xfadeTime",  { ~r_xfadeTime = val.max(0.1) },
            "nFields",    {
                ~r_nFields  = val.asInteger.clip(1, 16);
                ~r_fieldChs = Array.series(~r_nFields, 0, 1);
            }
        );
        ("param " ++ key ++ " = " ++ val).postln;
    }, '/remnant/param', nil, ~r_oscPort);

    OSCdef(\r_panic, { |msg|
        AppClock.sched(0, { ~r_panic.(); nil });
    }, '/remnant/panic', nil, ~r_oscPort);

    "7. OSC OK".postln;

    // ── 8. Boot ───────────────────────────────────────────────────────────
    ~r_boot.();
    "8. Orchestra OK".postln;

    // ── 9. Load score ─────────────────────────────────────────────────────
    if(File.exists(~r_scorePath)) {
        var f   = File.open(~r_scorePath, "r");
        var raw = f.readAllString;
        f.close;
        ~r_score = raw.parseJSON;
        ~r_score["gestures"].do { |g|
            var idx = g["index"].asInteger;
            var evs = g["events"] ?? [];
            var az  = if(evs.size > 0) {
                evs.collect { |e| e["azimuth"].asFloat }.sum / evs.size
            } { 180.0 };
            var cat     = g["lachenmann"] ?? (g["dynamic_form"] ?? "Neutro");
            var tension = g["tension"].asFloat;
            if(idx < ~r_nFields) {
                ~r_fieldAz[idx]      = az.round(0.1);
                ~r_fieldCat[idx]     = cat;
                ~r_fieldTension[idx] = tension;
            };
        };
        ("9. Score loaded: " ++ ~r_nFields
         ++ " fields · " ++ ~r_scorePath).postln;
    } {
        "9. Score not found.".postln;
    };

    // ── Ready ─────────────────────────────────────────────────────────────
    "═══════════════════════════════════════".postln;
    "REMNANT ready.".postln;
    "Evaluate remnant_conv.scd to activate convolution.".postln;
    "Test:   ~r_gesture.(\"Geräusch\", 0.8, 90)".postln;
    "Panic:  ~r_panic.()".postln;
    "CPU:    s.avgCPU".postln;
    "Fields: " ++ ~r_nFields ++ " on BlackHole CH " ++ ~r_fieldChs.asString.postln;
    "═══════════════════════════════════════".postln;

    }).play(AppClock);
});
)
