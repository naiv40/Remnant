/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — HUD                                                               ║
║  Launch AFTER remnant_sc.scd and remnant_conv.scd                            ║
║                                                                              ║
║  Block 1 — gate synth + score loader + timer engine                         ║
║  Block 2 — HUD window                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 1 — Gate + Score + Timer
// ═══════════════════════════════════════════════════════════════════════════
(
if(~r_mixBus.isNil) { Error("Launch remnant_sc.scd first").throw };

// ── Gate ─────────────────────────────────────────────────────────────────────
SynthDef(\r_gate, {
	|inBus=0, outBus=0, thresh= -42, attackTime=0.08, releaseTime=1.2, depth=1.0|
	var sig  = Mix.ar(SoundIn.ar([0,1,2,3])) / 4.0;
	var amp  = Amplitude.ar(sig, attackTime, releaseTime);
	var gate = (amp > thresh.dbamp).lag(attackTime, releaseTime);
	var env  = ((1 - depth) + (gate * depth)).clip(0, 1);
	Out.kr(outBus, env);
}).add;

~r_gateBus     = Bus.control(s, 1);
~r_gateThresh  = -42.0;
~r_gateAttack  =  0.08;
~r_gateRelease =  1.2;
~r_gateDepth   =  1.0;

~r_gateSynth = Synth(\r_gate, [
	\inBus,       ~r_mixBus.index,
	\outBus,      ~r_gateBus.index,
	\thresh,      ~r_gateThresh,
	\attackTime,  ~r_gateAttack,
	\releaseTime, ~r_gateRelease,
	\depth,       ~r_gateDepth,
], target: ~r_gProc, addAction: \addToHead);

~r_hudGateLevel = 1.0;
~r_flucoUpdateOrig = ~r_flucoUpdate;
~r_flucoUpdate = { |flucoTension|
	var gv = ~r_hudGateLevel ? 1.0;
	~r_flucoUpdateOrig.(flucoTension * gv);
};

// ── Score: costruisce la sequenza dei gesti ───────────────────────────────────
// Legge ~r_score (già caricato da remnant_sc.scd).
// Ogni gesto: (index, tStart, tEnd, cat, tension, azimuth medio degli eventi).
~r_hudGestures = [];
~r_hudDuration = 0.0;
~r_hudManualTension = nil;

if(~r_score.notNil) {
	var gest = ~r_score["gestures"];
	~r_hudDuration = ~r_score["duration"].asFloat;
	~r_hudGestures = gest.collect { |g|
		var evs = g["events"] ?? [];
		var az  = if(evs.size > 0) {
			evs.collect { |e| e["azimuth"].asFloat }.sum / evs.size
		} { 180.0 };
		var cat     = g["lachenmann"] ?? (g["dynamic_form"] ?? "Neutro");
		var tension = g["tension"].asFloat;
		(
			index:   g["index"].asInteger,
			tStart:  g["t_start"].asFloat,
			tEnd:    g["t_end"].asFloat,
			cat:     cat,
			tension: tension,
			azimuth: az.round(0.1),
		)
	};
	("Score: " ++ ~r_hudGestures.size ++ " gesti · "
	 ++ ~r_hudDuration ++ "s totali").postln;
} {
	"HUD: nessuna score caricata — avvia remnant_sc.scd".postln;
};

// ── Timer state ───────────────────────────────────────────────────────────────
~r_timerRunning   = false;
~r_timerStartTime = 0.0;
~r_timerGestIdx   = 0;
~r_timerRoutine   = nil;

// Avanza al gesto idx e chiama ~r_gesture globalmente
~r_hudAdvanceGesture = { |idx|
	var g = ~r_hudGestures[idx];
	if(g.notNil) {
		var tension = ~r_hudManualTension ?? g[\tension];
		~r_timerGestIdx = idx;
		AppClock.sched(0, {
			~r_gesture.(g[\cat], tension, g[\azimuth]);
			if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
			nil;
		});
		("▶ Gesto " ++ (idx+1) ++ "/" ++ ~r_hudGestures.size
		 ++ "  " ++ g[\cat]
		 ++ "  t=" ++ tension.round(0.01)
		 ++ "  az=" ++ g[\azimuth]).postln;
	};
};

// START: lancia Routine su SystemClock che scorre i gesti secondo la score
~r_hudStart = {
	if(~r_timerRunning.not and: { ~r_hudGestures.size > 0 }) {
		~r_timerRunning   = true;
		~r_timerGestIdx   = 0;
		~r_timerStartTime = thisThread.seconds;

		~r_timerRoutine = Routine({
			~r_hudGestures.size.do { |i|
				var g       = ~r_hudGestures[i];
				var gestDur = g[\tEnd] - g[\tStart];
				~r_hudAdvanceGesture.(i);
				gestDur.wait;
			};
			~r_timerRunning = false;
			AppClock.sched(0, {
				if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
				nil;
			});
			"═══ REMNANT fine ═══".postln;
		}).play(SystemClock);

		"═══ REMNANT start ═══".postln;
	} {
		if(~r_timerRunning) {
			"Timer già in esecuzione.".postln
		} {
			"Nessuna score caricata.".postln
		};
	};
};

// STOP: interrompe la Routine e azzera lo stato
~r_hudStop = {
	if(~r_timerRoutine.notNil) { ~r_timerRoutine.stop };
	~r_timerRunning = false;
	~r_timerGestIdx = 0;
	AppClock.sched(0, {
		if(~r_hudUpdateDisplay.notNil) { ~r_hudUpdateDisplay.() };
		nil;
	});
	"═══ REMNANT stop ═══".postln;
};

"HUD Block 1 OK — evaluate Block 2 to open window".postln;
)


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 2 — HUD window
// ═══════════════════════════════════════════════════════════════════════════
(
var win       = Window("REMNANT", Rect(20, 20, 260, 420), resizable: false)
                .background_(Color(0.08, 0.08, 0.08, 0.92))
                .alwaysOnTop_(true);
var layout    = VLayout();
var accentCol = Color(0.22, 0.55, 0.9);
var dimCol    = Color(0.45, 0.45, 0.45);
var fgCol     = Color.white;
var greenCol  = Color(0.2, 0.7, 0.3);
var redCol    = Color(0.9, 0.3, 0.1);
var monoFont  = Font("Courier New", 10);
var monoSmall = Font("Courier New", 9);
var makeSlider = { |labelStr, knobCol|
	var row = HLayout();
	var lbl = StaticText().string_(labelStr).font_(monoFont)
	          .stringColor_(dimCol).fixedWidth_(88);
	var val = StaticText().string_("—").font_(monoFont)
	          .stringColor_(fgCol).fixedWidth_(36).align_(\right);
	var sl  = Slider().orientation_(\horizontal)
	          .background_(Color(0.15,0.15,0.15))
	          .knobColor_(knobCol ?? accentCol);
	row.margins = [0,0,0,0]; row.spacing = 4;
	row.add(lbl); row.add(sl); row.add(val);
	[row, sl, val]
};
var sep = {
	StaticText().string_("─────────────────────────")
	.stringColor_(dimCol).font_(monoFont).align_(\center)
};
var gestLabel, catLabel, progressBar, timeLabel;
var startBtn, stopBtn;
var tensRow, tensSlider, tensVal;
var gateMeter;
var thrRow,  thrSlider,  thrVal;
var relRow,  relSlider,  relVal;
var xfRow,   xfSlider,   xfVal;
var volRow,  volSlider,  volVal;
var panicBtn, hudRoutine, r;

win.layout = layout;
layout.margins = [12, 12, 12, 12];
layout.spacing = 6;

// ── Titolo ────────────────────────────────────────────────────────────────────
layout.add(
	StaticText().string_("R E M N A N T")
	.font_(Font("Georgia", 12, italic: true))
	.stringColor_(dimCol).align_(\center)
);

// ── Gesto corrente / totale ───────────────────────────────────────────────────
gestLabel = StaticText().string_("— / —")
            .font_(Font("Courier New", 14, bold: true))
            .stringColor_(accentCol).align_(\center);
layout.add(gestLabel);

// ── Categoria Lachenmann ──────────────────────────────────────────────────────
catLabel = StaticText().string_("—")
           .font_(Font("Georgia", 11, italic: true))
           .stringColor_(fgCol).align_(\center);
layout.add(catLabel);

// ── Progress bar del gesto ────────────────────────────────────────────────────
progressBar = UserView()
              .fixedHeight_(6)
              .background_(Color(0.12, 0.12, 0.12))
              .drawFunc_({ |v|
                  var prog = progressBar.getProperty(\progress) ? 0.0;
                  var w    = v.bounds.width * prog;
                  Pen.color_(accentCol);
                  Pen.fillRect(Rect(0, 0, w, v.bounds.height));
              });
progressBar.setProperty(\progress, 0.0);
layout.add(progressBar);

// ── Tempo trascorso / totale ──────────────────────────────────────────────────
timeLabel = StaticText().string_("0.0 / 0.0 s")
            .font_(monoSmall).stringColor_(dimCol).align_(\center);
layout.add(timeLabel);

layout.add(sep.());

// ── START / STOP ──────────────────────────────────────────────────────────────
layout.add(HLayout(
	startBtn = Button()
		.states_([
			["▶  START", fgCol,    Color(0.1, 0.3, 0.1)],
			["▶  RUN",   greenCol, Color(0.05, 0.2, 0.05)],
		])
		.font_(Font("Courier New", 10, bold: true))
		.action_({ |btn|
			if(btn.value == 1) {
				~r_hudStart.();
			} {
				btn.value_(0);
			};
		}),
	stopBtn = Button()
		.states_([["■  STOP", redCol, Color(0.2, 0.05, 0.05)]])
		.font_(Font("Courier New", 10, bold: true))
		.action_({
			~r_hudStop.();
			startBtn.value_(0);
		}),
));

layout.add(sep.());

// ── Tension ───────────────────────────────────────────────────────────────────
r = makeSlider.("tension", accentCol);
tensRow = r[0]; tensSlider = r[1]; tensVal = r[2];
tensSlider.value_(0.3);
tensVal.string_("0.30");
tensSlider.action = { |sl|
	var t = sl.value.round(0.01);
	tensVal.string_(t.asString.padLeft(4, "0"));
	~r_hudManualTension = t;
	~r_gestTension = t;
	if(~r_synths.notNil) {
		~r_nFields.do { |i|
			var entry = ~r_synths[i];
			if(entry.notNil and: { entry[0].notNil }) {
				try { entry[0].set(\tension,
					(~r_gestTension + (~r_flucoTension * 0.4)).clip(0,1)) };
			};
		};
	};
};
// alt+click → torna al valore del gesto corrente dalla score
tensSlider.mouseDownAction = { |sl, x, y, mod|
	if(mod.isAlt) {
		var g  = ~r_hudGestures[~r_timerGestIdx ? 0];
		var sv = if(g.notNil) { g[\tension] } { 0.3 };
		~r_hudManualTension = nil;
		sl.value_(sv);
		tensVal.string_("auto");
	};
};
layout.add(tensRow);

// ── Gate meter ────────────────────────────────────────────────────────────────
layout.add(
	HLayout(
		StaticText().string_("gate").font_(monoFont).stringColor_(dimCol),
		gateMeter = UserView()
		            .fixedHeight_(14)
		            .background_(Color(0.12, 0.12, 0.12))
		            .drawFunc_({ |v|
		                var gv  = gateMeter.getProperty(\gateVal) ? 0.0;
		                var w   = v.bounds.width * gv;
		                var col = if(gv > 0.7) { redCol } { greenCol };
		                Pen.color_(col);
		                Pen.fillRect(Rect(0, 0, w, v.bounds.height));
		            })
	)
);
gateMeter.setProperty(\gateVal, 0.0);

r = makeSlider.("gate thr (dB)", Color(0.6,0.6,0.6));
thrRow = r[0]; thrSlider = r[1]; thrVal = r[2];
thrSlider.value_((-42 - (-80)) / 80);
thrVal.string_("-42");
thrSlider.action = { |sl|
	var db = ((sl.value * 80) - 80).round(1);
	thrVal.string_(db.asString);
	~r_gateThresh = db;
	if(~r_gateSynth.notNil) { try { ~r_gateSynth.set(\thresh, db) } };
};
layout.add(thrRow);

r = makeSlider.("gate rel (s)", Color(0.6,0.6,0.6));
relRow = r[0]; relSlider = r[1]; relVal = r[2];
relSlider.value_(1.2 / 8.0);
relVal.string_("1.2");
relSlider.action = { |sl|
	var rv = (sl.value * 8.0).round(0.1);
	relVal.string_(rv.asString);
	~r_gateRelease = rv;
	if(~r_gateSynth.notNil) { try { ~r_gateSynth.set(\releaseTime, rv) } };
};
layout.add(relRow);

layout.add(sep.());

r = makeSlider.("xfade (s)", Color(0.6,0.6,0.6));
xfRow = r[0]; xfSlider = r[1]; xfVal = r[2];
xfSlider.value_(3.0 / 12.0);
xfVal.string_("3.0");
xfSlider.action = { |sl|
	var xv = (sl.value * 12.0).round(0.1).max(0.1);
	xfVal.string_(xv.asString);
	~r_xfadeTime = xv;
};
layout.add(xfRow);

r = makeSlider.("master vol", Color(0.6,0.6,0.6));
volRow = r[0]; volSlider = r[1]; volVal = r[2];
volSlider.value_(1.0 / 3.0);
volVal.string_("1.0");
volSlider.action = { |sl|
	var vv = (sl.value * 3.0).round(0.01);
	volVal.string_(vv.asString);
	~r_masterVol = vv;
	if(~r_synths.notNil) {
		~r_nFields.do { |i|
			var entry = ~r_synths[i];
			if(entry.notNil and: { entry[2].notNil }) {
				try { entry[2].set(\amp, vv) };
			};
		};
	};
};
layout.add(volRow);

layout.add(sep.());

// ── PANIC ─────────────────────────────────────────────────────────────────────
panicBtn = Button()
	.states_([["PANIC", Color.red, Color(0.15,0.05,0.05)]])
	.font_(Font("Courier New", 10, bold: true))
	.action_({
		~r_hudStop.();
		startBtn.value_(0);
		if(~r_panic.notNil) { ~r_panic.() };
	});
layout.add(panicBtn);

// ── Aggiorna display (gesto, categoria, tension) ──────────────────────────────
~r_hudUpdateDisplay = {
	var nGest   = ~r_hudGestures.size;
	var idx     = ~r_timerGestIdx ? 0;
	var g       = ~r_hudGestures[idx];
	var cat     = if(g.notNil) { g[\cat] }     { "—" };
	var tension = if(g.notNil) { g[\tension] } { 0.3 };
	var gLabel  = if(~r_timerRunning) {
		(idx + 1).asString ++ " / " ++ nGest
	} { "— / " ++ nGest };
	{
		gestLabel.string_(gLabel);
		catLabel.string_(cat);
		if(~r_hudManualTension.isNil) {
			tensSlider.value_(tension);
			tensVal.string_(tension.round(0.01).asString.padLeft(4,"0"));
		};
	}.defer;
};

// ── Routine di refresh: gate + progress bar + tempo ───────────────────────────
hudRoutine = Routine({
	var gv, elapsed, g, gestDur, prog, gestElapsed;
	loop {
		0.08.wait;

		// gate meter
		gv = if(~r_gateBus.notNil) { ~r_gateBus.getSynchronous } { 1.0 };
		~r_hudGateLevel = gv;

		// progress bar e display tempo
		if(~r_timerRunning and: { ~r_hudGestures.size > 0 }) {
			var idx = ~r_timerGestIdx ? 0;
			g           = ~r_hudGestures[idx];
			gestDur     = if(g.notNil) { (g[\tEnd] - g[\tStart]).max(0.001) } { 1.0 };
			elapsed     = thisThread.seconds - ~r_timerStartTime;
			gestElapsed = elapsed - (if(g.notNil) { g[\tStart] } { 0.0 });
			prog        = (gestElapsed / gestDur).clip(0, 1);
		} {
			elapsed = 0.0;
			prog    = 0.0;
		};

		{
			gateMeter.setProperty(\gateVal, gv);
			gateMeter.refresh;
			progressBar.setProperty(\progress, prog);
			progressBar.refresh;
			timeLabel.string_(
				elapsed.round(0.1).asString ++ " / "
				++ ~r_hudDuration.round(0.1).asString ++ " s"
			);
		}.defer;
	};
}).play(AppClock);

win.onClose = {
	hudRoutine.stop;
	if(~r_timerRoutine.notNil) { ~r_timerRoutine.stop };
};
win.front;
"HUD open.  ▶ START per avviare · alt+click tension → score value".postln;
)
