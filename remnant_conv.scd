/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMNANT — Convolution Engine                                                ║
║  Launch AFTER remnant_sc.scd                                                 ║
║                                                                              ║
║  Evaluate each block separately (Cmd+Enter) in order:                       ║
║    Block 1 — params + IR generation + SynthDef + gesture override           ║
║    Block 2 — build UI function                                               ║
║    Block 3 — launch UI                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 1 — Engine
// ═══════════════════════════════════════════════════════════════════════════
(
Routine({

// ── params ──────────────────────────────────────────────────────────────────
~conv_cats = ["Klang","Farbklang","Geräusch","Kadenz","Textur","Stille","Neutro","Forward"];

// [irLen, wet, preDelayMs, pitch, modRate]
~conv_params = Dictionary[
	"Klang"     -> [4.0, 0.85, 10, 1.0,  0.1 ],
	"Farbklang" -> [3.0, 0.90,  5, 0.75, 0.3 ],
	"Geräusch"  -> [2.0, 0.95,  0, 1.0,  0.5 ],
	"Kadenz"    -> [1.5, 0.80, 30, 1.0,  0.0 ],
	"Textur"    -> [6.0, 0.92,  0, 0.5,  0.05],
	"Stille"    -> [0.1, 0.30,  0, 1.0,  0.0 ],
	"Neutro"    -> [1.0, 0.60,  0, 1.0,  0.0 ],
	"Forward"   -> [2.5, 0.85, 15, 1.5,  0.2 ],
];

~conv_sr    = s.sampleRate;
~conv_irBufs  = Dictionary.new;

// ── IR generator ─────────────────────────────────────────────────────────────
~conv_genIR = { |cat|
	var p       = ~conv_params[cat];
	var irLen   = p[0];
	var pitch   = p[3];
	var modRate = p[4];
	var sr      = ~conv_sr;
	var n       = (irLen * sr).round.asInteger.max(64);
	var sig     = Signal.newClear(n);
	var t       = 0.0;
	var env     = 0.0;
	var freq    = 0.0;
	var peak    = 0.0;
	var ratios  = [1.0, 1.414, 1.732, 2.236, 2.618];
	var spacing = (sr * 0.08 / pitch.max(0.1)).round.asInteger.max(1);
	var kDecay  = exp(-6.0 / irLen);
	var kAmp    = 1.0;

	switch(cat,
		"Klang", {
			freq = 120.0 * pitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-3.0 * t / irLen);
				sig[i] = (
					sin(2pi * freq * t) * env +
					sin(2pi * freq * 2.0 * t) * env * 0.5 +
					sin(2pi * freq * 3.0 * t) * env * 0.25 +
					sin(2pi * freq * 4.97 * t) * env * 0.15
				) * 0.3;
			};
		},
		"Farbklang", {
			freq = 80.0 * pitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-4.0 * t / irLen);
				sig[i] = ratios.sum({ |r, j|
					sin(2pi * freq * r * t + (j * 0.7)) * env / (j + 1)
				}) * 0.2;
			};
		},
		"Geräusch", {
			n.do { |i|
				t      = i / sr;
				env    = exp(-5.0 * t / irLen);
				sig[i] = (1.0.rand2 * env *
					sin(2pi * (800.0 + 2000.0.rand2) * t)) * 0.4;
			};
		},
		"Kadenz", {
			kAmp = 1.0;
			n.do { |i|
				if((i % spacing) == 0) {
					sig[i] = kAmp;
					kAmp   = kAmp * kDecay;
				} {
					sig[i] = 0.0;
				};
			};
		},
		"Textur", {
			n.do { |i|
				t      = i / sr;
				env    = exp(-1.5 * t / irLen);
				sig[i] = sin(2pi * (200.0 * pitch +
					50.0 * sin(2pi * modRate * t)) * t) * env * 0.35;
			};
		},
		"Stille", {
			sig[0] = 1.0;
			min(n, 16).do { |i|
				sig[i] = exp(-20.0 * i / 16.0) * 0.1;
			};
		},
		"Neutro", {
			freq = 400.0 * pitch;
			n.do { |i|
				t      = i / sr;
				env    = exp(-4.0 * t / irLen);
				sig[i] = sin(2pi * freq * t) * env * 0.5 +
				         1.0.rand2 * env * 0.15;
			};
		},
		"Forward", {
			n.do { |i|
				t      = i / sr;
				env    = (t / irLen) * exp(-3.0 * t / irLen);
				freq   = (200.0 + 1200.0 * (t / irLen)) * pitch;
				sig[i] = sin(2pi * freq * t) * env * 0.5;
			};
		},
	);

	peak = sig.abs.maxItem;
	if(peak > 0) { sig = sig / peak * 0.9 };
	sig
};

// ── allocate IR buffers ───────────────────────────────────────────────────────
~conv_cats.do { |cat|
	var sig = ~conv_genIR.(cat);
	~conv_irBufs[cat] = Buffer.loadCollection(s, sig);
};
s.sync;
"IR buffers ready".postln;

// ── SynthDef ──────────────────────────────────────────────────────────────────
// Uses Convolution2 — works directly with a loaded IR buffer, no preparation needed.
// frameSize must be a power of 2; 2048 is a good balance of latency vs CPU.
SynthDef(\r_conv, {
	|inBus=0, outBus=0, azimuth=180, tension=0.0, irBuf=0, wet=0.85, preDelay=0, amp=1.0|
	var dry, delayed, conv, out;
	var wetAmt = Lag.kr(tension * wet, 0.3);
	var dryAmt = Lag.kr(1.0 - (tension * wet * 0.9), 0.3);
	dry     = SoundIn.ar(inBus);
	delayed = DelayN.ar(dry, 0.5, (preDelay / SampleRate.ir).max(0.0001));
	conv    = Convolution2.ar(delayed, irBuf, 0, 2048, 0.5);
	out     = (dry * dryAmt) + (LeakDC.ar(conv) * wetAmt);
	Out.ar(outBus, Limiter.ar(out * amp, 0.92) ! 2);
}).add;

s.sync;

// ── update category map ───────────────────────────────────────────────────────
~r_catSynth = Dictionary.new;
~conv_cats.do { |cat| ~r_catSynth[cat] = \r_conv };
~r_catSynth["Gerausch"] = \r_conv;

// ── override ~r_gesture ───────────────────────────────────────────────────────
~r_gesture = { |category, tension, azimuth|
	var cat      = category ?? "Neutro";
	var irBuf    = ~conv_irBufs[cat] ?? ~conv_irBufs["Neutro"];
	var params   = ~conv_params[cat]  ?? ~conv_params["Neutro"];
	var wetMax   = params[1];
	var preDelay = (params[2] / 1000.0 * ~conv_sr).round.asInteger;
	var finalT   = (tension + (~r_flucoTension * 0.4)).clip(0, 1);

	~r_gestTension = tension ?? 0.3;
	~r_currentCat  = cat;
	~r_currentAz   = azimuth ?? 180.0;

	// New routing: one proc per field on ~r_fieldChs
	~r_nFields.do { |i|
		var adcBus  = ~r_fieldChs[i];
		var fieldAz = ~r_fieldAz[i];
		var entry   = ~r_synths[i];
		if(entry.notNil) {
			var procA, xfader, spat, procB;
			procA  = entry[0];
			xfader = entry[1];
			spat   = entry[2];
			procB  = Synth(\r_conv, [
				\inBus,    adcBus,
				\outBus,   ~r_procBusB[i].index,
				\azimuth,  fieldAz,
				\tension,  finalT,
				\irBuf,    irBuf.bufnum,
				\wet,      wetMax,
				\preDelay, preDelay,
				\amp,      ~r_masterVol,
			], target: ~r_gProc);
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
				try { procA.free };
				~r_synths[i] = [procB, xfader, spat];
				xfader.set(\busA, ~r_procBusB[i].index,
				           \busB, ~r_procBusA[i].index, \xfade, 0.0);
			}).play(AppClock);
		};
	};
	("▶ Conv: " ++ cat ++ " t=" ++ tension.round(0.01)
	 ++ " wet=" ++ wetMax).postln;
};

// Trigger initial gesture now that ~r_gesture is defined
AppClock.sched(0.1, {
	~r_gesture.("Neutro", 0.3, 180);
	nil;
});

// ── IR regen ─────────────────────────────────────────────────────────────────
~conv_regenIR = { |cat|
	var sig    = ~conv_genIR.(cat);
	var oldBuf = ~conv_irBufs[cat];
	var newBuf = Buffer.loadCollection(s, sig);
	Routine({
		s.sync;
		~conv_irBufs[cat] = newBuf;
		oldBuf.free;
		("IR regen: " ++ cat).postln;
		if(~r_currentCat == cat) {
			~r_gesture.(cat, ~r_gestTension, ~r_currentAz);
		};
	}).play(AppClock);
};

"═══════════════════════════════════════".postln;
"Conv engine ready — now evaluate Block 2 then Block 3".postln;
"═══════════════════════════════════════".postln;

}).play(AppClock);
)


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 2 — UI function definition
// ═══════════════════════════════════════════════════════════════════════════
(
~conv_buildUI = {
	var win        = Window("CONV", Rect(290, 20, 230, 330), resizable: false)
	                 .background_(Color(0.07, 0.07, 0.07, 0.93))
	                 .alwaysOnTop_(true);
	var layout     = VLayout();
	var bgCol      = Color(0.07, 0.07, 0.07, 0.93);
	var accentCol  = Color(0.22, 0.55, 0.9);
	var dimCol     = Color(0.4, 0.4, 0.4);
	var selCol     = Color(0.9, 0.5, 0.1);
	var monoSmall  = Font("Courier New", 9);
	var currentCat = "Neutro";
	var catBtns    = Dictionary.new;
	var paramDefs  = [
		[\irLen,    "IR len (s)",     0.05, 8.0, 0.05, true ],
		[\wet,      "wet max",        0.0,  1.0, 0.01, false],
		[\preDelay, "pre-delay (ms)", 0,    100, 1,    false],
		[\pitch,    "IR pitch",       0.25, 4.0, 0.01, true ],
		[\modRate,  "mod rate (Hz)",  0.0,  4.0, 0.01, false],
	];
	var sliders    = Dictionary.new;
	var valDisplays = Dictionary.new;
	var catGrid;
	var applyBtn;
	var liveBtn;

	win.layout = layout;
	layout.margins = [10, 10, 10, 10];
	layout.spacing = 5;

	// header
	layout.add(
		StaticText()
		.string_("C O N V O L U T I O N")
		.font_(Font("Georgia", 10, italic: true))
		.stringColor_(dimCol)
		.align_(\center)
	);

	// category buttons
	catGrid = HLayout();
	catGrid.spacing = 2;
	catGrid.margins = [0,0,0,0];
	layout.add(catGrid);

	~conv_cats.do { |cat|
		var shortName = cat.copyRange(0, min(3, cat.size - 1));
		var btn = Button()
			.states_([
				[shortName, dimCol,   Color(0.15, 0.15, 0.15)],
				[shortName, bgCol,    selCol],
			])
			.font_(Font("Courier New", 9, bold: true));

		btn.action = { |b|
			if(b.value == 1) {
				var p    = ~conv_params[cat];
				catBtns.do { |ob| if(ob !== btn) { ob.value_(0) } };
				currentCat = cat;
				paramDefs.do { |pd, i|
					var key   = pd[0];
					var mn    = pd[2];
					var mx    = pd[3];
					var isExp = pd[5];
					var val   = p[i];
					var norm  = if(isExp) {
						(log(val) - log(mn)) / (log(mx) - log(mn))
					} {
						(val - mn) / (mx - mn)
					};
					sliders[key].value_(norm.clip(0,1));
					valDisplays[key].string_(val.round(0.01).asString);
				};
			};
		};
		catBtns[cat] = btn;
		catGrid.add(btn);
	};

	layout.add(
		StaticText()
		.string_("────────────────────────")
		.stringColor_(dimCol).font_(monoSmall).align_(\center)
	);

	// sliders
	paramDefs.do { |pd|
		var key    = pd[0];
		var label  = pd[1];
		var mn     = pd[2];
		var mx     = pd[3];
		var step   = pd[4];
		var isExp  = pd[5];
		var row    = HLayout();
		var lbl    = StaticText()
		             .string_(label).font_(monoSmall)
		             .stringColor_(dimCol).fixedWidth_(92);
		var valDisp = StaticText()
		              .string_("—").font_(monoSmall)
		              .stringColor_(accentCol).fixedWidth_(38).align_(\right);
		var sl      = Slider()
		              .orientation_(\horizontal)
		              .background_(Color(0.15,0.15,0.15))
		              .knobColor_(accentCol);

		sl.action = {
			var norm = sl.value;
			var p    = ~conv_params[currentCat].copy;
			var idx  = paramDefs.collect(_[0]).indexOf(key);
			var val  = if(isExp) {
				exp(log(mn) + norm * (log(mx) - log(mn)))
			} {
				mn + norm * (mx - mn)
			}.round(step);
			p[idx] = val;
			valDisp.string_(val.asString);
			~conv_params[currentCat] = p;
		};

		row.margins = [0,0,0,0]; row.spacing = 4;
		row.add(lbl); row.add(sl); row.add(valDisp);
		layout.add(row);
		sliders[key]     = sl;
		valDisplays[key] = valDisp;
	};

	// buttons
	applyBtn = Button()
		.states_([["APPLY + REGEN IR", Color.white, Color(0.1,0.3,0.1)]])
		.font_(Font("Courier New", 9, bold: true))
		.action_({ ~conv_regenIR.(currentCat) });

	liveBtn = Button()
		.states_([["APPLY LIVE", dimCol, Color(0.15,0.15,0.15)]])
		.font_(Font("Courier New", 9, bold: true))
		.action_({
			var p      = ~conv_params[currentCat];
			var wetMax = p[1];
			var preDel = (p[2] / 1000.0 * ~conv_sr).round.asInteger;
			~r_synths.keysValuesDo { |instr, entry|
				if(instr != \mix and: { entry.notNil }) {
					entry[0].set(\wet, wetMax, \preDelay, preDel);
				};
			};
			("Live: " ++ currentCat ++ " wet=" ++ wetMax).postln;
		});

	layout.add(applyBtn);
	layout.add(liveBtn);

	// init sliders to Neutro
	{
		var p = ~conv_params["Neutro"];
		catBtns["Neutro"].value_(1);
		paramDefs.do { |pd, i|
			var key   = pd[0];
			var mn    = pd[2];
			var mx    = pd[3];
			var isExp = pd[5];
			var val   = p[i];
			var norm  = if(isExp) {
				(log(val) - log(mn)) / (log(mx) - log(mn))
			} {
				(val - mn) / (mx - mn)
			};
			sliders[key].value_(norm.clip(0,1));
			valDisplays[key].string_(val.round(0.01).asString);
		};
	}.defer(0.1);

	win.front;
};
"~conv_buildUI defined — evaluate Block 3 to open".postln;
)


// ═══════════════════════════════════════════════════════════════════════════
// BLOCK 3 — Launch UI
// ═══════════════════════════════════════════════════════════════════════════
(
~conv_buildUI.();
"Convolution interface open.".postln;
"  ~conv_regenIR.(\"Klang\")   — regen IR manually".postln;
"  ~conv_params[\"Klang\"]     — inspect params".postln;
)
